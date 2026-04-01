"""
OpenManus-Max Permission Engine
用户可选的多级权限模型 —— 从完全放权到严格沙盒

权限模式 (PermissionMode):
  - YOLO:       完全放权，Agent 可执行任何操作，无需确认
  - STANDARD:   标准模式，高危操作需要用户确认
  - STRICT:     严格管控，所有写操作和命令执行都需确认
  - SANDBOX:    沙盒隔离，所有执行限制在沙盒目录内，禁止系统级操作

工具风险等级 (ToolRisk):
  - READ_ONLY:  只读操作（搜索、查看文件、分析）
  - WORKSPACE:  工作区写操作（创建/编辑文件、生成图表）
  - EXECUTE:    代码/命令执行（Python、Shell）
  - SYSTEM:     系统级操作（安装包、网络请求、桌面控制）
  - DESTRUCTIVE: 破坏性操作（删除文件、格式化、rm -rf）
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import re
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field


# ============================================================
# 1. 枚举定义
# ============================================================

class PermissionMode(IntEnum):
    """权限模式 —— 数值越大越严格"""
    YOLO = 0        # 完全放权
    STANDARD = 1    # 标准模式
    STRICT = 2      # 严格管控
    SANDBOX = 3     # 沙盒隔离


class ToolRisk(IntEnum):
    """工具风险等级 —— 数值越大越危险"""
    READ_ONLY = 0
    WORKSPACE = 1
    EXECUTE = 2
    SYSTEM = 3
    DESTRUCTIVE = 4


class ApprovalDecision(IntEnum):
    """审批决策"""
    APPROVE = 0
    DENY = 1
    APPROVE_SESSION = 2   # 本次会话内同类操作自动批准
    APPROVE_ALWAYS = 3    # 永久批准此工具


# ============================================================
# 2. 工具风险注册表
# ============================================================

# 内置工具的默认风险等级
DEFAULT_TOOL_RISKS: Dict[str, ToolRisk] = {
    # READ_ONLY
    "web_search": ToolRisk.READ_ONLY,
    "web_crawl": ToolRisk.READ_ONLY,
    "browser": ToolRisk.READ_ONLY,
    "vision_analyze": ToolRisk.READ_ONLY,
    "ask_human": ToolRisk.READ_ONLY,
    "terminate": ToolRisk.READ_ONLY,
    "planning": ToolRisk.READ_ONLY,
    # WORKSPACE
    "file_editor": ToolRisk.WORKSPACE,
    "data_visualization": ToolRisk.WORKSPACE,
    "slides_generate": ToolRisk.WORKSPACE,
    "web_scaffold": ToolRisk.WORKSPACE,
    "image_generate": ToolRisk.WORKSPACE,
    "text_to_speech": ToolRisk.WORKSPACE,
    # EXECUTE
    "python_execute": ToolRisk.EXECUTE,
    "shell_exec": ToolRisk.EXECUTE,
    "parallel_map": ToolRisk.EXECUTE,
    # SYSTEM
    "computer_use": ToolRisk.SYSTEM,
    "schedule": ToolRisk.SYSTEM,
}

# 各权限模式下需要审批的最低风险等级
APPROVAL_THRESHOLDS: Dict[PermissionMode, int] = {
    PermissionMode.YOLO: 99,                     # 永不审批（无风险等级能达到 99）
    PermissionMode.STANDARD: ToolRisk.SYSTEM,    # SYSTEM 及以上需审批
    PermissionMode.STRICT: ToolRisk.WORKSPACE,   # WORKSPACE 及以上需审批
    PermissionMode.SANDBOX: ToolRisk.WORKSPACE,  # WORKSPACE 及以上需审批（且限制路径）
}


# ============================================================
# 3. 路径策略
# ============================================================

class PathPolicy(BaseModel):
    """路径访问策略"""
    allowed_read: List[str] = Field(default_factory=lambda: ["/"])
    allowed_write: List[str] = Field(default_factory=list)
    denied_paths: List[str] = Field(default_factory=lambda: [
        "/etc", "/boot", "/sys", "/proc", "/dev",
        "/usr/bin", "/usr/sbin", "/sbin", "/bin",
        os.path.expanduser("~/.ssh"),
        os.path.expanduser("~/.gnupg"),
    ])

    def can_read(self, path: str) -> bool:
        path = os.path.abspath(os.path.expanduser(path))
        for denied in self.denied_paths:
            if path.startswith(os.path.abspath(denied)):
                return False
        for allowed in self.allowed_read:
            if path.startswith(os.path.abspath(allowed)):
                return True
        return False

    def can_write(self, path: str) -> bool:
        path = os.path.abspath(os.path.expanduser(path))
        for denied in self.denied_paths:
            if path.startswith(os.path.abspath(denied)):
                return False
        for allowed in self.allowed_write:
            if path.startswith(os.path.abspath(allowed)):
                return True
        return False


# ============================================================
# 4. 命令策略
# ============================================================

class CommandPolicy(BaseModel):
    """命令执行策略"""
    blocked_commands: List[str] = Field(default_factory=lambda: [
        "rm -rf /", "rm -rf /*", "mkfs", "dd if=",
        ":(){ :|:& };:",  # fork bomb
        "chmod -R 777 /", "chown -R",
        "> /dev/sda", "shutdown", "reboot", "halt",
        "curl | sh", "curl | bash", "wget | sh", "wget | bash",
    ])
    blocked_patterns: List[str] = Field(default_factory=lambda: [
        r"rm\s+-[a-zA-Z]*f[a-zA-Z]*\s+/(?!tmp|home)",  # rm -rf outside /tmp, /home
        r"sudo\s+rm",
        r">\s*/etc/",
        r"pip\s+install.*--break-system-packages",
    ])
    allowed_commands: Optional[List[str]] = None  # None = 不限制; 列表 = 白名单

    def check(self, command: str) -> Tuple[bool, str]:
        """检查命令是否被允许。返回 (allowed, reason)"""
        cmd_lower = command.strip().lower()
        for blocked in self.blocked_commands:
            if blocked.lower() in cmd_lower:
                return False, f"Blocked dangerous command pattern: '{blocked}'"
        for pattern in self.blocked_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return False, f"Command matches blocked pattern: '{pattern}'"
        if self.allowed_commands is not None:
            cmd_base = command.strip().split()[0] if command.strip() else ""
            if cmd_base not in self.allowed_commands:
                return False, f"Command '{cmd_base}' not in allowed list"
        return True, ""


# ============================================================
# 5. 审批上下文与回调
# ============================================================

class ApprovalRequest(BaseModel):
    """审批请求"""
    tool_name: str
    risk_level: ToolRisk
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""

    @property
    def summary(self) -> str:
        risk_names = {0: "READ_ONLY", 1: "WORKSPACE", 2: "EXECUTE", 3: "SYSTEM", 4: "DESTRUCTIVE"}
        return (
            f"[Permission Request] Tool: {self.tool_name} | "
            f"Risk: {risk_names.get(self.risk_level, '?')} | "
            f"{self.description}"
        )


# 审批回调类型: 接收 ApprovalRequest, 返回 ApprovalDecision
ApprovalCallback = Callable[[ApprovalRequest], "asyncio.coroutine"]


async def cli_approval_callback(request: ApprovalRequest) -> ApprovalDecision:
    """默认的 CLI 审批回调 —— 在终端中请求用户确认"""
    print(f"\n{'='*60}")
    print(f"  PERMISSION REQUEST")
    print(f"{'='*60}")
    print(f"  Tool:   {request.tool_name}")
    risk_names = {0: "READ_ONLY", 1: "WORKSPACE", 2: "EXECUTE", 3: "SYSTEM", 4: "DESTRUCTIVE"}
    print(f"  Risk:   {risk_names.get(request.risk_level, '?')}")
    print(f"  Action: {request.description}")
    if request.parameters:
        for k, v in request.parameters.items():
            val_str = str(v)[:120]
            print(f"  {k}: {val_str}")
    if request.reason:
        print(f"  Reason: {request.reason}")
    print(f"{'='*60}")
    print(f"  [y] Approve  [n] Deny  [s] Approve for session  [a] Always approve this tool")

    response = await asyncio.to_thread(input, "  Your choice [y/n/s/a]: ")
    response = response.strip().lower()

    if response in ("y", "yes"):
        return ApprovalDecision.APPROVE
    elif response in ("s", "session"):
        return ApprovalDecision.APPROVE_SESSION
    elif response in ("a", "always"):
        return ApprovalDecision.APPROVE_ALWAYS
    else:
        return ApprovalDecision.DENY


# ============================================================
# 6. 权限引擎 (核心)
# ============================================================

class PermissionEngine:
    """
    权限引擎 —— 所有工具执行前的安全闸门

    职责:
    1. 根据当前 PermissionMode 判断工具是否需要审批
    2. 在 SANDBOX 模式下强制路径限制
    3. 检查命令安全性
    4. 管理会话级和永久级审批缓存
    5. 支持自定义审批回调（CLI / Web UI / API）
    """

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.STANDARD,
        workspace_dir: Optional[str] = None,
        approval_callback: Optional[ApprovalCallback] = None,
        tool_risks: Optional[Dict[str, ToolRisk]] = None,
    ):
        self.mode = mode
        self.workspace_dir = os.path.abspath(
            os.path.expanduser(workspace_dir or "~/.openmanus-max/workspace")
        )
        self.approval_callback = approval_callback or cli_approval_callback
        self.tool_risks = {**DEFAULT_TOOL_RISKS, **(tool_risks or {})}

        # 审批缓存
        self._session_approved: Set[str] = set()   # 本次会话已批准的工具
        self._always_approved: Set[str] = set()     # 永久批准的工具

        # 根据模式构建策略
        self.path_policy = self._build_path_policy()
        self.command_policy = self._build_command_policy()

    def _build_path_policy(self) -> PathPolicy:
        """根据权限模式构建路径策略"""
        if self.mode == PermissionMode.YOLO:
            return PathPolicy(
                allowed_read=["/"],
                allowed_write=["/"],
                denied_paths=[],
            )
        elif self.mode == PermissionMode.STANDARD:
            return PathPolicy(
                allowed_read=["/"],
                allowed_write=[
                    self.workspace_dir,
                    "/tmp",
                    os.path.expanduser("~"),
                ],
            )
        elif self.mode == PermissionMode.STRICT:
            return PathPolicy(
                allowed_read=[
                    self.workspace_dir,
                    "/tmp",
                    os.path.expanduser("~"),
                ],
                allowed_write=[
                    self.workspace_dir,
                    "/tmp",
                ],
            )
        else:  # SANDBOX
            return PathPolicy(
                allowed_read=[self.workspace_dir, "/tmp"],
                allowed_write=[self.workspace_dir, "/tmp"],
                denied_paths=[
                    "/etc", "/boot", "/sys", "/proc", "/dev",
                    "/usr", "/sbin", "/bin",
                    os.path.expanduser("~/.ssh"),
                    os.path.expanduser("~/.gnupg"),
                    os.path.expanduser("~/.config"),
                ],
            )

    def _build_command_policy(self) -> CommandPolicy:
        """根据权限模式构建命令策略"""
        if self.mode == PermissionMode.YOLO:
            return CommandPolicy(blocked_commands=[], blocked_patterns=[])
        elif self.mode == PermissionMode.SANDBOX:
            return CommandPolicy(
                allowed_commands=[
                    "python3", "python", "pip", "pip3", "node", "npm", "npx",
                    "pnpm", "yarn", "git", "ls", "cat", "head", "tail", "grep",
                    "find", "wc", "sort", "uniq", "echo", "mkdir", "cp", "mv",
                    "touch", "tar", "zip", "unzip", "curl", "wget", "jq",
                    "sed", "awk", "diff", "tee", "bc", "date",
                ],
            )
        else:
            return CommandPolicy()  # 默认黑名单

    def get_tool_risk(self, tool_name: str) -> ToolRisk:
        """获取工具的风险等级"""
        return self.tool_risks.get(tool_name, ToolRisk.EXECUTE)

    def needs_approval(self, tool_name: str) -> bool:
        """判断工具是否需要审批"""
        if tool_name in self._always_approved:
            return False
        if tool_name in self._session_approved:
            return False
        risk = self.get_tool_risk(tool_name)
        threshold = APPROVAL_THRESHOLDS.get(self.mode, ToolRisk.SYSTEM)
        return risk >= threshold

    async def check_and_approve(
        self,
        tool_name: str,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """
        检查工具执行权限并在需要时请求审批。

        返回: (approved, reason)
        """
        risk = self.get_tool_risk(tool_name)

        # YOLO 模式直接放行
        if self.mode == PermissionMode.YOLO:
            return True, "YOLO mode: all operations approved"

        # 检查缓存
        if tool_name in self._always_approved:
            return True, f"Tool '{tool_name}' is permanently approved"
        if tool_name in self._session_approved:
            return True, f"Tool '{tool_name}' is approved for this session"

        # 低风险操作直接放行
        threshold = APPROVAL_THRESHOLDS.get(self.mode, ToolRisk.SYSTEM)
        if risk < threshold:
            return True, f"Tool risk ({risk}) below threshold ({threshold})"

        # 需要审批
        request = ApprovalRequest(
            tool_name=tool_name,
            risk_level=risk,
            description=description or f"Execute tool '{tool_name}'",
            parameters=parameters or {},
            reason=f"Permission mode: {self.mode.name}, risk level: {risk.name}",
        )

        decision = await self.approval_callback(request)

        if decision == ApprovalDecision.APPROVE:
            return True, "User approved"
        elif decision == ApprovalDecision.APPROVE_SESSION:
            self._session_approved.add(tool_name)
            return True, "User approved for session"
        elif decision == ApprovalDecision.APPROVE_ALWAYS:
            self._always_approved.add(tool_name)
            return True, "User permanently approved"
        else:
            return False, "User denied the operation"

    def check_path_read(self, path: str) -> Tuple[bool, str]:
        """检查路径读取权限"""
        if self.mode == PermissionMode.YOLO:
            return True, ""
        if self.path_policy.can_read(path):
            return True, ""
        return False, f"Read access denied for path: {path}"

    def check_path_write(self, path: str) -> Tuple[bool, str]:
        """检查路径写入权限"""
        if self.mode == PermissionMode.YOLO:
            return True, ""
        if self.path_policy.can_write(path):
            return True, ""
        return False, f"Write access denied for path: {path}"

    def check_command(self, command: str) -> Tuple[bool, str]:
        """检查命令执行权限"""
        return self.command_policy.check(command)

    def reset_session(self):
        """重置会话级审批缓存"""
        self._session_approved.clear()

    @property
    def status(self) -> Dict[str, Any]:
        """返回当前权限引擎状态"""
        return {
            "mode": self.mode.name,
            "workspace_dir": self.workspace_dir,
            "session_approved": sorted(self._session_approved),
            "always_approved": sorted(self._always_approved),
            "writable_paths": self.path_policy.allowed_write,
            "readable_paths": self.path_policy.allowed_read,
        }
