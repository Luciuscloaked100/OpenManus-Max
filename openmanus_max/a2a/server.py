"""
OpenManus-Max A2A (Agent-to-Agent) Protocol Server
基于 HTTP 的 Agent 间通信协议，允许外部系统调用本 Agent 的能力
支持 JSON-RPC 2.0 格式，兼容 Google A2A 规范
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from openmanus_max.core.logger import logger


class A2ATask:
    """A2A 任务"""

    def __init__(self, task_id: str, prompt: str):
        self.id = task_id
        self.prompt = prompt
        self.status = "submitted"  # submitted, working, completed, failed
        self.result: Optional[str] = None
        self.error: Optional[str] = None
        self.artifacts: List[Dict] = []
        self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "status": {"state": self.status},
            "result": self.result,
            "error": self.error,
            "artifacts": self.artifacts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class A2AServer:
    """A2A 协议服务器"""

    def __init__(self, agent_factory=None, host: str = "0.0.0.0", port: int = 5000):
        self.agent_factory = agent_factory
        self.host = host
        self.port = port
        self.tasks: Dict[str, A2ATask] = {}
        self._agent_card = {
            "name": "OpenManus-Max",
            "description": "Advanced Autonomous AI Agent Framework",
            "version": "0.1.0",
            "url": f"http://{host}:{port}",
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
            },
            "skills": [
                {"id": "general", "name": "General Task Execution"},
                {"id": "coding", "name": "Code Generation & Execution"},
                {"id": "research", "name": "Web Research & Analysis"},
                {"id": "data", "name": "Data Analysis & Visualization"},
            ],
        }

    def get_agent_card(self) -> Dict:
        """返回 Agent Card（/.well-known/agent.json）"""
        return self._agent_card

    async def handle_task_send(self, request: Dict) -> Dict:
        """处理 tasks/send 请求"""
        params = request.get("params", {})
        message = params.get("message", {})
        prompt = ""

        # 提取文本内容
        parts = message.get("parts", [])
        for part in parts:
            if part.get("type") == "text":
                prompt += part.get("text", "")

        if not prompt:
            return self._error_response(request, -32602, "No text content in message")

        task_id = params.get("id", str(uuid.uuid4()))
        task = A2ATask(task_id=task_id, prompt=prompt)
        self.tasks[task_id] = task

        # 异步执行任务
        asyncio.create_task(self._execute_task(task))

        return self._success_response(request, task.to_dict())

    async def handle_task_get(self, request: Dict) -> Dict:
        """处理 tasks/get 请求"""
        params = request.get("params", {})
        task_id = params.get("id", "")

        if task_id not in self.tasks:
            return self._error_response(request, -32602, f"Task not found: {task_id}")

        return self._success_response(request, self.tasks[task_id].to_dict())

    async def handle_task_cancel(self, request: Dict) -> Dict:
        """处理 tasks/cancel 请求"""
        params = request.get("params", {})
        task_id = params.get("id", "")

        if task_id not in self.tasks:
            return self._error_response(request, -32602, f"Task not found: {task_id}")

        self.tasks[task_id].status = "failed"
        self.tasks[task_id].error = "Cancelled by client"
        return self._success_response(request, self.tasks[task_id].to_dict())

    async def _execute_task(self, task: A2ATask):
        """异步执行 A2A 任务"""
        task.status = "working"
        task.updated_at = datetime.now().isoformat()

        try:
            if self.agent_factory:
                agent = self.agent_factory()
                result = await agent.run(task.prompt)
                task.result = result
                task.artifacts.append({
                    "parts": [{"type": "text", "text": result}],
                })
            else:
                task.result = "Agent factory not configured"

            task.status = "completed"
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            logger.error(f"A2A task {task.id} failed: {e}")

        task.updated_at = datetime.now().isoformat()

    async def handle_jsonrpc(self, body: Dict) -> Dict:
        """统一 JSON-RPC 路由"""
        method = body.get("method", "")

        handlers = {
            "tasks/send": self.handle_task_send,
            "tasks/get": self.handle_task_get,
            "tasks/cancel": self.handle_task_cancel,
        }

        handler = handlers.get(method)
        if not handler:
            return self._error_response(body, -32601, f"Method not found: {method}")

        return await handler(body)

    def _success_response(self, request: Dict, result: Any) -> Dict:
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": result,
        }

    def _error_response(self, request: Dict, code: int, message: str) -> Dict:
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {"code": code, "message": message},
        }

    def create_fastapi_app(self):
        """创建 FastAPI 应用"""
        try:
            from fastapi import FastAPI, Request
            from fastapi.responses import JSONResponse
        except ImportError:
            raise ImportError("FastAPI required for A2A server. pip install fastapi uvicorn")

        app = FastAPI(title="OpenManus-Max A2A Server")

        @app.get("/.well-known/agent.json")
        async def agent_card():
            return JSONResponse(self.get_agent_card())

        @app.post("/")
        async def jsonrpc_endpoint(request: Request):
            body = await request.json()
            response = await self.handle_jsonrpc(body)
            return JSONResponse(response)

        @app.get("/tasks/{task_id}")
        async def get_task(task_id: str):
            if task_id in self.tasks:
                return JSONResponse(self.tasks[task_id].to_dict())
            return JSONResponse({"error": "Not found"}, status_code=404)

        @app.get("/health")
        async def health():
            return {"status": "ok", "tasks": len(self.tasks)}

        return app

    async def start(self):
        """启动 A2A 服务器"""
        try:
            import uvicorn
        except ImportError:
            raise ImportError("uvicorn required. pip install uvicorn")

        app = self.create_fastapi_app()
        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="info")
        server = uvicorn.Server(config)
        logger.info(f"A2A Server starting at http://{self.host}:{self.port}")
        await server.serve()
