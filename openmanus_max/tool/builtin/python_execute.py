"""
OpenManus-Max Python Execute Tool
安全的 Python 代码执行工具，使用子进程隔离
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import os
from typing import Optional

from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


class PythonExecute(BaseTool):
    name: str = "python_execute"
    description: str = """Execute Python code in an isolated subprocess. 
Use this for calculations, data processing, file operations, and any programmatic tasks.
The code runs in a real Python environment with access to installed packages.
Print output to stdout to see results."""
    parameters: dict = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The Python code to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Execution timeout in seconds (default: 30)",
                "default": 30,
            },
        },
        "required": ["code"],
    }

    async def execute(self, code: str, timeout: int = 30) -> ToolResult:
        # 写入临时文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="/tmp"
        ) as f:
            f.write(code)
            tmp_path = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/tmp",
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return self.fail(f"Execution timed out after {timeout}s")

            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                error_msg = stderr_str or f"Process exited with code {proc.returncode}"
                if stdout_str:
                    error_msg = f"STDOUT:\n{stdout_str}\n\nSTDERR:\n{error_msg}"
                return self.fail(error_msg)

            output = stdout_str
            if stderr_str:
                output += f"\n[stderr]: {stderr_str}"
            return self.success(output if output else "(no output)")

        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
