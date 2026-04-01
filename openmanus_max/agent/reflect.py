"""
OpenManus-Max ReflectAgent
带反思与自我修正机制的增强 Agent
在每次 act() 之后，由一个轻量级 Critic 评估执行结果
"""

from __future__ import annotations

from typing import Optional

from openmanus_max.agent.toolcall import ToolCallAgent
from openmanus_max.core.llm import LLM
from openmanus_max.core.logger import logger
from openmanus_max.core.schema import Message
from openmanus_max.memory.hierarchical import HierarchicalMemory
from openmanus_max.tool.base import ToolCollection


REFLECT_PROMPT = """You are a critical evaluator. Review the agent's last action and its result.

Evaluate:
1. Did the action make progress toward the goal?
2. Was the result correct and useful?
3. Should the agent continue with the current approach or change strategy?

Respond in this exact format:
ASSESSMENT: <brief assessment>
SHOULD_CONTINUE: <true/false>
SUGGESTION: <what to do next, if any>"""


class ReflectAgent(ToolCallAgent):
    """带反思机制的 Agent

    在标准 ToolCallAgent 的基础上，增加了 reflect() 阶段：
    - 每次工具执行后，调用 LLM 评估结果质量
    - 如果评估不通过，注入修正建议到记忆中
    - 支持配置反思频率（不必每步都反思）
    """

    def __init__(
        self,
        name: str = "reflect_agent",
        llm: Optional[LLM] = None,
        memory: Optional[HierarchicalMemory] = None,
        tools: Optional[ToolCollection] = None,
        system_prompt: str = "",
        max_steps: int = 0,
        reflect_every: int = 2,  # 每 N 步反思一次
    ):
        super().__init__(name, llm, memory, tools, system_prompt, max_steps)
        self.reflect_every = reflect_every
        self._steps_since_reflect = 0

    async def reflect(self, action_result: str) -> bool:
        """反思阶段：评估最近的行动结果"""
        self._steps_since_reflect += 1

        # 不是每步都反思
        if self._steps_since_reflect < self.reflect_every:
            return True

        self._steps_since_reflect = 0

        # 获取任务目标
        goal = self.memory.bb_get("task", "Unknown goal")

        reflect_messages = [
            {"role": "system", "content": REFLECT_PROMPT},
            {"role": "user", "content": f"Goal: {goal}\n\nLast action result:\n{action_result[:2000]}"},
        ]

        try:
            response = await self.llm.ask(
                messages=reflect_messages,
                temperature=0.0,
                max_tokens=500,
            )

            # 解析反思结果
            should_continue = True
            suggestion = ""

            for line in response.strip().split("\n"):
                line = line.strip()
                if line.startswith("SHOULD_CONTINUE:"):
                    val = line.split(":", 1)[1].strip().lower()
                    should_continue = val in ("true", "yes", "1")
                elif line.startswith("SUGGESTION:"):
                    suggestion = line.split(":", 1)[1].strip()
                elif line.startswith("ASSESSMENT:"):
                    assessment = line.split(":", 1)[1].strip()
                    logger.info(f"[{self.name}] Reflection: {assessment}")

            # 如果有建议，注入到记忆中
            if suggestion and should_continue:
                self.memory.add_message(
                    Message.system(f"[Reflection Suggestion] {suggestion}")
                )
                logger.info(f"[{self.name}] Suggestion injected: {suggestion[:100]}")

            return should_continue

        except Exception as e:
            logger.warning(f"[{self.name}] Reflection error (continuing): {e}")
            return True
