"""
OpenManus-Max DAG Task Scheduler
基于有向无环图的任务调度引擎，支持并行执行无依赖的节点
支持多 Agent 类型调度（根据任务类型选择不同 Agent）
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Coroutine, Dict, List, Optional, Type

from openmanus_max.core.config import get_config
from openmanus_max.core.llm import LLM
from openmanus_max.core.logger import logger
from openmanus_max.core.schema import Message, TaskGraph, TaskNode, TaskStatus


PLAN_SYSTEM_PROMPT = """You are a task planning expert. Given a user's goal, decompose it into a directed acyclic graph (DAG) of sub-tasks.

Rules:
1. Each task should be atomic and clearly defined.
2. Identify dependencies between tasks. If task B needs the result of task A, B depends on A.
3. Tasks with no dependencies between them CAN run in parallel.
4. Assign an agent_type to each task based on its nature:
   - "general": General-purpose tasks (default)
   - "code": Programming, code generation, debugging
   - "browser": Web browsing, form filling, web scraping
   - "data_analysis": Data processing, visualization, statistical analysis
   - "research": Deep research, multi-source information gathering
5. Return a JSON array of task objects.

Output format (strict JSON):
[
  {"id": "t1", "title": "...", "description": "...", "agent_type": "general", "dependencies": []},
  {"id": "t2", "title": "...", "description": "...", "agent_type": "code", "dependencies": ["t1"]},
  {"id": "t3", "title": "...", "description": "...", "agent_type": "browser", "dependencies": []},
  {"id": "t4", "title": "...", "description": "...", "agent_type": "general", "dependencies": ["t2", "t3"]}
]

