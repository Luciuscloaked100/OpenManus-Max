"""
OpenManus-Max Core Schema - 核心数据模型定义
包含 Message、ToolResult、TaskNode、TaskGraph 等基础数据结构
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ============================================================
# Message 相关
# ============================================================

class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """统一消息模型"""
    role: Role
    content: Optional[str] = None
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    base64_image: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        data = {"role": self.role.value}
        if self.content is not None:
            data["content"] = self.content
        if self.name:
            data["name"] = self.name
        if self.tool_calls:
            data["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        return data

    @classmethod
    def system(cls, content: str) -> "Message":
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> "Message":
        return cls(role=Role.USER, content=content)

    @classmethod
    def assistant(cls, content: str, tool_calls: Optional[List] = None) -> "Message":
        return cls(role=Role.ASSISTANT, content=content, tool_calls=tool_calls)

    @classmethod
    def tool_result(cls, content: str, tool_call_id: str, name: str = "") -> "Message":
        return cls(role=Role.TOOL, content=content, tool_call_id=tool_call_id, name=name)


# ============================================================
# Tool 相关
# ============================================================

class ToolResult(BaseModel):
    """工具执行结果"""
    output: Any = None
    error: Optional[str] = None
    base64_image: Optional[str] = None
    files: Optional[List[str]] = None

    class Config:
        arbitrary_types_allowed = True

    def __bool__(self):
        return self.output is not None or self.error is not None

    def __str__(self):
        if self.error:
            return f"Error: {self.error}"
        return str(self.output) if self.output else ""

    @property
    def success(self) -> bool:
        return self.error is None


# ============================================================
# DAG Task 相关
# ============================================================

class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class TaskNode(BaseModel):
    """DAG 任务节点"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    agent_type: Optional[str] = None  # 指定执行的 agent 类型
    dependencies: List[str] = Field(default_factory=list)  # 依赖的节点 ID
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED)


class TaskGraph(BaseModel):
    """DAG 任务图"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal: str
    nodes: Dict[str, TaskNode] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)

    def add_node(self, node: TaskNode) -> str:
        self.nodes[node.id] = node
        return node.id

    def get_ready_nodes(self) -> List[TaskNode]:
        """获取所有依赖已完成、可以执行的节点"""
        ready = []
        for node in self.nodes.values():
            if node.status != TaskStatus.PENDING:
                continue
            deps_met = all(
                self.nodes[dep_id].status == TaskStatus.COMPLETED
                for dep_id in node.dependencies
                if dep_id in self.nodes
            )
            if deps_met:
                ready.append(node)
        return ready

    def mark_running(self, node_id: str):
        if node_id in self.nodes:
            self.nodes[node_id].status = TaskStatus.RUNNING
            self.nodes[node_id].started_at = datetime.now()

    def mark_completed(self, node_id: str, result: str = ""):
        if node_id in self.nodes:
            self.nodes[node_id].status = TaskStatus.COMPLETED
            self.nodes[node_id].result = result
            self.nodes[node_id].completed_at = datetime.now()

    def mark_failed(self, node_id: str, error: str = ""):
        if node_id in self.nodes:
            self.nodes[node_id].status = TaskStatus.FAILED
            self.nodes[node_id].error = error
            self.nodes[node_id].completed_at = datetime.now()

    @property
    def is_complete(self) -> bool:
        return all(n.is_terminal for n in self.nodes.values())

    @property
    def progress(self) -> str:
        total = len(self.nodes)
        if total == 0:
            return "0/0"
        done = sum(1 for n in self.nodes.values() if n.status == TaskStatus.COMPLETED)
        return f"{done}/{total}"

    def format_status(self) -> str:
        """格式化输出任务图状态"""
        icons = {
            TaskStatus.PENDING: "[ ]",
            TaskStatus.READY: "[~]",
            TaskStatus.RUNNING: "[→]",
            TaskStatus.COMPLETED: "[✓]",
            TaskStatus.FAILED: "[✗]",
            TaskStatus.BLOCKED: "[!]",
            TaskStatus.SKIPPED: "[-]",
        }
        lines = [f"Task Graph: {self.goal} ({self.progress})"]
        for node in self.nodes.values():
            icon = icons.get(node.status, "[ ]")
            deps = f" (deps: {', '.join(node.dependencies)})" if node.dependencies else ""
            lines.append(f"  {icon} {node.id}: {node.title}{deps}")
        return "\n".join(lines)


# ============================================================
# Agent 状态
# ============================================================

class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    REFLECTING = "reflecting"
    FINISHED = "finished"
    ERROR = "error"
