"""
OpenManus-Max Planning Tool
DAG 任务计划的创建、查看和管理工具
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from openmanus_max.core.schema import TaskGraph, TaskNode, TaskStatus, ToolResult
from openmanus_max.tool.base import BaseTool


class PlanningTool(BaseTool):
    name: str = "planning"
    description: str = """Task planning tool for creating and managing DAG task plans.
- create: Create a new task plan with nodes and dependencies
- view: View current plan status
- mark_step: Mark a step as completed/failed/skipped
- update: Update plan by adding/modifying nodes"""
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["create", "view", "mark_step", "update"],
                "description": "Planning command",
            },
            "goal": {
                "type": "string",
                "description": "Task goal (for create)",
            },
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "agent_type": {"type": "string"},
                        "dependencies": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
                "description": "Task steps (for create/update)",
            },
            "step_id": {
                "type": "string",
                "description": "Step ID (for mark_step)",
            },
            "status": {
                "type": "string",
                "enum": ["completed", "failed", "skipped"],
                "description": "New status (for mark_step)",
            },
            "result": {
                "type": "string",
                "description": "Step result or error message",
            },
        },
        "required": ["command"],
    }

    _graph: Optional[TaskGraph] = None

    class Config:
        arbitrary_types_allowed = True

    async def execute(
        self,
        command: str,
        goal: Optional[str] = None,
        steps: Optional[List[Dict]] = None,
        step_id: Optional[str] = None,
        status: Optional[str] = None,
        result: Optional[str] = None,
    ) -> ToolResult:
        if command == "create":
            return self._create(goal or "Unnamed task", steps or [])
        elif command == "view":
            return self._view()
        elif command == "mark_step":
            return self._mark_step(step_id or "", status or "completed", result)
        elif command == "update":
            return self._update(steps or [])
        else:
            return self.fail(f"Unknown command: {command}")

    def _create(self, goal: str, steps: List[Dict]) -> ToolResult:
        self._graph = TaskGraph(goal=goal)
        for s in steps:
            node = TaskNode(
                id=s.get("id", ""),
                title=s.get("title", ""),
                description=s.get("description", ""),
                agent_type=s.get("agent_type", "general"),
                dependencies=s.get("dependencies", []),
            )
            self._graph.add_node(node)
        return self.success(f"Plan created with {len(self._graph.nodes)} steps:\n{self._graph.format_status()}")

    def _view(self) -> ToolResult:
        if not self._graph:
            return self.fail("No active plan. Use 'create' first.")
        return self.success(self._graph.format_status())

    def _mark_step(self, step_id: str, status: str, result: Optional[str]) -> ToolResult:
        if not self._graph:
            return self.fail("No active plan.")
        if step_id not in self._graph.nodes:
            return self.fail(f"Step '{step_id}' not found.")
        if status == "completed":
            self._graph.mark_completed(step_id, result or "")
        elif status == "failed":
            self._graph.mark_failed(step_id, result or "")
        elif status == "skipped":
            self._graph.nodes[step_id].status = TaskStatus.SKIPPED
        return self.success(f"Step '{step_id}' marked as {status}.\n{self._graph.format_status()}")

    def _update(self, steps: List[Dict]) -> ToolResult:
        if not self._graph:
            return self.fail("No active plan.")
        for s in steps:
            nid = s.get("id", "")
            if nid in self._graph.nodes:
                node = self._graph.nodes[nid]
                if "title" in s:
                    node.title = s["title"]
                if "description" in s:
                    node.description = s["description"]
                if "dependencies" in s:
                    node.dependencies = s["dependencies"]
            else:
                node = TaskNode(
                    id=nid,
                    title=s.get("title", ""),
                    description=s.get("description", ""),
                    agent_type=s.get("agent_type", "general"),
                    dependencies=s.get("dependencies", []),
                )
                self._graph.add_node(node)
        return self.success(f"Plan updated:\n{self._graph.format_status()}")

    @property
    def graph(self) -> Optional[TaskGraph]:
        return self._graph
