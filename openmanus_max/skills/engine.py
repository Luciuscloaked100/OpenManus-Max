"""
OpenManus-Max Skill System
基于 SKILL.md 的可扩展技能系统，参考 IronClaw 的信任衰减机制

Skill 来源与信任等级:
  - TRUSTED:   用户在本地 skills/ 目录手动创建的技能，拥有完整工具权限
  - INSTALLED: 从注册表或外部安装的技能，仅可使用只读工具

信任衰减规则 (Trust Attenuation):
  当任何 INSTALLED 级别的 Skill 被激活时，LLM 可见的工具列表
  会被强制缩减为只读白名单，防止恶意 Skill 通过 Prompt 注入
  操纵 Agent 执行危险操作。
"""

from __future__ import annotations

import hashlib
import os
import re
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


# ============================================================
# 1. 信任等级
# ============================================================

class SkillTrust(IntEnum):
    """技能信任等级 —— 数值越小权限越低"""
    INSTALLED = 0   # 外部安装，仅只读
    TRUSTED = 1     # 本地用户创建，完全信任


# ============================================================
# 2. Skill 数据模型
# ============================================================

class ActivationCriteria(BaseModel):
    """技能激活条件"""
    keywords: List[str] = Field(default_factory=list)
    exclude_keywords: List[str] = Field(default_factory=list)
    patterns: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    max_context_tokens: int = 2000


class SkillManifest(BaseModel):
    """SKILL.md 前置元数据"""
    name: str
    version: str = "0.0.0"
    description: str = ""
    activation: ActivationCriteria = Field(default_factory=ActivationCriteria)
    requires: Dict[str, List[str]] = Field(default_factory=dict)


class LoadedSkill(BaseModel):
    """已加载的技能"""
    manifest: SkillManifest
    prompt_content: str
    trust: SkillTrust
    source_path: str
    content_hash: str = ""

    class Config:
        arbitrary_types_allowed = True

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            self.content_hash = hashlib.sha256(
                self.prompt_content.encode()
            ).hexdigest()[:16]


# ============================================================
# 3. SKILL.md 解析器
# ============================================================

class SkillParser:
    """解析 SKILL.md 文件 (YAML frontmatter + Markdown body)"""

    FRONTMATTER_RE = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL
    )

    @classmethod
    def parse_file(cls, path: str, trust: SkillTrust) -> LoadedSkill:
        """从文件路径解析 SKILL.md"""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return cls.parse(content, source_path=path, trust=trust)

    @classmethod
    def parse(cls, content: str, source_path: str = "", trust: SkillTrust = SkillTrust.INSTALLED) -> LoadedSkill:
        """解析 SKILL.md 内容"""
        match = cls.FRONTMATTER_RE.match(content)
        if match:
            frontmatter_str = match.group(1)
            prompt_content = match.group(2).strip()
            manifest_data = cls._parse_yaml_simple(frontmatter_str)
        else:
            prompt_content = content.strip()
            manifest_data = {"name": Path(source_path).parent.name or "unnamed"}

        # 构建 manifest
        activation_data = manifest_data.pop("activation", {})
        requires_data = manifest_data.pop("requires", {})

        activation = ActivationCriteria(**activation_data) if isinstance(activation_data, dict) else ActivationCriteria()
        manifest = SkillManifest(
            activation=activation,
            requires=requires_data if isinstance(requires_data, dict) else {},
            **{k: v for k, v in manifest_data.items() if k in SkillManifest.model_fields},
        )

        # 强制限制
        manifest.activation.keywords = manifest.activation.keywords[:20]
        manifest.activation.patterns = manifest.activation.patterns[:5]
        manifest.activation.tags = manifest.activation.tags[:10]

        return LoadedSkill(
            manifest=manifest,
            prompt_content=prompt_content,
            trust=trust,
            source_path=source_path,
        )

    @staticmethod
    def _parse_yaml_simple(text: str) -> Dict[str, Any]:
        """简易 YAML 解析（避免强依赖 PyYAML）"""
        try:
            import yaml
            return yaml.safe_load(text) or {}
        except ImportError:
            pass
        # 极简回退解析
        result: Dict[str, Any] = {}
        for line in text.strip().split("\n"):
            line = line.strip()
            if ":" in line and not line.startswith("#"):
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if value:
                    result[key] = value
        return result


# ============================================================
# 4. 信任衰减引擎
# ============================================================

# 只读工具白名单 —— 即使在最低信任下也安全的工具
READ_ONLY_TOOLS = frozenset([
    "web_search", "web_crawl", "browser", "vision_analyze",
    "ask_human", "terminate", "planning",
    "data_visualization",  # 生成图表是只读的（输出到 workspace）
])


class AttenuationResult(BaseModel):
    """信任衰减结果"""
    allowed_tools: List[str]
    removed_tools: List[str]
    min_trust: int
    explanation: str


