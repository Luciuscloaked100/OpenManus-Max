"""
OpenManus-Max ManusAgent
主通用 Agent，集成所有内置工具、权限引擎、Skill 系统和高级能力
"""

from __future__ import annotations

from typing import List, Optional

from openmanus_max.agent.reflect import ReflectAgent
from openmanus_max.core.config import get_config
from openmanus_max.core.llm import LLM
from openmanus_max.core.schema import ToolResult
from openmanus_max.memory.hierarchical import HierarchicalMemory
from openmanus_max.security.permission import (
    PermissionEngine,
    PermissionMode,
    ToolRisk,
)
from openmanus_max.skills.engine import (
    LoadedSkill,
    SkillRegistry,
    attenuate_tools,
    select_skills,
)
from openmanus_max.tool.base import BaseTool, ToolCollection
from openmanus_max.tool.builtin.python_execute import PythonExecute
from openmanus_max.tool.builtin.shell_exec import ShellExec
from openmanus_max.tool.builtin.file_editor import FileEditor
from openmanus_max.tool.builtin.web_search import WebSearch
from openmanus_max.tool.builtin.web_crawl import WebCrawl
from openmanus_max.tool.builtin.browser import BrowserTool
from openmanus_max.tool.builtin.planning import PlanningTool
from openmanus_max.tool.builtin.terminate import Terminate, AskHuman
from openmanus_max.tool.builtin.vision import VisionTool
from openmanus_max.tool.builtin.data_visualization import DataVisualization
from openmanus_max.tool.builtin.computer_use import ComputerUseTool


MANUS_SYSTEM_PROMPT = """You are OpenManus-Max, an advanced autonomous AI agent capable of solving complex tasks.

You have access to a comprehensive set of tools:

**Core Tools:**
- python_execute: Run Python code for calculations, data processing, and programming tasks
- shell_exec: Execute shell commands for system operations
- file_editor: Read, write, and edit files

**Information & Web:**
- web_search: Search the internet (text, images, news) with multi-engine fallback
- web_crawl: Deep content extraction from web pages (Markdown, links, structured data)
- browser: Browse websites and interact with web pages

**Analysis & Visualization:**
- vision_analyze: Analyze images and PDF pages using LLM vision capabilities
- data_visualization: Generate charts and graphs (bar, line, pie, scatter, heatmap, etc.)

**Planning & Control:**
- planning: Create and manage DAG task plans
- ask_human: Ask the user for clarification when needed
- terminate: End the task with a final answer

**Desktop Automation:**
- computer_use: Control mouse, keyboard, and take screenshots for GUI automation

{permission_info}
{skill_info}

Guidelines:
1. Break complex tasks into manageable steps using the planning tool
2. Use the right tool for each sub-task
3. Use web_crawl for deep content extraction, browser for interactive pages
4. Use vision_analyze for understanding images and PDF documents
5. Use data_visualization for creating charts from data
6. Verify your work before presenting final results
7. If stuck, try alternative approaches before asking for help
8. Always provide clear, well-structured final answers
9. Save important intermediate results to files to prevent data loss
10. Respect the current permission mode and do not attempt to bypass restrictions

When the task is complete, use the terminate tool with a comprehensive summary."""


# 权限模式到枚举的映射
_MODE_MAP = {
    "yolo": PermissionMode.YOLO,
    "standard": PermissionMode.STANDARD,
    "strict": PermissionMode.STRICT,
    "sandbox": PermissionMode.SANDBOX,
}


