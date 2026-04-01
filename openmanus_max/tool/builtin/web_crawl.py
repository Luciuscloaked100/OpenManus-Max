"""
OpenManus-Max Web Crawl Tool
网页深度内容提取工具 - 支持 Markdown 转换、正文提取、结构化数据提取
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional
from urllib.parse import urljoin, urlparse

from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


class WebCrawl(BaseTool):
    """网页深度内容提取工具"""

    name: str = "web_crawl"
    description: str = (
        "Crawl and extract content from web pages. Supports multiple extraction modes: "
        "'text' for clean text, 'markdown' for Markdown-formatted content, "
        "'links' for all links on the page, 'structured' for metadata and main content. "
        "More powerful than basic browser text extraction."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to crawl",
            },
            "mode": {
                "type": "string",
                "description": "Extraction mode: text, markdown, links, structured, full",
                "enum": ["text", "markdown", "links", "structured", "full"],
                "default": "markdown",
            },
            "max_length": {
                "type": "integer",
                "description": "Maximum content length in characters",
                "default": 10000,
            },
            "selector": {
                "type": "string",
                "description": "Optional CSS selector to extract specific content",
                "default": "",
            },
        },
        "required": ["url"],
    }

    async def execute(
        self,
        url: str,
        mode: str = "markdown",
        max_length: int = 10000,
        selector: str = "",
        **kwargs,
    ) -> ToolResult:
        try:
            import httpx
            from bs4 import BeautifulSoup
        except ImportError:
            return ToolResult(error="httpx and beautifulsoup4 required. pip install httpx beautifulsoup4")

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
            }

            async with httpx.AsyncClient(
                follow_redirects=True, timeout=30.0, headers=headers
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            # 如果指定了 CSS 选择器
            if selector:
                elements = soup.select(selector)
                if not elements:
                    return ToolResult(error=f"No elements found for selector: {selector}")
                # 创建新的 soup 只包含选中的元素
                from bs4 import Tag
                new_soup = BeautifulSoup("<div></div>", "html.parser")
                container = new_soup.div
                for el in elements:
                    container.append(el.__copy__() if hasattr(el, '__copy__') else el)
                soup = new_soup

            if mode == "text":
                result = self._extract_text(soup, max_length)
            elif mode == "markdown":
                result = self._extract_markdown(soup, url, max_length)
            elif mode == "links":
                result = self._extract_links(soup, url, max_length)
            elif mode == "structured":
                result = self._extract_structured(soup, url, max_length)
            elif mode == "full":
                result = self._extract_full(soup, url, max_length)
            else:
                result = self._extract_text(soup, max_length)

            return ToolResult(output=result)

        except httpx.HTTPStatusError as e:
            return ToolResult(error=f"HTTP {e.response.status_code}: {url}")
        except Exception as e:
            return ToolResult(error=f"Crawl failed: {e}")

    def _clean_soup(self, soup):
        """移除无用元素"""
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
            tag.decompose()
        return soup

    def _extract_text(self, soup, max_length: int) -> str:
        soup = self._clean_soup(soup)
        text = soup.get_text(separator="\n", strip=True)
        # 清理多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_length]

    def _extract_markdown(self, soup, base_url: str, max_length: int) -> str:
        soup = self._clean_soup(soup)
        lines = []

        # 提取标题
        title = soup.find("title")
        if title:
            lines.append(f"# {title.get_text(strip=True)}\n")

        # 查找主要内容区域
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find(attrs={"role": "main"})
            or soup.find("div", class_=re.compile(r"content|article|post|entry", re.I))
            or soup.body
            or soup
        )

        if main:
            lines.append(self._tag_to_markdown(main, base_url))

        result = "\n".join(lines)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result[:max_length]

    def _tag_to_markdown(self, tag, base_url: str) -> str:
        """递归将 HTML 标签转换为 Markdown"""
        from bs4 import NavigableString, Tag

        parts = []
        for child in tag.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    parts.append(text)
            elif isinstance(child, Tag):
                name = child.name
                if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    level = int(name[1])
                    text = child.get_text(strip=True)
                    if text:
                        parts.append(f"\n{'#' * level} {text}\n")
                elif name == "p":
                    text = child.get_text(strip=True)
                    if text:
                        parts.append(f"\n{text}\n")
                elif name == "a":
                    text = child.get_text(strip=True)
                    href = child.get("href", "")
                    if href and text:
                        full_url = urljoin(base_url, href) if not href.startswith("http") else href
                        parts.append(f"[{text}]({full_url})")
                    elif text:
                        parts.append(text)
                elif name == "img":
                    alt = child.get("alt", "image")
                    src = child.get("src", "")
                    if src:
                        full_url = urljoin(base_url, src) if not src.startswith("http") else src
                        parts.append(f"![{alt}]({full_url})")
                elif name in ("ul", "ol"):
                    items = child.find_all("li", recursive=False)
                    for i, li in enumerate(items):
                        prefix = f"{i+1}." if name == "ol" else "-"
                        text = li.get_text(strip=True)
                        if text:
                            parts.append(f"{prefix} {text}")
                    parts.append("")
                elif name == "pre" or name == "code":
                    code = child.get_text()
                    if "\n" in code:
                        parts.append(f"\n```\n{code}\n```\n")
                    else:
                        parts.append(f"`{code.strip()}`")
                elif name == "blockquote":
                    text = child.get_text(strip=True)
                    if text:
                        parts.append(f"\n> {text}\n")
                elif name == "table":
                    parts.append(self._table_to_markdown(child))
                elif name in ("strong", "b"):
                    text = child.get_text(strip=True)
                    if text:
                        parts.append(f"**{text}**")
                elif name in ("em", "i"):
                    text = child.get_text(strip=True)
                    if text:
                        parts.append(f"*{text}*")
                elif name == "br":
                    parts.append("\n")
                elif name == "hr":
                    parts.append("\n---\n")
                else:
                    # 递归处理其他标签
                    inner = self._tag_to_markdown(child, base_url)
                    if inner.strip():
                        parts.append(inner)

        return " ".join(parts)

    def _table_to_markdown(self, table) -> str:
        """将 HTML 表格转换为 Markdown 表格"""
        rows = table.find_all("tr")
        if not rows:
            return ""

        md_rows = []
        for row in rows:
            cells = row.find_all(["th", "td"])
            md_cells = [cell.get_text(strip=True).replace("|", "\\|") for cell in cells]
            md_rows.append("| " + " | ".join(md_cells) + " |")

        if len(md_rows) > 0:
            # 添加分隔行
            num_cols = md_rows[0].count("|") - 1
            separator = "| " + " | ".join(["---"] * max(num_cols, 1)) + " |"
            md_rows.insert(1, separator)

        return "\n" + "\n".join(md_rows) + "\n"

    def _extract_links(self, soup, base_url: str, max_length: int) -> str:
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if href.startswith("#") or href.startswith("javascript:"):
                continue
            full_url = urljoin(base_url, href) if not href.startswith("http") else href
            links.append(f"- [{text or 'link'}]({full_url})")

        result = f"Found {len(links)} links:\n\n" + "\n".join(links)
        return result[:max_length]

    def _extract_structured(self, soup, base_url: str, max_length: int) -> str:
        """提取结构化信息"""
        import json

        data = {
            "url": base_url,
            "title": "",
            "description": "",
            "headings": [],
            "main_text": "",
            "links_count": 0,
            "images_count": 0,
        }

        title = soup.find("title")
        if title:
            data["title"] = title.get_text(strip=True)

        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            data["description"] = meta_desc.get("content", "")

        for h in soup.find_all(["h1", "h2", "h3"]):
            text = h.get_text(strip=True)
            if text:
                data["headings"].append({"level": h.name, "text": text})

        data["links_count"] = len(soup.find_all("a", href=True))
        data["images_count"] = len(soup.find_all("img"))

        soup_clean = self._clean_soup(soup)
        data["main_text"] = soup_clean.get_text(separator=" ", strip=True)[:3000]

        return json.dumps(data, indent=2, ensure_ascii=False)[:max_length]

    def _extract_full(self, soup, base_url: str, max_length: int) -> str:
        """完整提取：Markdown + 链接 + 结构化"""
        md = self._extract_markdown(soup, base_url, max_length // 2)
        links = self._extract_links(soup, base_url, max_length // 4)
        return f"{md}\n\n---\n\n{links}"[:max_length]
