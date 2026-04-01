"""
OpenManus-Max MCP Client
Model Context Protocol 客户端 - 连接外部 MCP Server，动态发现并注册工具
支持 stdio 和 SSE 两种传输方式
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from typing import Any, Dict, List, Optional

import httpx

from openmanus_max.core.logger import logger
from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool, ToolCollection


class MCPTool(BaseTool):
    """从 MCP Server 动态发现的工具"""

    name: str = "mcp_tool"
    description: str = ""
    parameters: Dict[str, Any] = {}
    _server: Any = None  # MCPServerConnection reference

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, name: str, description: str, parameters: Dict, server: Any):
        super().__init__(name=name, description=description, parameters=parameters)
        self._server = server

    async def execute(self, **kwargs) -> ToolResult:
        """通过 MCP Server 执行工具"""
        try:
            result = await self._server.call_tool(self.name, kwargs)
            return ToolResult(output=result)
        except Exception as e:
            return ToolResult(error=f"MCP tool '{self.name}' error: {e}")


class MCPServerConnection:
    """MCP Server 连接"""

    def __init__(
        self,
        name: str,
        transport: str = "stdio",
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        url: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        self.name = name
        self.transport = transport
        self.command = command
        self.args = args or []
        self.url = url
        self.env = env or {}
        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._http_client: Optional[httpx.AsyncClient] = None
        self._tools: Dict[str, Dict] = {}
        self._connected = False

    async def connect(self):
        """建立连接"""
        if self.transport == "stdio":
            await self._connect_stdio()
        elif self.transport == "sse":
            await self._connect_sse()
        else:
            raise ValueError(f"Unsupported transport: {self.transport}")
        self._connected = True

    async def _connect_stdio(self):
        """通过 stdio 连接 MCP Server"""
        if not self.command:
            raise ValueError("stdio transport requires 'command'")

        cmd = [self.command] + self.args
        env = {**dict(__import__("os").environ), **self.env}

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # 发送 initialize 请求
        init_result = await self._send_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "openmanus-max", "version": "0.1.0"},
        })
        logger.info(f"MCP Server '{self.name}' initialized: {init_result.get('serverInfo', {}).get('name', 'unknown')}")

        # 发送 initialized 通知
        await self._send_notification("notifications/initialized", {})

    async def _connect_sse(self):
        """通过 SSE 连接 MCP Server"""
        if not self.url:
            raise ValueError("SSE transport requires 'url'")
        self._http_client = httpx.AsyncClient(timeout=30.0)
        logger.info(f"MCP SSE Client connected to {self.url}")

    async def discover_tools(self) -> List[Dict]:
        """发现 MCP Server 提供的工具"""
        if self.transport == "stdio":
            result = await self._send_jsonrpc("tools/list", {})
            tools = result.get("tools", [])
        elif self.transport == "sse":
            resp = await self._http_client.post(
                f"{self.url}/tools/list",
                json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": self._next_id()},
            )
            data = resp.json()
            tools = data.get("result", {}).get("tools", [])
        else:
            tools = []

        self._tools = {t["name"]: t for t in tools}
        logger.info(f"Discovered {len(tools)} tools from MCP Server '{self.name}'")
        return tools

    async def call_tool(self, tool_name: str, arguments: Dict) -> Any:
        """调用 MCP Server 上的工具"""
        if self.transport == "stdio":
            result = await self._send_jsonrpc("tools/call", {
                "name": tool_name,
                "arguments": arguments,
            })
            # 提取内容
            content = result.get("content", [])
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(texts) if texts else json.dumps(result)
        elif self.transport == "sse":
            resp = await self._http_client.post(
                f"{self.url}/tools/call",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                    "id": self._next_id(),
                },
            )
            data = resp.json()
            result = data.get("result", {})
            content = result.get("content", [])
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(texts) if texts else json.dumps(result)

    async def _send_jsonrpc(self, method: str, params: Dict) -> Dict:
        """发送 JSON-RPC 请求（stdio）"""
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise RuntimeError("Not connected")

        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._next_id(),
        }

        data = json.dumps(request) + "\n"
        self._process.stdin.write(data.encode())
        self._process.stdin.flush()

        # 读取响应
        loop = asyncio.get_event_loop()
        line = await loop.run_in_executor(None, self._process.stdout.readline)
        if not line:
            raise RuntimeError("MCP Server closed connection")

        response = json.loads(line.decode().strip())
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")
        return response.get("result", {})

    async def _send_notification(self, method: str, params: Dict):
        """发送 JSON-RPC 通知（无 id，不期望响应）"""
        if not self._process or not self._process.stdin:
            return
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        data = json.dumps(notification) + "\n"
        self._process.stdin.write(data.encode())
        self._process.stdin.flush()

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def disconnect(self):
        """断开连接"""
        if self._process:
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected


class MCPManager:
    """MCP 连接管理器 - 管理多个 MCP Server 连接"""

    def __init__(self):
        self.servers: Dict[str, MCPServerConnection] = {}
        self.tools: Dict[str, MCPTool] = {}

    async def add_server(
        self,
        name: str,
        transport: str = "stdio",
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        url: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> List[MCPTool]:
        """添加并连接一个 MCP Server，返回发现的工具"""
        server = MCPServerConnection(
            name=name,
            transport=transport,
            command=command,
            args=args,
            url=url,
            env=env,
        )
        await server.connect()
        self.servers[name] = server

        # 发现工具
        raw_tools = await server.discover_tools()
        mcp_tools = []
        for t in raw_tools:
            tool_name = f"mcp_{name}_{t['name']}"
            mcp_tool = MCPTool(
                name=tool_name,
                description=t.get("description", f"MCP tool from {name}"),
                parameters=t.get("inputSchema", {}),
                server=server,
            )
            # 实际调用时使用原始名称
            mcp_tool._original_name = t["name"]
            self.tools[tool_name] = mcp_tool
            mcp_tools.append(mcp_tool)

        return mcp_tools

    async def remove_server(self, name: str):
        """移除并断开一个 MCP Server"""
        if name in self.servers:
            await self.servers[name].disconnect()
            del self.servers[name]
            # 移除相关工具
            to_remove = [k for k in self.tools if k.startswith(f"mcp_{name}_")]
            for k in to_remove:
                del self.tools[k]

    def get_tool_collection(self) -> ToolCollection:
        """获取所有 MCP 工具的集合"""
        return ToolCollection(*self.tools.values())

    async def disconnect_all(self):
        """断开所有连接"""
        for server in self.servers.values():
            await server.disconnect()
        self.servers.clear()
        self.tools.clear()
