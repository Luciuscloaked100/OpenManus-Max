"""
OpenManus-Max BaseAgent
Agent 抽象基类，定义 think → act → reflect 循环
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from openmanus_max.core.config import get_config
from openmanus_max.core.llm import LLM
from openmanus_max.core.logger import logger
from openmanus_max.core.schema import AgentState, Message
from openmanus_max.memory.hierarchical import HierarchicalMemory
from openmanus_max.tool.base import ToolCollection


class BaseAgent(ABC):
    """Agent 基类

    核心循环：
    1. think() - 分析当前状态，决定下一步行动
    2. act() - 执行行动（调用工具）
    3. reflect() - 评估行动结果，决定是否继续
    """

    def __init__(
        self,
        name: str = "agent",
        llm: Optional[LLM] = None,
        memory: Optional[HierarchicalMemory] = None,
        tools: Optional[ToolCollection] = None,
        system_prompt: str = "",
        max_steps: int = 0,
    ):
        self.name = name
        self.llm = llm or LLM()
        self.memory = memory or HierarchicalMemory()
        self.tools = tools or ToolCollection()
        self.system_prompt = system_prompt
        self.max_steps = max_steps or get_config().max_steps
        self.state = AgentState.IDLE
        self.current_step = 0
        self._stuck_count = 0
        self._last_output = ""

        if system_prompt:
            self.memory.add_message(Message.system(system_prompt))

    async def run(self, task: str) -> str:
        """执行任务的主循环"""
        self.state = AgentState.IDLE
        self.current_step = 0
        self.memory.add_message(Message.user(task))
        self.memory.bb_set("task", task)

        logger.info(f"[{self.name}] Starting task: {task[:100]}...")

        results = []
        while self.current_step < self.max_steps:
            self.current_step += 1
            logger.info(f"[{self.name}] Step {self.current_step}/{self.max_steps}")

            # 1. Think
            self.state = AgentState.THINKING
            should_act, thought = await self.think()
            if thought:
                logger.debug(f"[{self.name}] Thought: {thought[:200]}")

            if not should_act:
                logger.info(f"[{self.name}] Decided to stop after thinking")
                break

            # 2. Act
            self.state = AgentState.ACTING
            action_result = await self.act()

            # 检查是否卡住
            if self._check_stuck(action_result):
                logger.warning(f"[{self.name}] Detected stuck state, breaking")
                break

            results.append(action_result)

            # 3. Reflect
            self.state = AgentState.REFLECTING
            should_continue = await self.reflect(action_result)
            if not should_continue:
                logger.info(f"[{self.name}] Decided to stop after reflection")
                break

            # 检查是否任务完成（terminate 工具）
            if self._is_terminated(action_result):
                break

        self.state = AgentState.FINISHED
        final = results[-1] if results else "No actions taken."
        logger.info(f"[{self.name}] Task completed in {self.current_step} steps")
        return final

    @abstractmethod
    async def think(self) -> tuple[bool, str]:
        """思考阶段：分析上下文，决定下一步

        Returns:
            (should_act, thought_text)
        """

    @abstractmethod
    async def act(self) -> str:
        """行动阶段：执行工具调用"""

    async def reflect(self, action_result: str) -> bool:
        """反思阶段：评估结果，默认继续

        子类可以覆盖此方法实现更复杂的反思逻辑
        """
        return True

    def _check_stuck(self, output: str) -> bool:
        """检测是否陷入重复循环"""
        if output == self._last_output and output:
            self._stuck_count += 1
        else:
            self._stuck_count = 0
        self._last_output = output
        return self._stuck_count >= 3

    def _is_terminated(self, output: str) -> bool:
        """检查是否调用了 terminate"""
        return "[TASK COMPLETE]" in output