def attenuate_tools(
    tool_names: List[str],
    active_skills: List[LoadedSkill],
) -> AttenuationResult:
    """
    根据激活技能的最低信任等级，过滤工具列表。

    规则:
    - 无技能激活 → 不过滤
    - 全部 TRUSTED → 不过滤
    - 存在 INSTALLED → 仅保留 READ_ONLY_TOOLS
    """
    if not active_skills:
        return AttenuationResult(
            allowed_tools=tool_names,
            removed_tools=[],
            min_trust=SkillTrust.TRUSTED,
            explanation="No skills active, all tools available",
        )

    min_trust = min(s.trust for s in active_skills)

    if min_trust >= SkillTrust.TRUSTED:
        return AttenuationResult(
            allowed_tools=tool_names,
            removed_tools=[],
            min_trust=min_trust,
            explanation="All active skills are trusted, all tools available",
        )

    # 存在 INSTALLED 技能 → 衰减到只读
    allowed = [t for t in tool_names if t in READ_ONLY_TOOLS]
    removed = [t for t in tool_names if t not in READ_ONLY_TOOLS]

    installed_names = [s.manifest.name for s in active_skills if s.trust == SkillTrust.INSTALLED]
    return AttenuationResult(
        allowed_tools=allowed,
        removed_tools=removed,
        min_trust=min_trust,
        explanation=(
            f"Installed skills detected ({', '.join(installed_names)}). "
            f"Tool ceiling reduced to read-only. "
            f"Removed {len(removed)} tools: {', '.join(removed[:5])}{'...' if len(removed) > 5 else ''}"
        ),
    )


# ============================================================
# 5. Skill 选择器（基于消息内容匹配激活的技能）
# ============================================================

def score_skill(message: str, skill: LoadedSkill) -> float:
    """对技能进行激活评分"""
    msg_lower = message.lower()
    score = 0.0

    # 排除关键词检查
    for kw in skill.manifest.activation.exclude_keywords:
        if kw.lower() in msg_lower:
            return 0.0

    # 关键词匹配
    for kw in skill.manifest.activation.keywords:
        if kw.lower() in msg_lower:
            score += 10.0 if kw.lower() == msg_lower else 5.0

    # 标签匹配
    for tag in skill.manifest.activation.tags:
        if tag.lower() in msg_lower:
            score += 3.0

    # 正则匹配
    for pattern in skill.manifest.activation.patterns:
        try:
            if re.search(pattern, message, re.IGNORECASE):
                score += 20.0
        except re.error:
            pass

    return min(score, 100.0)


def select_skills(
    message: str,
    available_skills: List[LoadedSkill],
    max_skills: int = 3,
    max_context_tokens: int = 4000,
) -> List[LoadedSkill]:
    """根据消息内容选择最相关的技能"""
    scored = [(score_skill(message, s), s) for s in available_skills]
    scored = [(sc, s) for sc, s in scored if sc > 0]
    scored.sort(key=lambda x: -x[0])

    selected = []
    total_tokens = 0
    for sc, skill in scored:
        token_est = len(skill.prompt_content) // 4
        if total_tokens + token_est > max_context_tokens:
            break
        selected.append(skill)
        total_tokens += token_est
        if len(selected) >= max_skills:
            break

    return selected


# ============================================================
# 6. Skill 注册表
# ============================================================

class SkillRegistry:
    """
    技能注册表 —— 管理技能的发现、加载和生命周期

    目录结构:
      ~/.openmanus-max/skills/       → TRUSTED (用户本地)
      ~/.openmanus-max/installed/    → INSTALLED (外部安装)
      <workspace>/skills/            → TRUSTED (项目级)
    """

    def __init__(
        self,
        user_skills_dir: Optional[str] = None,
        installed_skills_dir: Optional[str] = None,
        workspace_skills_dir: Optional[str] = None,
    ):
        self.user_skills_dir = os.path.expanduser(
            user_skills_dir or "~/.openmanus-max/skills"
        )
        self.installed_skills_dir = os.path.expanduser(
            installed_skills_dir or "~/.openmanus-max/installed"
        )
        self.workspace_skills_dir = workspace_skills_dir
        self._skills: Dict[str, LoadedSkill] = {}

    def discover_all(self) -> List[LoadedSkill]:
        """扫描所有目录，加载技能"""
        self._skills.clear()

        # 用户本地技能 (TRUSTED)
        self._scan_dir(self.user_skills_dir, SkillTrust.TRUSTED)

        # 工作区技能 (TRUSTED)
        if self.workspace_skills_dir:
            self._scan_dir(self.workspace_skills_dir, SkillTrust.TRUSTED)

        # 安装的技能 (INSTALLED)
        self._scan_dir(self.installed_skills_dir, SkillTrust.INSTALLED)

        return list(self._skills.values())

    def _scan_dir(self, directory: str, trust: SkillTrust):
        """扫描目录中的 SKILL.md 文件"""
        if not os.path.isdir(directory):
            return

        for entry in os.listdir(directory):
            skill_dir = os.path.join(directory, entry)
            skill_file = os.path.join(skill_dir, "SKILL.md")
            if os.path.isfile(skill_file):
                try:
                    skill = SkillParser.parse_file(skill_file, trust)
                    self._skills[skill.manifest.name] = skill
                except Exception as e:
                    pass  # 跳过无法解析的技能

    def get(self, name: str) -> Optional[LoadedSkill]:
        return self._skills.get(name)

    def list_skills(self) -> List[LoadedSkill]:
        return list(self._skills.values())

    def add_skill(self, skill: LoadedSkill):
        self._skills[skill.manifest.name] = skill

    def remove_skill(self, name: str) -> bool:
        return self._skills.pop(name, None) is not None
