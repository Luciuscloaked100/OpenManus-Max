"""
OpenManus-Max IPC Server
通过 stdin/stdout JSON 协议与 Electron 桌面端通信

协议格式（每行一个 JSON）：

输入（Electron → Python）：
  {"type": "task", "payload": {"task": "...", "mode": "standard"}}
  {"type": "command", "payload": {"command": "/tools"}}
  {"type": "permission_response", "payload": {"requestId": "...", "approved": true}}
  {"type": "stop", "payload": {}}
  {"type": "get_status", "payload": {}}
  {"type": "get_tools", "payload": {}}
  {"type": "get_skills", "payload": {}}
  {"type": "get_config", "payload": {}}
  {"type": "set_config", "payload": {"content": "..."}}
  {"type": "set_permission_mode", "payload": {"mode": "yolo"}}

输出（Python → Electron）：
  {"event": "ready", "data": {...}}
  {"event": "thinking", "data": {"step": 1, "thought": "..."}}
  {"event": "tool_call", "data": {"tool": "...", "args": {...}}}
  {"event": "tool_result", "data": {"tool": "...", "output": "..."}}
  {"event": "message", "data": {"role": "agent", "content": "..."}}
  {"event": "permission_request", "data": {"requestId": "...", "tool": "...", "detail": "..."}}
  {"event": "task_complete", "data": {"result": "..."}}
  {"event": "task_error", "data": {"error": "..."}}
  {"event": "status", "data": {...}}
  {"event": "tools", "data": {"tools": [...]}}
  {"event": "skills", "data": {"skills": [...]}}
  {"event": "config", "data": {"content": "..."}}
  {"event": "log", "data": {"level": "info", "text": "..."}}
"""

from __future__ import annotations

import asyncio
import json
import sys
import traceback
from typing import Any, Callable, Dict, Optional

from openmanus_max.core.config import Config, get_config, set_config
from openmanus_max.core.logger import logger


