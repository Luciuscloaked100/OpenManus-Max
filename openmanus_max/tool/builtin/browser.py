"""
OpenManus-Max Browser Tool
基于 Playwright 的浏览器自动化工具
"""

from __future__ import annotations

import asyncio
from typing import Optional

from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


class BrowserTool(BaseTool):
    name: str = "browser"
    description: str = """Browser automation tool for web interaction.
Supports: navigate, get_content, click, type_text, screenshot, scroll, go_back.
Use this to browse websites, fill forms, extract content, and interact with web pages."""
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "navigate", "get_content", "click", "type_text",
                    "screenshot", "scroll", "go_back", "get_links",
                ],
                "description": "Browser action to perform",
            },
            "url": {
                "type": "string",
                "description": "URL to navigate to (for navigate action)",
            },
            "selector": {
                "type": "string",
                "description": "CSS selector for click/type actions",
            },
            "text": {
                "type": "string",
                "description": "Text to type (for type_text action)",
            },
            "direction": {
                "type": "string",
                "enum": ["up", "down"],
                "description": "Scroll direction",
                "default": "down",
            },
            "save_path": {
                "type": "string",
                "description": "Path to save screenshot",
            },
        },
        "required": ["action"],
    }

    _browser: object = None
    _page: object = None

    class Config:
        arbitrary_types_allowed = True

    async def _ensure_browser(self):
        if self._page is not None:
            return
        try:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
            self._page = await self._browser.new_page()
            await self._page.set_viewport_size({"width": 1280, "height": 720})
        except ImportError:
            raise ImportError(
                "playwright not installed. Run: pip install playwright && playwright install chromium"
            )

    async def execute(
        self,
        action: str,
        url: Optional[str] = None,
        selector: Optional[str] = None,
        text: Optional[str] = None,
        direction: str = "down",
        save_path: Optional[str] = None,
    ) -> ToolResult:
        try:
            await self._ensure_browser()
        except ImportError as e:
            return self.fail(str(e))

        try:
            if action == "navigate":
                if not url:
                    return self.fail("URL is required for navigate action")
                await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
                title = await self._page.title()
                return self.success(f"Navigated to: {url}\nTitle: {title}")

            elif action == "get_content":
                content = await self._page.evaluate("""
                    () => {
                        const sel = document.querySelector('article') || document.querySelector('main') || document.body;
                        return sel ? sel.innerText.substring(0, 8000) : '';
                    }
                """)
                url = self._page.url
                return self.success(f"URL: {url}\nContent:\n{content}")

            elif action == "click":
                if not selector:
                    return self.fail("Selector is required for click action")
                await self._page.click(selector, timeout=5000)
                await self._page.wait_for_load_state("domcontentloaded")
                return self.success(f"Clicked: {selector}")

            elif action == "type_text":
                if not selector or text is None:
                    return self.fail("Selector and text are required for type_text")
                await self._page.fill(selector, text, timeout=5000)
                return self.success(f"Typed text into: {selector}")

            elif action == "screenshot":
                path = save_path or "/tmp/screenshot.png"
                await self._page.screenshot(path=path, full_page=False)
                return ToolResult(output=f"Screenshot saved: {path}", files=[path])

            elif action == "scroll":
                delta = -500 if direction == "up" else 500
                await self._page.mouse.wheel(0, delta)
                await asyncio.sleep(0.5)
                return self.success(f"Scrolled {direction}")

            elif action == "go_back":
                await self._page.go_back(wait_until="domcontentloaded")
                return self.success(f"Navigated back to: {self._page.url}")

            elif action == "get_links":
                links = await self._page.evaluate("""
                    () => {
                        return Array.from(document.querySelectorAll('a[href]'))
                            .slice(0, 50)
                            .map(a => ({text: a.innerText.trim().substring(0, 80), href: a.href}))
                            .filter(l => l.text && l.href.startsWith('http'));
                    }
                """)
                lines = [f"Links on page ({len(links)}):\n"]
                for i, l in enumerate(links, 1):
                    lines.append(f"  {i}. [{l['text']}]({l['href']})")
                return self.success("\n".join(lines))

            else:
                return self.fail(f"Unknown action: {action}")

        except Exception as e:
            return self.fail(f"Browser error: {str(e)}")

    async def close(self):
        if self._browser:
            await self._browser.close()
        if hasattr(self, '_pw') and self._pw:
            await self._pw.stop()
        self._browser = None
        self._page = None
