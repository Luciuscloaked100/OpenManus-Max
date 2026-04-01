"""
OpenManus-Max Hierarchical Memory System
三层记忆架构：工作记忆 + 情节记忆（LLM 智能摘要）+ 全局黑板
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from openmanus_max.core.config import get_config
from openmanus_max.core.logger import logger
from openmanus_max.core.schema import Message, Role


SUMMARIZE_PROMPT = """Summarize the following conversation segment concisely. 
Focus on: key decisions made, important findings, tool results, and any errors encountered.
Keep it under 200 words. Be factual and specific.

Conversation:
{conversation}

Summary:"""


class EpisodicEntry(BaseModel):
    """情节记忆条目：对一组交互的摘要"""
    summary: str
    step_range: str
    key_findings: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
    llm_generated: bool = False  # 是否由 LLM 生成


class HierarchicalMemory(BaseModel):
    """分层记忆系统

    Layer 1 - Working Memory: 最近 N 步的完整交互（精确上下文）
    Layer 2 - Episodic Memory: 过去步骤的 LLM 智能摘要（压缩上下文）
    Layer 3 - Blackboard: 全局状态树（共享数据）
    """

    # Layer 1: 工作记忆
    working_messages: List[Message] = Field(default_factory=list)
    working_memory_size: int = 10

    # Layer 2: 情节记忆
    episodic_entries: List[EpisodicEntry] = Field(default_factory=list)
    _pending_for_summary: List[Message] = []
    episodic_summary_threshold: int = 5

    # Layer 3: 全局黑板
    blackboard: Dict[str, Any] = Field(default_factory=dict)

    # 系统消息
    system_messages: List[Message] = Field(default_factory=list)

    # LLM 引用（用于智能摘要）
    _llm: Any = None

    max_total_messages: int = 200

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, llm: Any = None, **data):
        super().__init__(**data)
        self._pending_for_summary = []
        self._llm = llm
        config = get_config().memory
        # Only apply config defaults if not explicitly passed in data
        if 'working_memory_size' not in data:
            self.working_memory_size = config.working_memory_size
        if 'episodic_summary_threshold' not in data:
            self.episodic_summary_threshold = config.episodic_summary_threshold
        if 'max_total_messages' not in data:
            self.max_total_messages = config.max_total_messages

    def set_llm(self, llm: Any):
        """设置 LLM 引用（用于智能摘要）"""
        self._llm = llm

    def add_message(self, message: Message):
        """添加消息到工作记忆"""
        if message.role == Role.SYSTEM:
            if not any(m.content == message.content for m in self.system_messages):
                self.system_messages.append(message)
            return

        self.working_messages.append(message)

        while len(self.working_messages) > self.working_memory_size:
            old_msg = self.working_messages.pop(0)
            self._pending_for_summary.append(old_msg)

        if len(self._pending_for_summary) >= self.episodic_summary_threshold:
            self._compress_to_episodic()

    def add_messages(self, messages: List[Message]):
        for m in messages:
            self.add_message(m)

    def _compress_to_episodic(self):
        """将待摘要消息压缩为情节记忆"""
        if not self._pending_for_summary:
            return

        # 构建对话文本
        contents = []
        key_findings = []
        for msg in self._pending_for_summary:
            if msg.content:
                snippet = msg.content[:300]
                contents.append(f"[{msg.role.value}] {snippet}")
                if msg.role == Role.TOOL and len(msg.content) > 20:
                    key_findings.append(msg.content[:150])

        conversation_text = "\n".join(contents)

        # 尝试使用 LLM 做智能摘要
        summary_text = self._try_llm_summarize(conversation_text)
        llm_generated = summary_text is not None

        if not summary_text:
            # 回退到简单拼接
            summary_text = f"Compressed {len(self._pending_for_summary)} messages. "
            summary_text += " | ".join(contents[:3])
            if len(contents) > 3:
                summary_text += f" ... and {len(contents) - 3} more"

        entry = EpisodicEntry(
            summary=summary_text[:800],
            step_range=f"batch of {len(self._pending_for_summary)} msgs",
            key_findings=key_findings[:5],
            llm_generated=llm_generated,
        )
        self.episodic_entries.append(entry)
        self._pending_for_summary = []
        logger.debug(f"Compressed to episodic memory (LLM={llm_generated}), total entries: {len(self.episodic_entries)}")

    def _try_llm_summarize(self, conversation_text: str) -> Optional[str]:
        """尝试使用 LLM 做智能摘要（同步包装）"""
        if not self._llm:
            return None
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在异步上下文中，创建一个 future
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._async_summarize(conversation_text)
                    )
                    return future.result(timeout=15)
            else:
                return asyncio.run(self._async_summarize(conversation_text))
        except Exception as e:
            logger.debug(f"LLM summarize failed, falling back: {e}")
            return None

    async def _async_summarize(self, conversation_text: str) -> str:
        """异步 LLM 摘要"""
        prompt = SUMMARIZE_PROMPT.format(conversation=conversation_text[:3000])
        result = await self._llm.ask(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=300,
        )
        return result

    async def async_compress_pending(self):
        """异步版本的压缩（推荐在 Agent 循环中调用）"""
        if len(self._pending_for_summary) < self.episodic_summary_threshold:
            return
        if not self._pending_for_summary:
            return

        contents = []
        key_findings = []
        for msg in self._pending_for_summary:
            if msg.content:
                snippet = msg.content[:300]
                contents.append(f"[{msg.role.value}] {snippet}")
                if msg.role == Role.TOOL and len(msg.content) > 20:
                    key_findings.append(msg.content[:150])

        conversation_text = "\n".join(contents)
        llm_generated = False
        summary_text = None

        if self._llm:
            try:
                prompt = SUMMARIZE_PROMPT.format(conversation=conversation_text[:3000])
                summary_text = await self._llm.ask(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=300,
                )
                llm_generated = True
            except Exception as e:
                logger.debug(f"Async LLM summarize failed: {e}")

        if not summary_text:
            summary_text = f"Compressed {len(self._pending_for_summary)} messages. "
            summary_text += " | ".join(contents[:3])

        entry = EpisodicEntry(
            summary=summary_text[:800],
            step_range=f"batch of {len(self._pending_for_summary)} msgs",
            key_findings=key_findings[:5],
            llm_generated=llm_generated,
        )
        self.episodic_entries.append(entry)
        self._pending_for_summary = []

    def get_context_messages(self) -> List[Message]:
        """获取完整的上下文消息列表"""
        result = []

        # 1. 系统消息
        result.extend(self.system_messages)

        # 2. 情节记忆摘要
        if self.episodic_entries:
            episodic_text = self._format_episodic()
            result.append(Message.system(
                f"[Historical Context Summary]\n{episodic_text}"
            ))

        # 3. 黑板状态
        if self.blackboard:
            bb_text = self._format_blackboard()
            result.append(Message.system(
                f"[Current Task State]\n{bb_text}"
            ))

        # 4. 工作记忆
        result.extend(self.working_messages)

        return result

    def _format_episodic(self) -> str:
        lines = []
        for i, entry in enumerate(self.episodic_entries[-5:], 1):
            tag = "[LLM]" if entry.llm_generated else "[auto]"
            lines.append(f"Episode {i} {tag} ({entry.step_range}): {entry.summary}")
            if entry.key_findings:
                for f in entry.key_findings[:2]:
                    lines.append(f"  - Finding: {f[:100]}")
        return "\n".join(lines)

    def _format_blackboard(self) -> str:
        return json.dumps(self.blackboard, indent=2, ensure_ascii=False, default=str)

    # ---- 黑板操作 ----

    def bb_set(self, key: str, value: Any):
        self.blackboard[key] = value

    def bb_get(self, key: str, default: Any = None) -> Any:
        return self.blackboard.get(key, default)

    def bb_update(self, data: Dict[str, Any]):
        self.blackboard.update(data)

    def bb_delete(self, key: str):
        self.blackboard.pop(key, None)

    def clear(self):
        self.working_messages.clear()
        self.episodic_entries.clear()
        self._pending_for_summary = []
        self.blackboard.clear()
        self.system_messages.clear()

    @property
    def total_messages(self) -> int:
        return len(self.system_messages) + len(self.working_messages)

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "system_messages": len(self.system_messages),
            "working_messages": len(self.working_messages),
            "episodic_entries": len(self.episodic_entries),
            "pending_for_summary": len(self._pending_for_summary),
            "blackboard_keys": list(self.blackboard.keys()),
        }
