"""
OpenManus-Max File Editor Tool
文件读写与编辑工具，支持 view/create/edit/append/replace
"""

from __future__ import annotations

import os
from typing import Optional

from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


class FileEditor(BaseTool):
    name: str = "file_editor"
    description: str = """File operations tool supporting view, create, write, append, and str_replace.
- view: Read file content (with optional line range)
- create: Create a new file with content
- write: Overwrite entire file content
- append: Append content to file
- str_replace: Replace specific text in file
- list_dir: List directory contents"""
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["view", "create", "write", "append", "str_replace", "list_dir"],
                "description": "The file operation to perform",
            },
            "path": {
                "type": "string",
                "description": "Absolute file or directory path",
            },
            "content": {
                "type": "string",
                "description": "Content for create/write/append operations",
            },
            "old_str": {
                "type": "string",
                "description": "String to find (for str_replace)",
            },
            "new_str": {
                "type": "string",
                "description": "Replacement string (for str_replace)",
            },
            "start_line": {
                "type": "integer",
                "description": "Start line number for view (1-indexed)",
            },
            "end_line": {
                "type": "integer",
                "description": "End line number for view (inclusive)",
            },
        },
        "required": ["command", "path"],
    }

    async def execute(
        self,
        command: str,
        path: str,
        content: Optional[str] = None,
        old_str: Optional[str] = None,
        new_str: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> ToolResult:
        path = os.path.expanduser(path)

        if command == "view":
            return self._view(path, start_line, end_line)
        elif command == "create":
            return self._create(path, content or "")
        elif command == "write":
            return self._write(path, content or "")
        elif command == "append":
            return self._append(path, content or "")
        elif command == "str_replace":
            return self._str_replace(path, old_str or "", new_str or "")
        elif command == "list_dir":
            return self._list_dir(path)
        else:
            return self.fail(f"Unknown command: {command}")

    def _view(self, path: str, start: Optional[int], end: Optional[int]) -> ToolResult:
        if not os.path.exists(path):
            return self.fail(f"File not found: {path}")
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            total = len(lines)
            if start is not None or end is not None:
                s = max(1, start or 1) - 1
                e = min(total, end or total)
                selected = lines[s:e]
                numbered = [f"{i+s+1:4d} | {l}" for i, l in enumerate(selected)]
                header = f"File: {path} (lines {s+1}-{e} of {total})\n"
            else:
                if total > 300:
                    selected = lines[:300]
                    numbered = [f"{i+1:4d} | {l}" for i, l in enumerate(selected)]
                    header = f"File: {path} ({total} lines, showing first 300)\n"
                else:
                    numbered = [f"{i+1:4d} | {l}" for i, l in enumerate(lines)]
                    header = f"File: {path} ({total} lines)\n"
            return self.success(header + "".join(numbered))
        except Exception as e:
            return self.fail(f"Error reading {path}: {e}")

    def _create(self, path: str, content: str) -> ToolResult:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return self.success(f"Created file: {path} ({len(content)} chars)")
        except Exception as e:
            return self.fail(f"Error creating {path}: {e}")

    def _write(self, path: str, content: str) -> ToolResult:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return self.success(f"Written to: {path} ({len(content)} chars)")
        except Exception as e:
            return self.fail(f"Error writing {path}: {e}")

    def _append(self, path: str, content: str) -> ToolResult:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
            return self.success(f"Appended to: {path} ({len(content)} chars)")
        except Exception as e:
            return self.fail(f"Error appending to {path}: {e}")

    def _str_replace(self, path: str, old_str: str, new_str: str) -> ToolResult:
        if not os.path.exists(path):
            return self.fail(f"File not found: {path}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if old_str not in content:
                return self.fail(f"String not found in {path}: '{old_str[:80]}...'")
            count = content.count(old_str)
            new_content = content.replace(old_str, new_str)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return self.success(f"Replaced {count} occurrence(s) in {path}")
        except Exception as e:
            return self.fail(f"Error replacing in {path}: {e}")

    def _list_dir(self, path: str) -> ToolResult:
        if not os.path.exists(path):
            return self.fail(f"Path not found: {path}")
        try:
            entries = sorted(os.listdir(path))
            lines = []
            for e in entries:
                full = os.path.join(path, e)
                if os.path.isdir(full):
                    lines.append(f"  [DIR]  {e}/")
                else:
                    size = os.path.getsize(full)
                    lines.append(f"  [FILE] {e} ({size} bytes)")
            header = f"Directory: {path} ({len(entries)} items)\n"
            return self.success(header + "\n".join(lines))
        except Exception as e:
            return self.fail(f"Error listing {path}: {e}")
