"""
OpenManus-Max Media Generator
多媒体生成工具：图像生成、TTS 语音合成
支持 OpenAI DALL-E 和 TTS API
"""

from __future__ import annotations

import os
from typing import Optional

from openai import AsyncOpenAI

from openmanus_max.core.config import get_config
from openmanus_max.core.logger import logger
from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


class ImageGenerator(BaseTool):
    name: str = "image_generate"
    description: str = """Generate images from text descriptions using AI (DALL-E).
Provide a detailed description of the image you want to create.
Returns the path to the saved image file."""
    parameters: dict = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Detailed description of the image to generate",
            },
            "size": {
                "type": "string",
                "enum": ["1024x1024", "1792x1024", "1024x1792"],
                "description": "Image size (default: 1024x1024)",
                "default": "1024x1024",
            },
            "save_path": {
                "type": "string",
                "description": "Path to save the image (optional, auto-generated if not provided)",
            },
        },
        "required": ["prompt"],
    }

    async def execute(
        self,
        prompt: str,
        size: str = "1024x1024",
        save_path: Optional[str] = None,
    ) -> ToolResult:
        config = get_config()
        api_key = config.media.image_api_key or config.llm.api_key
        if not api_key:
            return self.fail("No API key configured for image generation")

        try:
            client = AsyncOpenAI(api_key=api_key, base_url=config.llm.base_url)
            response = await client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                n=1,
                response_format="url",
            )

            image_url = response.data[0].url
            revised_prompt = response.data[0].revised_prompt or prompt

            # 下载图片
            if not save_path:
                workspace = config.workspace_dir
                os.makedirs(workspace, exist_ok=True)
                save_path = os.path.join(workspace, f"generated_image_{os.getpid()}.png")

            import httpx
            async with httpx.AsyncClient() as http:
                img_response = await http.get(image_url)
                with open(save_path, "wb") as f:
                    f.write(img_response.content)

            return ToolResult(
                output=f"Image generated and saved to: {save_path}\nRevised prompt: {revised_prompt}",
                files=[save_path],
            )

        except Exception as e:
            return self.fail(f"Image generation failed: {str(e)}")


class TTSGenerator(BaseTool):
    name: str = "text_to_speech"
    description: str = """Convert text to speech audio using AI (OpenAI TTS).
Returns the path to the saved audio file."""
    parameters: dict = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to convert to speech",
            },
            "voice": {
                "type": "string",
                "enum": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
                "description": "Voice to use (default: alloy)",
                "default": "alloy",
            },
            "save_path": {
                "type": "string",
                "description": "Path to save the audio file",
            },
        },
        "required": ["text"],
    }

    async def execute(
        self,
        text: str,
        voice: str = "alloy",
        save_path: Optional[str] = None,
    ) -> ToolResult:
        config = get_config()
        api_key = config.media.tts_api_key or config.llm.api_key
        if not api_key:
            return self.fail("No API key configured for TTS")

        try:
            client = AsyncOpenAI(api_key=api_key, base_url=config.llm.base_url)
            response = await client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
            )

            if not save_path:
                workspace = config.workspace_dir
                os.makedirs(workspace, exist_ok=True)
                save_path = os.path.join(workspace, f"tts_output_{os.getpid()}.mp3")

            response.stream_to_file(save_path)

            return ToolResult(
                output=f"Audio generated and saved to: {save_path}\nVoice: {voice}, Length: {len(text)} chars",
                files=[save_path],
            )

        except Exception as e:
            return self.fail(f"TTS generation failed: {str(e)}")
