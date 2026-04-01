"""
OpenManus-Max Terminate & AskHuman Tools
"""

from __future__ import annotations

import asyncio
from typing import Optional

from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


class Terminate(BaseTool):
    name: str = "terminate"
    description: str = """Terminate the current task and provide a final answer to the user.
Use this when the task is complete or cannot be continued."""
    parameters: dict = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Final message or result to present to the user",
            },
        },
        "required": ["message"],
    }

    async def execute(self, message: str) -> ToolResult:
        return self.success(f"[TASK COMPLETE] {message}")


class AskHuman(BaseTool):
    name: str = "ask_human"
    description: str = """Ask the human user for input or clarification.
Use this when you need additional information, confirmation, or guidance."""
    parameters: dict = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to ask the user",
            },
        },
        "required": ["question"],
    }

    _input_callback: object = None

    class Config:
        arbitrary_types_allowed = True

    async def execute(self, question: str) -> ToolResult:
        print(f"\n{'='*60}")
        print(f"Agent asks: {question}")
        print(f"{'='*60}")

        if self._input_callback:
            response = await self._input_callback(question)
        else:
            response = await asyncio.to_thread(input, "Your answer: ")

        return self.success(f"Human response: {response}")
