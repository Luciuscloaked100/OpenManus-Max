"""
OpenManus-Max LLM Client
统一的大模型调用封装，支持普通对话、Tool Calling、流式输出、多模态 Vision
"""

from __future__ import annotations

import base64
import json
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage

from openmanus_max.core.config import LLMConfig, get_config
from openmanus_max.core.logger import logger
from openmanus_max.core.schema import Message


class LLM:
    """LLM 客户端封装"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_config().llm
        self.client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    async def ask(
        self,
        messages: List[Union[Dict, Message]],
        system_msgs: Optional[List[Union[Dict, Message]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """普通对话"""
        formatted = self._format_messages(messages, system_msgs)
        params = {
            "model": self.config.model,
            "messages": formatted,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }

        try:
            response = await self.client.chat.completions.create(**params)
            if response.usage:
                self.total_prompt_tokens += response.usage.prompt_tokens
                self.total_completion_tokens += response.usage.completion_tokens
            content = response.choices[0].message.content
            return content or ""
        except Exception as e:
            logger.error(f"LLM ask error: {e}")
            raise

    async def ask_stream(
        self,
        messages: List[Union[Dict, Message]],
        system_msgs: Optional[List[Union[Dict, Message]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> str:
        """流式对话 - 逐 Token 返回"""
        formatted = self._format_messages(messages, system_msgs)
        params = {
            "model": self.config.model,
            "messages": formatted,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "stream": True,
        }

        try:
            full_content = ""
            stream = await self.client.chat.completions.create(**params)
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_content += token
                    if on_token:
                        on_token(token)
            return full_content
        except Exception as e:
            logger.error(f"LLM ask_stream error: {e}")
            raise

    async def ask_stream_iter(
        self,
        messages: List[Union[Dict, Message]],
        system_msgs: Optional[List[Union[Dict, Message]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """流式对话 - 返回异步迭代器"""
        formatted = self._format_messages(messages, system_msgs)
        params = {
            "model": self.config.model,
            "messages": formatted,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "stream": True,
        }

        stream = await self.client.chat.completions.create(**params)
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def ask_tool(
        self,
        messages: List[Union[Dict, Message]],
        tools: List[Dict],
        system_msgs: Optional[List[Union[Dict, Message]]] = None,
        tool_choice: str = "auto",
        temperature: Optional[float] = None,
    ) -> Optional[ChatCompletionMessage]:
        """工具调用"""
        formatted = self._format_messages(messages, system_msgs)
        params = {
            "model": self.config.model,
            "messages": formatted,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        try:
            response = await self.client.chat.completions.create(**params)
            if response.usage:
                self.total_prompt_tokens += response.usage.prompt_tokens
                self.total_completion_tokens += response.usage.completion_tokens
            if response.choices and response.choices[0].message:
                return response.choices[0].message
            return None
        except Exception as e:
            logger.error(f"LLM ask_tool error: {e}")
            raise

    async def ask_vision(
        self,
        prompt: str,
        image_data: Union[str, bytes],
        image_type: str = "png",
        system_msgs: Optional[List[Union[Dict, Message]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """多模态视觉分析 - 支持图像理解"""
        # 如果是 bytes，转为 base64
        if isinstance(image_data, bytes):
            b64 = base64.b64encode(image_data).decode("utf-8")
        else:
            b64 = image_data

        # 构建 vision 消息
        vision_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{image_type};base64,{b64}"
                    },
                },
            ],
        }

        formatted = []
        if system_msgs:
            for m in system_msgs:
                formatted.append(m.to_dict() if isinstance(m, Message) else m)
        formatted.append(vision_message)

        params = {
            "model": self.config.model,
            "messages": formatted,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }

        try:
            response = await self.client.chat.completions.create(**params)
            if response.usage:
                self.total_prompt_tokens += response.usage.prompt_tokens
                self.total_completion_tokens += response.usage.completion_tokens
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM ask_vision error: {e}")
            raise

    async def ask_vision_url(
        self,
        prompt: str,
        image_url: str,
        system_msgs: Optional[List[Union[Dict, Message]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """多模态视觉分析 - 支持图像 URL"""
        vision_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }

        formatted = []
        if system_msgs:
            for m in system_msgs:
                formatted.append(m.to_dict() if isinstance(m, Message) else m)
        formatted.append(vision_message)

        params = {
            "model": self.config.model,
            "messages": formatted,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }

        try:
            response = await self.client.chat.completions.create(**params)
            if response.usage:
                self.total_prompt_tokens += response.usage.prompt_tokens
                self.total_completion_tokens += response.usage.completion_tokens
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM ask_vision_url error: {e}")
            raise

    def _format_messages(
        self,
        messages: List[Union[Dict, Message]],
        system_msgs: Optional[List[Union[Dict, Message]]] = None,
    ) -> List[Dict]:
        result = []
        if system_msgs:
            for m in system_msgs:
                result.append(m.to_dict() if isinstance(m, Message) else m)
        for m in messages:
            result.append(m.to_dict() if isinstance(m, Message) else m)
        return result

    @property
    def token_usage(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
        }
