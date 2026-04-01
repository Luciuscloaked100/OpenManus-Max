"""
OpenManus-Max Dual Execution Engine
双引擎执行器 —— 统一的命令/代码执行接口

支持三种执行后端:
  - LOCAL:   直接在宿主机执行（受 PermissionEngine 约束）
  - DOCKER:  在 Docker 容器中隔离执行
  - AUTO:    根据 PermissionMode 自动选择（YOLO/STANDARD/STRICT → LOCAL, SANDBOX → DOCKER）
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, Field

from openmanus_max.security.permission import PermissionEngine, PermissionMode


class ExecutionBackend(str, Enum):
    LOCAL = "local"
    DOCKER = "docker"
    AUTO = "auto"


class ExecResult(BaseModel):
    """执行结果"""
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    backend: str = "local"
    blocked: bool = False
    block_reason: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.blocked

    @property
    def output(self) -> str:
        if self.blocked:
            return f"[BLOCKED] {self.block_reason}"
        if self.stderr and self.stdout:
            return f"{self.stdout}\n\n--- stderr ---\n{self.stderr}"
        return self.stdout or self.stderr or "(no output)"


class ExecutionEngine:
    """
    双引擎执行器

    所有命令和代码执行都通过此引擎，它会:
    1. 根据 backend 设置选择执行方式
    2. 通过 PermissionEngine 检查命令安全性
    3. 在需要时请求用户审批
    4. 执行命令并返回结果
    """

    MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB

    def __init__(
        self,
        permission_engine: PermissionEngine,
        backend: ExecutionBackend = ExecutionBackend.AUTO,
        docker_image: str = "python:3.11-slim",
        workspace_dir: Optional[str] = None,
        default_timeout: int = 120,
    ):
        self.permission = permission_engine
        self.backend = backend
        self.docker_image = docker_image
        self.workspace_dir = workspace_dir or permission_engine.workspace_dir
        self.default_timeout = default_timeout

    def _resolve_backend(self) -> str:
        """根据配置和权限模式解析实际执行后端"""
        if self.backend != ExecutionBackend.AUTO:
            return self.backend.value
        if self.permission.mode == PermissionMode.SANDBOX:
            return "docker"
        return "local"

    async def execute_shell(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        """执行 Shell 命令"""
        timeout = timeout or self.default_timeout

        # 1. 命令安全检查
        allowed, reason = self.permission.check_command(command)
        if not allowed:
            return ExecResult(blocked=True, block_reason=reason, backend="blocked")

        # 2. 权限审批
        approved, approval_reason = await self.permission.check_and_approve(
            tool_name="shell_exec",
            description=f"Execute shell command: {command[:100]}",
            parameters={"command": command, "cwd": cwd or ""},
        )
        if not approved:
            return ExecResult(blocked=True, block_reason=approval_reason, backend="denied")

        # 3. 路径检查
        work_dir = cwd or self.workspace_dir
        if work_dir:
            can_read, path_reason = self.permission.check_path_read(work_dir)
            if not can_read:
                return ExecResult(blocked=True, block_reason=path_reason, backend="blocked")

        # 4. 执行
        backend = self._resolve_backend()
        if backend == "docker":
            return await self._execute_docker(command, work_dir, timeout, env)
        else:
            return await self._execute_local(command, work_dir, timeout, env)

    async def execute_python(
        self,
        code: str,
        timeout: int = 30,
        cwd: Optional[str] = None,
    ) -> ExecResult:
        """执行 Python 代码"""
        # 1. 权限审批
        approved, reason = await self.permission.check_and_approve(
            tool_name="python_execute",
            description=f"Execute Python code ({len(code)} chars)",
            parameters={"code_preview": code[:200]},
        )
        if not approved:
            return ExecResult(blocked=True, block_reason=reason, backend="denied")

        # 2. 写入临时文件
        work_dir = cwd or self.workspace_dir
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=work_dir or "/tmp"
        ) as f:
            f.write(code)
            tmp_path = f.name

        try:
            backend = self._resolve_backend()
            if backend == "docker":
                return await self._execute_docker(
                    f"python3 {tmp_path}", work_dir, timeout
                )
            else:
                return await self._execute_local_python(tmp_path, timeout, work_dir)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def _execute_local(
        self,
        command: str,
        cwd: Optional[str],
        timeout: int,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        """本地执行 Shell 命令"""
        try:
            full_env = {**os.environ, **(env or {})}
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd or os.getcwd(),
                env=full_env,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ExecResult(
                    exit_code=-1,
                    stderr=f"Command timed out after {timeout}s",
                    backend="local",
                )

            stdout_str, truncated_out = self._truncate(stdout)
            stderr_str, truncated_err = self._truncate(stderr)

            return ExecResult(
                exit_code=proc.returncode or 0,
                stdout=stdout_str,
                stderr=stderr_str,
                truncated=truncated_out or truncated_err,
                backend="local",
            )
        except Exception as e:
            return ExecResult(
                exit_code=-1, stderr=str(e), backend="local"
            )

    async def _execute_local_python(
        self,
        script_path: str,
        timeout: int,
        cwd: Optional[str],
    ) -> ExecResult:
        """本地执行 Python 脚本"""
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd or "/tmp",
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ExecResult(
                    exit_code=-1,
                    stderr=f"Python execution timed out after {timeout}s",
                    backend="local",
                )

            stdout_str, t1 = self._truncate(stdout)
            stderr_str, t2 = self._truncate(stderr)

            return ExecResult(
                exit_code=proc.returncode or 0,
                stdout=stdout_str,
                stderr=stderr_str,
                truncated=t1 or t2,
                backend="local",
            )
        except Exception as e:
            return ExecResult(exit_code=-1, stderr=str(e), backend="local")

    async def _execute_docker(
        self,
        command: str,
        cwd: Optional[str],
        timeout: int,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        """Docker 容器内执行"""
        try:
            # 构建 docker run 命令
            docker_args = [
                "docker", "run", "--rm",
                "--network=none",  # 默认无网络
                f"--memory=512m",
                f"--cpus=1.0",
                "--pids-limit=256",
                "--read-only",
                "--tmpfs", "/tmp:rw,size=256m",
            ]

            # 挂载工作区
            if cwd and os.path.isdir(cwd):
                docker_args.extend(["-v", f"{cwd}:/workspace:rw"])
                docker_args.extend(["-w", "/workspace"])

            # 环境变量
            for k, v in (env or {}).items():
                docker_args.extend(["-e", f"{k}={v}"])

            docker_args.append(self.docker_image)
            docker_args.extend(["sh", "-c", command])

            proc = await asyncio.create_subprocess_exec(
                *docker_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout + 10  # Docker 启动开销
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ExecResult(
                    exit_code=-1,
                    stderr=f"Docker execution timed out after {timeout}s",
                    backend="docker",
                )

            stdout_str, t1 = self._truncate(stdout)
            stderr_str, t2 = self._truncate(stderr)

            return ExecResult(
                exit_code=proc.returncode or 0,
                stdout=stdout_str,
                stderr=stderr_str,
                truncated=t1 or t2,
                backend="docker",
            )
        except FileNotFoundError:
            return ExecResult(
                exit_code=-1,
                stderr="Docker not found. Install Docker or switch to local backend.",
                backend="docker",
            )
        except Exception as e:
            return ExecResult(exit_code=-1, stderr=str(e), backend="docker")

    def _truncate(self, data: bytes) -> Tuple[str, bool]:
        """截断过长的输出"""
        text = data.decode("utf-8", errors="replace").strip()
        if len(text) > self.MAX_OUTPUT_BYTES:
            return text[: self.MAX_OUTPUT_BYTES] + "\n... (truncated)", True
        return text, False

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "backend": self._resolve_backend(),
            "configured_backend": self.backend.value,
            "permission_mode": self.permission.mode.name,
            "workspace_dir": self.workspace_dir,
            "docker_image": self.docker_image,
        }
