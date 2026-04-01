"""
OpenManus-Max Shell Execution Tool
Bash 命令执行工具
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


class ShellExec(BaseTool):
    name: str = "shell_exec"
    description: str = """Execute shell commands in bash.
Use this for file operations, installing packages, running scripts, and system tasks.
Commands run in the current working directory."""
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 120)",
                "default": 120,
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (optional)",
            },
        },
        "required": ["command"],
    }

    # 危险命令黑名单
    _DANGEROUS = ["rm -rf /", "mkfs", "dd if=", ":(){ :|:& };:"]

    async def execute(
        self, command: str, timeout: int = 120, cwd: Optional[str] = None
    ) -> ToolResult:
        # 安全检查
        for danger in self._DANGEROUS:
            if danger in command:
                return self.fail(f"Blocked dangerous command: {command}")

        work_dir = cwd or os.getcwd()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return self.fail(f"Command timed out after {timeout}s")

            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                error_msg = stderr_str or f"Exit code: {proc.returncode}"
                if stdout_str:
                    error_msg = f"STDOUT:\n{stdout_str}\n\nSTDERR:\n{error_msg}"
                return self.fail(error_msg)

            output = stdout_str
            if stderr_str:
                output += f"\n[stderr]: {stderr_str}"
            return self.success(output if output else "(command completed)")

        except Exception as e:
            return self.fail(f"Shell error: {str(e)}")
