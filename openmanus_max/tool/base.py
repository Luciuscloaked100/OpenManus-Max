"""
OpenManus-Max Tool System Base
工具基类与工具集合管理
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

from openmanus_max.core.schema import ToolResult


class BaseTool(ABC, BaseModel):
    """工具基类"""
    name: str
    description: str
    parameters: Optional[Dict] = None

    class Config:
        arbitrary_types_allowed = True

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具"""

    async def __call__(self, **kwargs) -> ToolResult:
        return await self.execute(**kwargs)

    def to_param(self) -> Dict:
        """转换为 OpenAI function calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }

    def success(self, data: Any) -> ToolResult:
        if isinstance(data, str):
            return ToolResult(output=data)
        return ToolResult(output=json.dumps(data, indent=2, ensure_ascii=False, default=str))

    def fail(self, msg: str) -> ToolResult:
        return ToolResult(error=msg)


class ToolCollection:
    """工具集合管理器"""

    def __init__(self, *tools: BaseTool):
        self._tools: Dict[str, BaseTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def unregister(self, name: str):
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    async def execute(self, name: str, **kwargs) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(error=f"Tool '{name}' not found. Available: {list(self._tools.keys())}")
        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            return ToolResult(error=f"Tool '{name}' execution error: {str(e)}")

    def to_params(self) -> List[Dict]:
        """获取所有工具的 function calling 参数"""
        return [tool.to_param() for tool in self._tools.values()]

    @property
    def tool_names(self) -> List[str]:
        return list(self._tools.keys())

    @property
    def tools(self) -> List[BaseTool]:
        return list(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
