"""
OpenManus-Max Schedule Tool
Agent 可调用的定时任务管理工具
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from openmanus_max.core.schema import ToolResult
from openmanus_max.scheduler.cron_scheduler import CronScheduler, ScheduledTask
from openmanus_max.tool.base import BaseTool


class ScheduleTool(BaseTool):
    name: str = "schedule"
    description: str = """Manage scheduled/recurring tasks.
- create: Create a new scheduled task (cron or interval)
- list: List all scheduled tasks
- remove: Remove a scheduled task
- status: Get scheduler status

For cron expressions, use 5-field format: minute hour day-of-month month day-of-week
For interval, specify seconds between runs (minimum 300 for recurring)."""
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["create", "list", "remove", "status"],
                "description": "Scheduler command",
            },
            "name": {
                "type": "string",
                "description": "Task name (for create)",
            },
            "prompt": {
                "type": "string",
                "description": "Task description/prompt (for create)",
            },
            "schedule_type": {
                "type": "string",
                "enum": ["cron", "interval"],
                "description": "Schedule type (for create)",
            },
            "schedule_expr": {
                "type": "string",
                "description": "Cron expression or interval in seconds (for create)",
            },
            "repeat": {
                "type": "boolean",
                "description": "Whether to repeat (default: true)",
                "default": True,
            },
            "task_id": {
                "type": "string",
                "description": "Task ID (for remove)",
            },
        },
        "required": ["command"],
    }

    _scheduler: Optional[CronScheduler] = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, scheduler: Optional[CronScheduler] = None, **data):
        super().__init__(**data)
        self._scheduler = scheduler or CronScheduler()

    async def execute(
        self,
        command: str,
        name: Optional[str] = None,
        prompt: Optional[str] = None,
        schedule_type: Optional[str] = None,
        schedule_expr: Optional[str] = None,
        repeat: bool = True,
        task_id: Optional[str] = None,
    ) -> ToolResult:
        if command == "create":
            if not all([name, prompt, schedule_type, schedule_expr]):
                return self.fail("name, prompt, schedule_type, and schedule_expr are required")
            task = ScheduledTask(
                id=str(uuid.uuid4())[:8],
                name=name,
                prompt=prompt,
                schedule_type=schedule_type,
                schedule_expr=schedule_expr,
                repeat=repeat,
            )
            self._scheduler.add_task(task)
            return self.success(
                f"Scheduled task created:\n"
                f"  ID: {task.id}\n"
                f"  Name: {task.name}\n"
                f"  Type: {task.schedule_type}\n"
                f"  Schedule: {task.schedule_expr}\n"
                f"  Repeat: {task.repeat}"
            )

        elif command == "list":
            tasks = self._scheduler.list_tasks()
            if not tasks:
                return self.success("No scheduled tasks.")
            lines = [f"Scheduled Tasks ({len(tasks)}):\n"]
            for t in tasks:
                status = "enabled" if t.enabled else "disabled"
                lines.append(
                    f"  [{t.id}] {t.name} ({t.schedule_type}: {t.schedule_expr}) "
                    f"[{status}] runs: {t.run_count}"
                )
            return self.success("\n".join(lines))

        elif command == "remove":
            if not task_id:
                return self.fail("task_id is required")
            if self._scheduler.remove_task(task_id):
                return self.success(f"Task {task_id} removed.")
            return self.fail(f"Task {task_id} not found.")

        elif command == "status":
            tasks = self._scheduler.list_tasks()
            return self.success(
                f"Scheduler Status:\n"
                f"  Total tasks: {len(tasks)}\n"
                f"  Active: {sum(1 for t in tasks if t.enabled)}\n"
                f"  Total runs: {sum(t.run_count for t in tasks)}"
            )

        return self.fail(f"Unknown command: {command}")
