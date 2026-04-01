"""
OpenManus-Max Computer Use Tool
桌面自动化 RPA 工具 - 支持鼠标、键盘、截图等桌面级操作
兼容 Anthropic Computer Use API 规范
"""

from __future__ import annotations

import asyncio
import base64
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


class ComputerUseTool(BaseTool):
    """桌面自动化 RPA 工具"""

    name: str = "computer_use"
    description: str = (
        "Control the computer desktop: move mouse, click, type text, take screenshots, "
        "scroll, and press keyboard shortcuts. Useful for automating GUI applications "
        "that don't have APIs. Requires a display (X11/Wayland) or virtual display (Xvfb)."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform",
                "enum": [
                    "screenshot",
                    "mouse_move",
                    "left_click",
                    "right_click",
                    "double_click",
                    "middle_click",
                    "type_text",
                    "key_press",
                    "scroll_up",
                    "scroll_down",
                    "drag",
                    "get_cursor_position",
                    "get_screen_size",
                ],
            },
            "x": {
                "type": "integer",
                "description": "X coordinate for mouse actions",
                "default": 0,
            },
            "y": {
                "type": "integer",
                "description": "Y coordinate for mouse actions",
                "default": 0,
            },
            "text": {
                "type": "string",
                "description": "Text to type (for type_text action)",
                "default": "",
            },
            "key": {
                "type": "string",
                "description": "Key or key combination to press (e.g., 'Return', 'ctrl+c', 'alt+F4')",
                "default": "",
            },
            "end_x": {
                "type": "integer",
                "description": "End X coordinate for drag action",
                "default": 0,
            },
            "end_y": {
                "type": "integer",
                "description": "End Y coordinate for drag action",
                "default": 0,
            },
            "clicks": {
                "type": "integer",
                "description": "Number of scroll clicks",
                "default": 3,
            },
            "screenshot_path": {
                "type": "string",
                "description": "Path to save screenshot (for screenshot action)",
                "default": "/tmp/screenshot.png",
            },
        },
        "required": ["action"],
    }

    _display: Optional[str] = None

    async def execute(
        self,
        action: str,
        x: int = 0,
        y: int = 0,
        text: str = "",
        key: str = "",
        end_x: int = 0,
        end_y: int = 0,
        clicks: int = 3,
        screenshot_path: str = "/tmp/screenshot.png",
        **kwargs,
    ) -> ToolResult:
        # 检查 xdotool 是否可用
        if action != "screenshot" and not await self._check_tool("xdotool"):
            return ToolResult(error="xdotool not installed. Install with: sudo apt install xdotool")

        try:
            if action == "screenshot":
                return await self._screenshot(screenshot_path)
            elif action == "mouse_move":
                return await self._mouse_move(x, y)
            elif action == "left_click":
                return await self._click(x, y, button=1)
            elif action == "right_click":
                return await self._click(x, y, button=3)
            elif action == "double_click":
                return await self._double_click(x, y)
            elif action == "middle_click":
                return await self._click(x, y, button=2)
            elif action == "type_text":
                return await self._type_text(text)
            elif action == "key_press":
                return await self._key_press(key)
            elif action == "scroll_up":
                return await self._scroll(x, y, direction="up", clicks=clicks)
            elif action == "scroll_down":
                return await self._scroll(x, y, direction="down", clicks=clicks)
            elif action == "drag":
                return await self._drag(x, y, end_x, end_y)
            elif action == "get_cursor_position":
                return await self._get_cursor_position()
            elif action == "get_screen_size":
                return await self._get_screen_size()
            else:
                return ToolResult(error=f"Unknown action: {action}")
        except Exception as e:
            return ToolResult(error=f"Computer use error: {e}")

    async def _run_cmd(self, cmd: List[str], timeout: int = 10) -> Tuple[str, str, int]:
        """运行命令"""
        env = os.environ.copy()
        if self._display:
            env["DISPLAY"] = self._display

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return stdout.decode().strip(), stderr.decode().strip(), proc.returncode
        except asyncio.TimeoutError:
            proc.kill()
            return "", "Command timed out", -1

    async def _check_tool(self, tool: str) -> bool:
        """检查工具是否可用"""
        try:
            stdout, _, rc = await self._run_cmd(["which", tool])
            return rc == 0
        except Exception:
            return False

    async def _screenshot(self, path: str) -> ToolResult:
        """截图"""
        # 尝试多种截图工具
        for tool_cmd in [
            ["scrot", path],
            ["import", "-window", "root", path],
            ["gnome-screenshot", "-f", path],
        ]:
            if await self._check_tool(tool_cmd[0]):
                stdout, stderr, rc = await self._run_cmd(tool_cmd)
                if rc == 0 and os.path.exists(path):
                    # 读取并返回 base64
                    with open(path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    return ToolResult(
                        output=f"Screenshot saved to {path}",
                        base64_image=b64,
                        files=[path],
                    )

        return ToolResult(error="No screenshot tool available. Install scrot: sudo apt install scrot")

    async def _mouse_move(self, x: int, y: int) -> ToolResult:
        stdout, stderr, rc = await self._run_cmd(["xdotool", "mousemove", str(x), str(y)])
        if rc == 0:
            return ToolResult(output=f"Mouse moved to ({x}, {y})")
        return ToolResult(error=f"Mouse move failed: {stderr}")

    async def _click(self, x: int, y: int, button: int = 1) -> ToolResult:
        if x > 0 or y > 0:
            await self._run_cmd(["xdotool", "mousemove", str(x), str(y)])
        stdout, stderr, rc = await self._run_cmd(["xdotool", "click", str(button)])
        if rc == 0:
            btn_name = {1: "left", 2: "middle", 3: "right"}.get(button, str(button))
            return ToolResult(output=f"{btn_name} click at ({x}, {y})")
        return ToolResult(error=f"Click failed: {stderr}")

    async def _double_click(self, x: int, y: int) -> ToolResult:
        if x > 0 or y > 0:
            await self._run_cmd(["xdotool", "mousemove", str(x), str(y)])
        stdout, stderr, rc = await self._run_cmd(["xdotool", "click", "--repeat", "2", "1"])
        if rc == 0:
            return ToolResult(output=f"Double click at ({x}, {y})")
        return ToolResult(error=f"Double click failed: {stderr}")

    async def _type_text(self, text: str) -> ToolResult:
        if not text:
            return ToolResult(error="No text provided")
        stdout, stderr, rc = await self._run_cmd(["xdotool", "type", "--clearmodifiers", text])
        if rc == 0:
            return ToolResult(output=f"Typed: {text[:50]}{'...' if len(text) > 50 else ''}")
        return ToolResult(error=f"Type failed: {stderr}")

    async def _key_press(self, key: str) -> ToolResult:
        if not key:
            return ToolResult(error="No key provided")
        # 转换常见键名
        key = key.replace("ctrl", "ctrl").replace("Ctrl", "ctrl")
        key = key.replace("alt", "alt").replace("Alt", "alt")
        key = key.replace("shift", "shift").replace("Shift", "shift")
        key = key.replace("enter", "Return").replace("Enter", "Return")
        key = key.replace("tab", "Tab").replace("Tab", "Tab")
        key = key.replace("esc", "Escape").replace("Esc", "Escape")

        stdout, stderr, rc = await self._run_cmd(["xdotool", "key", key])
        if rc == 0:
            return ToolResult(output=f"Key pressed: {key}")
        return ToolResult(error=f"Key press failed: {stderr}")

    async def _scroll(self, x: int, y: int, direction: str, clicks: int) -> ToolResult:
        if x > 0 or y > 0:
            await self._run_cmd(["xdotool", "mousemove", str(x), str(y)])
        button = "4" if direction == "up" else "5"
        stdout, stderr, rc = await self._run_cmd(
            ["xdotool", "click", "--repeat", str(clicks), button]
        )
        if rc == 0:
            return ToolResult(output=f"Scrolled {direction} {clicks} clicks at ({x}, {y})")
        return ToolResult(error=f"Scroll failed: {stderr}")

    async def _drag(self, x: int, y: int, end_x: int, end_y: int) -> ToolResult:
        await self._run_cmd(["xdotool", "mousemove", str(x), str(y)])
        await self._run_cmd(["xdotool", "mousedown", "1"])
        await asyncio.sleep(0.1)
        await self._run_cmd(["xdotool", "mousemove", str(end_x), str(end_y)])
        await asyncio.sleep(0.1)
        stdout, stderr, rc = await self._run_cmd(["xdotool", "mouseup", "1"])
        if rc == 0:
            return ToolResult(output=f"Dragged from ({x},{y}) to ({end_x},{end_y})")
        return ToolResult(error=f"Drag failed: {stderr}")

    async def _get_cursor_position(self) -> ToolResult:
        stdout, stderr, rc = await self._run_cmd(["xdotool", "getmouselocation"])
        if rc == 0:
            return ToolResult(output=f"Cursor position: {stdout}")
        return ToolResult(error=f"Get cursor position failed: {stderr}")

    async def _get_screen_size(self) -> ToolResult:
        stdout, stderr, rc = await self._run_cmd(["xdotool", "getdisplaygeometry"])
        if rc == 0:
            return ToolResult(output=f"Screen size: {stdout}")
        return ToolResult(error=f"Get screen size failed: {stderr}")