class IPCServer:
    """IPC 通信服务器 - 通过 stdin/stdout 与 Electron 通信"""

    def __init__(self):
        self._agent = None
        self._agent_factory: Optional[Callable] = None
        self._running = False
        self._current_task: Optional[asyncio.Task] = None
        self._permission_futures: Dict[str, asyncio.Future] = {}
        self._permission_counter = 0

    def emit(self, event: str, data: Any = None):
        """向 Electron 发送事件（写入 stdout）"""
        msg = json.dumps({"event": event, "data": data or {}}, ensure_ascii=False)
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()

    def emit_log(self, level: str, text: str):
        """发送日志事件"""
        self.emit("log", {"level": level, "text": text})

    async def start(self, agent_factory: Callable):
        """启动 IPC 服务器主循环"""
        self._agent_factory = agent_factory
        self._running = True

        # 发送 ready 事件
        config = get_config()
        self.emit("ready", {
            "version": "1.0.0",
            "model": config.llm.model,
            "permission_mode": config.permission.mode,
            "workspace": config.workspace_dir,
            "max_steps": config.max_steps,
        })

        # 从 stdin 读取命令
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while self._running:
            try:
                line = await reader.readline()
                if not line:
                    break
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue

                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError:
                    self.emit_log("error", f"Invalid JSON: {line_str[:100]}")
                    continue

                await self._handle_message(msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.emit_log("error", f"IPC error: {str(e)}")

        self._running = False

    async def _handle_message(self, msg: dict):
        """处理来自 Electron 的消息"""
        msg_type = msg.get("type", "")
        payload = msg.get("payload", {})

        try:
            if msg_type == "task":
                await self._handle_task(payload)
            elif msg_type == "stop":
                await self._handle_stop()
            elif msg_type == "command":
                await self._handle_command(payload)
            elif msg_type == "permission_response":
                self._handle_permission_response(payload)
            elif msg_type == "get_status":
                self._handle_get_status()
            elif msg_type == "get_tools":
                self._handle_get_tools()
            elif msg_type == "get_skills":
                self._handle_get_skills()
            elif msg_type == "get_config":
                self._handle_get_config()
            elif msg_type == "set_config":
                self._handle_set_config(payload)
            elif msg_type == "set_permission_mode":
                self._handle_set_permission_mode(payload)
            else:
                self.emit_log("warning", f"Unknown message type: {msg_type}")
        except Exception as e:
            self.emit("task_error", {"error": str(e), "traceback": traceback.format_exc()})

    async def _handle_task(self, payload: dict):
        """处理任务请求"""
        task = payload.get("task", "")
        if not task:
            self.emit("task_error", {"error": "Empty task"})
            return

        # 如果有正在运行的任务，先停止
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            try:
                await self._current_task
            except asyncio.CancelledError:
                pass

        # 创建新 Agent
        permission_mode = payload.get("mode")
        self._agent = self._agent_factory(permission_mode)

        # 注入 IPC 回调到 Agent
        self._inject_ipc_hooks()

        self.emit("task_started", {"task": task})

        # 异步执行任务
        self._current_task = asyncio.create_task(self._run_task(task))

    async def _run_task(self, task: str):
        """执行任务并发送事件流"""
        try:
            # 重写 Agent 的 run 方法来发送中间事件
            agent = self._agent
            agent.state = "idle"
            agent.current_step = 0
            agent.memory.add_message(
                __import__("openmanus_max.core.schema", fromlist=["Message"]).Message.user(task)
            )
            agent.memory.bb_set("task", task)

            # 激活 Skills
            if hasattr(agent, "activate_skills_for_task"):
                agent.activate_skills_for_task(task)

            results = []
            while agent.current_step < agent.max_steps:
                agent.current_step += 1
                step = agent.current_step

                # Think
                self.emit("thinking", {
                    "step": step,
                    "max_steps": agent.max_steps,
                    "status": "Analyzing and planning next action..."
                })

                should_act, thought = await agent.think()
                if thought:
                    self.emit("thought", {"step": step, "content": thought})

                if not should_act:
                    self.emit("message", {
                        "role": "agent",
                        "content": thought or "Task analysis complete.",
                        "step": step,
                    })
                    break

                # Act - 获取最后一个 tool call 信息
                last_msg = agent.memory.working[-1] if agent.memory.working else None
                if last_msg and hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    for tc in last_msg.tool_calls:
                        func = tc.get("function", {})
                        tool_name = func.get("name", "unknown")
                        tool_args = func.get("arguments", "{}")
                        self.emit("tool_call", {
                            "step": step,
                            "tool": tool_name,
                            "args": tool_args if isinstance(tool_args, str) else json.dumps(tool_args),
                        })

                action_result = await agent.act()

                self.emit("tool_result", {
                    "step": step,
                    "output": str(action_result)[:2000],
                })

                if agent._check_stuck(action_result):
                    self.emit("message", {
                        "role": "agent",
                        "content": "Detected repeated actions, stopping to avoid infinite loop.",
                        "step": step,
                    })
                    break

                results.append(action_result)

                # Reflect
                should_continue = await agent.reflect(action_result)
                if not should_continue:
                    break

                if agent._is_terminated(action_result):
                    break

            final = results[-1] if results else "No actions taken."
            self.emit("task_complete", {"result": str(final), "steps": agent.current_step})

        except asyncio.CancelledError:
            self.emit("task_error", {"error": "Task cancelled by user"})
        except Exception as e:
            self.emit("task_error", {
                "error": str(e),
                "traceback": traceback.format_exc(),
            })

    def _inject_ipc_hooks(self):
        """注入 IPC 回调到 Agent 的权限引擎"""
        if not self._agent or not hasattr(self._agent, "permission"):
            return

        # 替换权限引擎的 ask_user 方法为 IPC 版本
        original_check = self._agent.permission.check_and_approve

        async def ipc_check_and_approve(tool_name: str, detail: str = "") -> bool:
            """通过 IPC 请求用户审批"""
            from openmanus_max.security.permission import PermissionMode
            if self._agent.permission.mode == PermissionMode.YOLO:
                return True

            # 检查是否已经被批准
            risk = self._agent.permission.get_tool_risk(tool_name)
            if self._agent.permission._is_approved(tool_name):
                return True

            # 发送权限请求到 Electron
            self._permission_counter += 1
            request_id = f"perm_{self._permission_counter}"

            self.emit("permission_request", {
                "requestId": request_id,
                "tool": tool_name,
                "risk": risk.name if hasattr(risk, "name") else str(risk),
                "detail": detail,
            })

            # 等待用户响应
            future = asyncio.get_event_loop().create_future()
            self._permission_futures[request_id] = future

            try:
                approved = await asyncio.wait_for(future, timeout=300)  # 5 分钟超时
            except asyncio.TimeoutError:
                approved = False
                self.emit_log("warning", f"Permission request timed out: {tool_name}")
            finally:
                self._permission_futures.pop(request_id, None)

            if approved:
                self._agent.permission.approve_session(tool_name)

            return approved

        # 注入
        self._agent.permission.check_and_approve = ipc_check_and_approve

    def _handle_permission_response(self, payload: dict):
        """处理用户的权限审批响应"""
        request_id = payload.get("requestId", "")
        approved = payload.get("approved", False)

        future = self._permission_futures.get(request_id)
        if future and not future.done():
            future.set_result(approved)

    async def _handle_stop(self):
        """停止当前任务"""
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            self.emit("task_error", {"error": "Task stopped by user"})

    async def _handle_command(self, payload: dict):
        """处理内置命令"""
        command = payload.get("command", "")

        if command == "/tools":
            self._handle_get_tools()
        elif command == "/status":
            self._handle_get_status()
        elif command == "/skills":
            self._handle_get_skills()
        elif command == "/memory":
            if self._agent and self._agent.memory:
                self.emit("status", {"memory": self._agent.memory.stats})
            else:
                self.emit("status", {"memory": {}})
        else:
            self.emit_log("info", f"Unknown command: {command}")

    def _handle_get_status(self):
        """返回 Agent 状态"""
        if self._agent:
            self.emit("status", self._agent.status_info)
        else:
            config = get_config()
            self.emit("status", {
                "name": "manus",
                "state": "idle",
                "current_step": 0,
                "tools": [],
                "tool_count": 0,
                "permission_mode": config.permission.mode.upper(),
                "active_skills": [],
                "skill_count": 0,
            })

    def _handle_get_tools(self):
        """返回工具列表"""
        if self._agent:
            tools = []
            for name in sorted(self._agent.tools._tools.keys()):
                tool = self._agent.tools.get(name)
                tools.append({
                    "name": name,
                    "description": tool.description[:120] if tool else "",
                })
            self.emit("tools", {"tools": tools})
        else:
            # 返回默认工具列表
            default_tools = [
                {"name": "python_execute", "description": "Execute Python code"},
                {"name": "shell_exec", "description": "Execute shell commands"},
                {"name": "file_editor", "description": "Read, write, and edit files"},
                {"name": "web_search", "description": "Search the internet"},
                {"name": "web_crawl", "description": "Deep content extraction from web pages"},
                {"name": "browser", "description": "Browse and interact with web pages"},
                {"name": "planning", "description": "Create and manage DAG task plans"},
                {"name": "ask_human", "description": "Ask the user for clarification"},
                {"name": "terminate", "description": "End the task with a final answer"},
                {"name": "vision_analyze", "description": "Analyze images using LLM vision"},
                {"name": "data_visualization", "description": "Generate charts and graphs"},
                {"name": "computer_use", "description": "Desktop GUI automation"},
                {"name": "parallel_map", "description": "Execute parallel subtasks"},
                {"name": "schedule", "description": "Schedule tasks for future execution"},
                {"name": "image_generate", "description": "Generate images from text"},
                {"name": "text_to_speech", "description": "Convert text to speech audio"},
                {"name": "slides_generate", "description": "Generate slide presentations"},
                {"name": "web_scaffold", "description": "Create web project scaffolds"},
            ]
            self.emit("tools", {"tools": default_tools})

    def _handle_get_skills(self):
        """返回 Skill 列表"""
        if self._agent and hasattr(self._agent, "skill_registry") and self._agent.skill_registry:
            skills = []
            for s in self._agent.skill_registry.list_skills():
                skills.append({
                    "name": s.manifest.name,
                    "version": s.manifest.version,
                    "description": s.manifest.description,
                    "author": s.manifest.author,
                    "trust": "trusted" if s.trust == 1 else "installed",
                    "tools": s.manifest.tools,
                })
            self.emit("skills", {"skills": skills})
        else:
            self.emit("skills", {"skills": []})

    def _handle_get_config(self):
        """返回当前配置"""
        config = get_config()
        import os
        config_path = os.path.expanduser("~/.openmanus-max/config.toml")
        content = ""
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                content = f.read()
        self.emit("config", {
            "content": content,
            "model": config.llm.model,
            "base_url": config.llm.base_url,
            "permission_mode": config.permission.mode,
            "workspace": config.workspace_dir,
            "max_steps": config.max_steps,
        })

    def _handle_set_config(self, payload: dict):
        """写入配置"""
        content = payload.get("content", "")
        if content:
            import os
            config_dir = os.path.expanduser("~/.openmanus-max")
            os.makedirs(config_dir, exist_ok=True)
            config_path = os.path.join(config_dir, "config.toml")
            with open(config_path, "w") as f:
                f.write(content)
            # 重新加载
            try:
                new_config = Config.load(config_path)
                set_config(new_config)
                self.emit("config_saved", {"success": True})
            except Exception as e:
                self.emit("config_saved", {"success": False, "error": str(e)})

    def _handle_set_permission_mode(self, payload: dict):
        """切换权限模式"""
        mode_str = payload.get("mode", "standard").lower()
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        mode_map = {
            "yolo": PermissionMode.YOLO,
            "standard": PermissionMode.STANDARD,
            "strict": PermissionMode.STRICT,
            "sandbox": PermissionMode.SANDBOX,
        }
        if mode_str in mode_map:
            if self._agent:
                self._agent.permission = PermissionEngine(
                    mode=mode_map[mode_str],
                    workspace_dir=self._agent.permission.workspace_dir,
                )
            config = get_config()
            config.permission.mode = mode_str
            set_config(config)
            self.emit("permission_changed", {"mode": mode_str.upper()})
        else:
            self.emit_log("error", f"Invalid permission mode: {mode_str}")


async def run_ipc_server(agent_factory: Callable):
    """启动 IPC 服务器"""
    server = IPCServer()
    await server.start(agent_factory)
