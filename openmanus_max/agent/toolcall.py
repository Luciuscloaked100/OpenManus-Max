"""
OpenManus-Max ToolCallAgent
基于 LLM Function Calling 的工具调用 Agent
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from openmanus_max.agent.base import BaseAgent
from openmanus_max.core.llm import LLM
from openmanus_max.core.logger import logger
from openmanus_max.core.schema import Message, ToolResult
from openmanus_max.memory.hierarchical import HierarchicalMemory
from openmanus_max.tool.base import ToolCollection


class ToolCallAgent(BaseAgent):
    """基于 Function Calling 的工具调用 Agent

    think() 阶段调用 LLM 获取 tool_calls
    act() 阶段执行工具并收集结果
    """

    def __init__(
        self,
        name: str = "toolcall_agent",
        llm: Optional[LLM] = None,
        memory: Optional[HierarchicalMemory] = None,
        tools: Optional[ToolCollection] = None,
        system_prompt: str = "",
        max_steps: int = 0,
        tool_choice: str = "auto",
    ):
        super().__init__(name, llm, memory, tools, system_prompt, max_steps)
        self.tool_choice = tool_choice
        self._pending_tool_calls: List[Dict] = []

    async def think(self) -> tuple[bool, str]:
        """调用 LLM 获取下一步的工具调用"""
        messages = self.memory.get_context_messages()
        msg_dicts = [m.to_dict() for m in messages]
        tool_params = self.tools.to_params()

        try:
            if tool_params:
                response = await self.llm.ask_tool(
                    messages=msg_dicts,
                    tools=tool_params,
                    tool_choice=self.tool_choice,
                )
            else:
                # 没有工具时退化为普通对话
                text = await self.llm.ask(messages=msg_dicts)
                self.memory.add_message(Message.assistant(text))
                return False, text

            if response is None:
                return False, "LLM returned empty response"

            # 记录 assistant 消息
            assistant_msg = Message.assistant(
                content=response.content or "",
                tool_calls=[tc.model_dump() for tc in response.tool_calls] if response.tool_calls else None,
            )
            self.memory.add_message(assistant_msg)

            if response.tool_calls:
                self._pending_tool_calls = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                    for tc in response.tool_calls
                ]
                thought = response.content or ""
                tool_names = [tc["name"] for tc in self._pending_tool_calls]
                logger.info(f"[{self.name}] Will call tools: {tool_names}")
                return True, thought
            else:
                # LLM 没有调用工具，可能是最终回答
                return False, response.content or ""

        except Exception as e:
            logger.error(f"[{self.name}] Think error: {e}")
            return False, f"Error: {str(e)}"

    async def act(self) -> str:
        """执行所有待处理的工具调用"""
        if not self._pending_tool_calls:
            return "No tool calls to execute"

        results = []
        for tc in self._pending_tool_calls:
            tool_name = tc["name"]
            tool_call_id = tc["id"]

            # 解析参数
            try:
                args = json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
            except json.JSONDecodeError:
                args = {}

            logger.info(f"[{self.name}] Executing: {tool_name}({list(args.keys())})")

            # 执行工具
            result = await self.tools.execute(tool_name, **args)

            # 记录工具结果到记忆
            result_text = str(result)
            self.memory.add_message(
                Message.tool_result(
                    content=result_text,
                    tool_call_id=tool_call_id,
                    name=tool_name,
                )
            )
            results.append(f"[{tool_name}] {result_text}")

        self._pending_tool_calls = []
        return "\n".join(results)