class ManusAgent(ReflectAgent):
    """主通用 Agent

    继承 ReflectAgent 的反思能力，预装所有内置工具，
    集成权限引擎和 Skill 系统。
    """

    def __init__(
        self,
        name: str = "manus",
        llm: Optional[LLM] = None,
        memory: Optional[HierarchicalMemory] = None,
        extra_tools: Optional[ToolCollection] = None,
        max_steps: int = 0,
        system_prompt: str = "",
        permission_engine: Optional[PermissionEngine] = None,
        skill_registry: Optional[SkillRegistry] = None,
    ):
        config = get_config()

        # 1. 初始化权限引擎
        if permission_engine:
            self.permission = permission_engine
        else:
            mode = _MODE_MAP.get(config.permission.mode.lower(), PermissionMode.STANDARD)
            custom_risks = {
                k: ToolRisk(v) for k, v in config.permission.custom_tool_risks.items()
            }
            self.permission = PermissionEngine(
                mode=mode,
                workspace_dir=config.permission.workspace_dir or config.workspace_dir,
                tool_risks=custom_risks if custom_risks else None,
            )

        # 2. 初始化 Skill 注册表
        if skill_registry:
            self.skill_registry = skill_registry
        elif config.skill.enabled:
            self.skill_registry = SkillRegistry(
                user_skills_dir=config.skill.user_skills_dir,
                installed_skills_dir=config.skill.installed_skills_dir,
                workspace_skills_dir=config.workspace_dir + "/skills" if config.workspace_dir else None,
            )
            self.skill_registry.discover_all()
        else:
            self.skill_registry = None

        # 3. 活跃的 Skills
        self._active_skills: List[LoadedSkill] = []

        # 4. 构建内置工具集
        vision_tool = VisionTool()
        tools = ToolCollection(
            PythonExecute(),
            ShellExec(),
            FileEditor(),
            WebSearch(),
            WebCrawl(),
            BrowserTool(),
            PlanningTool(),
            AskHuman(),
            Terminate(),
            vision_tool,
            DataVisualization(),
            ComputerUseTool(),
        )

        # 注册额外工具
        if extra_tools:
            for tool in extra_tools.tools:
                tools.register(tool)

        # 5. 构建 system prompt
        perm_info = f"**Permission Mode: {self.permission.mode.name}**"
        if self.permission.mode == PermissionMode.YOLO:
            perm_info += "\nYou have full unrestricted access to all operations."
        elif self.permission.mode == PermissionMode.SANDBOX:
            perm_info += f"\nAll operations are restricted to workspace: {self.permission.workspace_dir}"
        elif self.permission.mode == PermissionMode.STRICT:
            perm_info += "\nAll write operations and command executions require user approval."

        skill_info = ""
        if self._active_skills:
            skill_names = [s.manifest.name for s in self._active_skills]
            skill_info = f"**Active Skills:** {', '.join(skill_names)}"

        final_prompt = (system_prompt or MANUS_SYSTEM_PROMPT).format(
            permission_info=perm_info,
            skill_info=skill_info,
        )

        super().__init__(
            name=name,
            llm=llm,
            memory=memory,
            tools=tools,
            system_prompt=final_prompt,
            max_steps=max_steps or config.max_steps,
            reflect_every=3,
        )

        # 为 Vision 工具注入 LLM 引用
        vision_tool.set_llm(self.llm)

        # 为分层记忆注入 LLM 引用（用于智能摘要）
        if self.memory:
            self.memory.set_llm(self.llm)

    def activate_skills_for_task(self, task: str):
        """根据任务内容激活相关 Skills，并应用信任衰减"""
        if not self.skill_registry:
            return

        config = get_config()
        available = self.skill_registry.list_skills()
        if not available:
            return

        self._active_skills = select_skills(
            message=task,
            available_skills=available,
            max_skills=config.skill.max_skills_per_task,
            max_context_tokens=config.skill.max_context_tokens,
        )

        if not self._active_skills:
            return

        # 应用信任衰减
        result = attenuate_tools(
            tool_names=self.tools.tool_names,
            active_skills=self._active_skills,
        )

        if result.removed_tools:
            for tool_name in result.removed_tools:
                self.tools.unregister(tool_name)

        # 将 Skill prompt 注入到系统消息中
        skill_prompts = []
        for skill in self._active_skills:
            skill_prompts.append(
                f"--- Skill: {skill.manifest.name} ---\n{skill.prompt_content}"
            )
        if skill_prompts:
            extra = "\n\n**Activated Skill Instructions:**\n" + "\n\n".join(skill_prompts)
            self.system_prompt += extra

    async def run(self, task: str) -> str:
        """执行任务（重写以集成 Skill 激活）"""
        self.activate_skills_for_task(task)
        return await super().run(task)

    @property
    def status_info(self) -> dict:
        """返回 Agent 完整状态信息"""
        return {
            "name": self.name,
            "state": str(self.state),
            "current_step": self.current_step,
            "tools": self.tools.tool_names,
            "tool_count": len(self.tools),
            "permission_mode": self.permission.mode.name,
            "permission_status": self.permission.status,
            "active_skills": [s.manifest.name for s in self._active_skills],
            "skill_count": len(self.skill_registry.list_skills()) if self.skill_registry else 0,
        }
