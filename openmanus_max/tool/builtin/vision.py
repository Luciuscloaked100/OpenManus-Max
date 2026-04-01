"""
OpenManus-Max Vision Tool
多模态视觉理解工具 - 支持图像分析、PDF 页面理解、截图分析
"""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional

from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


class VisionTool(BaseTool):
    """多模态视觉理解工具"""

    name: str = "vision_analyze"
    description: str = (
        "Analyze images and visual content using LLM vision capabilities. "
        "Supports local image files (PNG, JPG, GIF, WebP), PDF pages, "
        "and image URLs. Provide a prompt describing what to analyze."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "What to analyze or extract from the image",
            },
            "image_path": {
                "type": "string",
                "description": "Local path to an image file (PNG, JPG, GIF, WebP, PDF)",
                "default": "",
            },
            "image_url": {
                "type": "string",
                "description": "URL of the image to analyze",
                "default": "",
            },
            "pdf_page": {
                "type": "integer",
                "description": "For PDF files, which page to analyze (1-indexed, default: 1)",
                "default": 1,
            },
        },
        "required": ["prompt"],
    }

    _llm: Any = None

    class Config:
        arbitrary_types_allowed = True

    def set_llm(self, llm):
        self._llm = llm

    async def execute(
        self,
        prompt: str,
        image_path: str = "",
        image_url: str = "",
        pdf_page: int = 1,
        **kwargs,
    ) -> ToolResult:
        if not self._llm:
            return ToolResult(error="Vision tool requires LLM to be configured. Call set_llm() first.")

        if not image_path and not image_url:
            return ToolResult(error="Either 'image_path' or 'image_url' must be provided.")

        try:
            if image_url:
                result = await self._llm.ask_vision_url(prompt=prompt, image_url=image_url)
                return ToolResult(output=result)

            if image_path:
                if not os.path.exists(image_path):
                    return ToolResult(error=f"File not found: {image_path}")

                ext = os.path.splitext(image_path)[1].lower()

                if ext == ".pdf":
                    return await self._analyze_pdf(prompt, image_path, pdf_page)
                elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
                    return await self._analyze_image(prompt, image_path, ext)
                else:
                    return ToolResult(error=f"Unsupported file type: {ext}")

        except Exception as e:
            return ToolResult(error=f"Vision analysis failed: {e}")

    async def _analyze_image(self, prompt: str, path: str, ext: str) -> ToolResult:
        """分析图像文件"""
        with open(path, "rb") as f:
            image_data = f.read()

        image_type_map = {
            ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg",
            ".gif": "gif", ".webp": "webp", ".bmp": "bmp",
        }
        image_type = image_type_map.get(ext, "png")

        result = await self._llm.ask_vision(
            prompt=prompt,
            image_data=image_data,
            image_type=image_type,
        )
        return ToolResult(output=result)

    async def _analyze_pdf(self, prompt: str, path: str, page: int) -> ToolResult:
        """分析 PDF 页面（转为图像后分析）"""
        try:
            from pdf2image import convert_from_path
        except ImportError:
            # 回退：尝试用 pdftotext 提取文本
            return await self._pdf_text_fallback(prompt, path, page)

        try:
            images = convert_from_path(path, first_page=page, last_page=page, dpi=200)
            if not images:
                return ToolResult(error=f"Could not render PDF page {page}")

            import io
            buf = io.BytesIO()
            images[0].save(buf, format="PNG")
            image_data = buf.getvalue()

            result = await self._llm.ask_vision(
                prompt=f"This is page {page} of a PDF document. {prompt}",
                image_data=image_data,
                image_type="png",
            )
            return ToolResult(output=result)
        except Exception as e:
            return await self._pdf_text_fallback(prompt, path, page)

    async def _pdf_text_fallback(self, prompt: str, path: str, page: int) -> ToolResult:
        """PDF 文本回退方案"""
        import subprocess
        try:
            result = subprocess.run(
                ["pdftotext", "-f", str(page), "-l", str(page), path, "-"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                text = result.stdout.strip()[:5000]
                llm_result = await self._llm.ask(
                    messages=[{"role": "user", "content": f"Based on this PDF text:\n\n{text}\n\n{prompt}"}]
                )
                return ToolResult(output=f"[Text extraction fallback]\n{llm_result}")
            return ToolResult(error="Could not extract PDF content")
        except Exception as e:
            return ToolResult(error=f"PDF fallback failed: {e}")
