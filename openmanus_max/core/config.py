"""
OpenManus-Max Configuration System
支持 TOML 配置文件 + 环境变量覆盖 + 多级权限模式
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM 配置"""
    model: str = "gpt-4.1-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    max_tokens: int = 8192
    temperature: float = 0.0
    max_input_tokens: int = 128000
    timeout: int = 300

    def model_post_init(self, __context: Any) -> None:
        if not self.api_key:
            self.api_key = os.environ.get("OPENAI_API_KEY", "")
        if not self.base_url or self.base_url == "https://api.openai.com/v1":
            env_base = os.environ.get("OPENAI_BASE_URL", "")
            if env_base:
                self.base_url = env_base


class PermissionConfig(BaseModel):
    """权限模式配置"""
    mode: str = "standard"  # yolo / standard / strict / sandbox
    workspace_dir: str = ""  # 覆盖全局 workspace_dir
    docker_image: str = "python:3.11-slim"
    execution_backend: str = "auto"  # auto / local / docker
    custom_tool_risks: Dict[str, int] = Field(default_factory=dict)
    allowed_commands: Optional[List[str]] = None  # sandbox 模式白名单
    extra_denied_paths: List[str] = Field(default_factory=list)


class SkillConfig(BaseModel):
    """Skill 系统配置"""
    enabled: bool = True
    user_skills_dir: str = "~/.openmanus-max/skills"
    installed_skills_dir: str = "~/.openmanus-max/installed"
    max_skills_per_task: int = 3
    max_context_tokens: int = 4000


class RoutineConfig(BaseModel):
    """Routine 守护进程配置"""
    enabled: bool = False
    db_path: str = "~/.openmanus-max/routines.db"
    poll_interval: float = 1.0
    max_concurrent: int = 3


class SandboxConfig(BaseModel):
    """沙箱配置"""
    enabled: bool = True
    type: str = "local"  # local / docker / remote
    work_dir: str = "/tmp/openmanus-max-workspace"
    timeout: int = 120
    max_memory: str = "2g"
    max_cpu: float = 2.0


class SearchConfig(BaseModel):
    """搜索配置"""
    engine: str = "duckduckgo"  # google / bing / duckduckgo
    api_key: str = ""
    max_results: int = 10


class SchedulerConfig(BaseModel):
    """调度器配置"""
    enabled: bool = True
    db_path: str = "~/.openmanus-max/scheduler.db"
    max_concurrent: int = 5


class MemoryConfig(BaseModel):
    """记忆系统配置"""
    working_memory_size: int = 10
    episodic_summary_threshold: int = 5
    max_total_messages: int = 200


class MediaConfig(BaseModel):
    """多媒体配置"""
    image_api: str = "openai"  # openai / stability
    image_api_key: str = ""
    tts_api: str = "openai"
    tts_api_key: str = ""


class Config(BaseModel):
    """全局配置"""
    project_name: str = "OpenManus-Max"
    workspace_dir: str = Field(default_factory=lambda: os.path.expanduser("~/.openmanus-max/workspace"))
    log_level: str = "INFO"
    max_steps: int = 30
    llm: LLMConfig = Field(default_factory=LLMConfig)
    permission: PermissionConfig = Field(default_factory=PermissionConfig)
    skill: SkillConfig = Field(default_factory=SkillConfig)
    routine: RoutineConfig = Field(default_factory=RoutineConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)

    def model_post_init(self, __context: Any) -> None:
        os.makedirs(self.workspace_dir, exist_ok=True)
        # 权限模式的 workspace 默认跟随全局
        if not self.permission.workspace_dir:
            self.permission.workspace_dir = self.workspace_dir

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        """从 TOML 文件加载配置，支持环境变量覆盖"""
        data = {}
        if config_path and os.path.exists(config_path):
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

        config = cls(**data)
        # 环境变量覆盖
        if os.environ.get("OPENAI_API_KEY"):
            config.llm.api_key = os.environ["OPENAI_API_KEY"]
        if os.environ.get("OPENAI_BASE_URL"):
            config.llm.base_url = os.environ["OPENAI_BASE_URL"]
        if os.environ.get("OPENMANUS_PERMISSION_MODE"):
            config.permission.mode = os.environ["OPENMANUS_PERMISSION_MODE"]
        return config


# 全局单例
_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def set_config(config: Config):
    global _config
    _config = config