Only output the JSON array, no other text."""


class AgentRegistry:
    """Agent 注册表 - 管理不同类型的 Agent 工厂"""

    def __init__(self):
        self._factories: Dict[str, Callable] = {}
        self._default_factory: Optional[Callable] = None

    def register(self, agent_type: str, factory: Callable):
        """注册一个 Agent 工厂"""
        self._factories[agent_type] = factory
        logger.debug(f"Registered agent type: {agent_type}")

    def set_default(self, factory: Callable):
        """设置默认 Agent 工厂"""
        self._default_factory = factory

    def create(self, agent_type: str) -> Any:
        """根据类型创建 Agent"""
        factory = self._factories.get(agent_type, self._default_factory)
        if factory is None:
            raise ValueError(f"No agent factory registered for type: {agent_type}")
        return factory()

    @property
    def registered_types(self) -> List[str]:
        return list(self._factories.keys())


class DAGScheduler:
    """DAG 任务调度器

    核心职责：
    1. 使用 LLM 将用户目标分解为 DAG 任务图
    2. 拓扑排序，识别可并行的节点
    3. 根据 agent_type 调度不同的 Agent 执行
    4. 支持并发执行
    """

    def __init__(self, llm: Optional[LLM] = None):
        self.llm = llm or LLM()
        self.graph: Optional[TaskGraph] = None
        self.registry = AgentRegistry()

    def register_agent(self, agent_type: str, factory: Callable):
        """注册 Agent 类型"""
        self.registry.register(agent_type, factory)

    def set_default_agent(self, factory: Callable):
        """设置默认 Agent"""
        self.registry.set_default(factory)

    async def plan(self, goal: str, context: str = "") -> TaskGraph:
        """使用 LLM 将目标分解为 DAG 任务图"""
        user_prompt = f"Goal: {goal}"
        if context:
            user_prompt += f"\n\nAdditional context:\n{context}"

        # 如果有注册的 Agent 类型，告知 LLM
        if self.registry.registered_types:
            user_prompt += f"\n\nAvailable agent types: {', '.join(self.registry.registered_types)}"

        messages = [
            Message.system(PLAN_SYSTEM_PROMPT),
            Message.user(user_prompt),
        ]

        response = await self.llm.ask(
            messages=[m.to_dict() for m in messages],
            temperature=0.0,
        )

        # 解析 LLM 返回的 JSON
        graph = TaskGraph(goal=goal)
        try:
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            tasks = json.loads(text)

            for t in tasks:
                node = TaskNode(
                    id=t.get("id", ""),
                    title=t.get("title", ""),
                    description=t.get("description", ""),
                    agent_type=t.get("agent_type", "general"),
                    dependencies=t.get("dependencies", []),
                )
                graph.add_node(node)

            logger.info(f"DAG plan created: {len(graph.nodes)} nodes for goal: {goal}")
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse DAG plan, creating single-node fallback: {e}")
            node = TaskNode(
                id="t1",
                title=goal,
                description=goal,
                agent_type="general",
            )
            graph.add_node(node)

        self.graph = graph
        return graph

    async def execute(
        self,
        graph: TaskGraph,
        executor: Optional[Callable[[TaskNode, TaskGraph], Coroutine[Any, Any, str]]] = None,
        max_concurrent: int = 3,
    ) -> TaskGraph:
        """执行 DAG 任务图

        Args:
            graph: 任务图
            executor: 自定义执行函数。如果为 None，使用 Agent 注册表调度。
            max_concurrent: 最大并发数
        """
        self.graph = graph
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _run_node(node: TaskNode):
            async with semaphore:
                graph.mark_running(node.id)
                logger.info(f"Executing task: [{node.id}] {node.title} (agent: {node.agent_type})")

                # 收集依赖节点的结果作为上下文
                dep_context = self._collect_dependency_results(node, graph)

                try:
                    if executor:
                        result = await executor(node, graph)
                    else:
                        result = await self._execute_with_agent(node, dep_context)
                    graph.mark_completed(node.id, result)
                    logger.info(f"Completed task: [{node.id}] {node.title}")
                except Exception as e:
                    graph.mark_failed(node.id, str(e))
                    logger.error(f"Failed task: [{node.id}] {node.title}: {e}")

        # 循环调度
        max_iterations = len(graph.nodes) * 2
        iteration = 0
        while not graph.is_complete and iteration < max_iterations:
            iteration += 1
            ready_nodes = graph.get_ready_nodes()

            if not ready_nodes:
                has_running = any(
                    n.status == TaskStatus.RUNNING for n in graph.nodes.values()
                )
                if not has_running:
                    for n in graph.nodes.values():
                        if n.status == TaskStatus.PENDING:
                            n.status = TaskStatus.BLOCKED
                    break
                await asyncio.sleep(0.1)
                continue

            tasks = [_run_node(node) for node in ready_nodes]
            await asyncio.gather(*tasks)

        logger.info(f"DAG execution complete: {graph.progress}")
        return graph

    async def _execute_with_agent(self, node: TaskNode, dep_context: str) -> str:
        """使用注册的 Agent 执行任务节点"""
        agent_type = node.agent_type or "general"

        try:
            agent = self.registry.create(agent_type)
        except ValueError:
            logger.warning(f"Agent type '{agent_type}' not registered, using default")
            agent = self.registry.create("general")

        # 构建任务 prompt
        prompt = f"Task: {node.title}\n"
        if node.description:
            prompt += f"Description: {node.description}\n"
        if dep_context:
            prompt += f"\nContext from previous tasks:\n{dep_context}\n"

        result = await agent.run(prompt)
        return result

    def _collect_dependency_results(self, node: TaskNode, graph: TaskGraph) -> str:
        """收集依赖节点的执行结果"""
        results = []
        for dep_id in node.dependencies:
            dep_node = graph.nodes.get(dep_id)
            if dep_node and dep_node.result:
                results.append(f"[{dep_node.title}]: {dep_node.result[:500]}")
        return "\n".join(results)

    def get_status(self) -> str:
        """获取当前任务图状态"""
        if self.graph:
            return self.graph.format_status()
        return "No active task graph"
