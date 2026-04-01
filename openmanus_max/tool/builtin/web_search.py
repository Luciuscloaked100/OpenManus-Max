"""
OpenManus-Max Web Search Tool
多引擎搜索工具 - 支持 DuckDuckGo（主）+ 回退引擎
支持文本搜索、图片搜索、新闻搜索
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from openmanus_max.core.logger import logger
from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


class WebSearch(BaseTool):
    name: str = "web_search"
    description: str = (
        "Search the web for information. Supports multiple search types: "
        "'text' for general web search, 'images' for image search, "
        "'news' for recent news. Uses DuckDuckGo with automatic fallback. "
        "Returns results with titles, URLs, and snippets."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "search_type": {
                "type": "string",
                "description": "Type of search: text, images, news",
                "enum": ["text", "images", "news"],
                "default": "text",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default: 8)",
                "default": 8,
            },
            "region": {
                "type": "string",
                "description": "Region for results: wt-wt (worldwide), us-en, cn-zh, etc.",
                "default": "wt-wt",
            },
            "time_range": {
                "type": "string",
                "description": "Time filter: d (day), w (week), m (month), y (year), or empty for all",
                "default": "",
            },
        },
        "required": ["query"],
    }

    async def execute(
        self,
        query: str,
        search_type: str = "text",
        max_results: int = 8,
        region: str = "wt-wt",
        time_range: str = "",
        **kwargs,
    ) -> ToolResult:
        # 尝试 DuckDuckGo
        result = await self._search_duckduckgo(query, search_type, max_results, region, time_range)
        if result.success:
            return result

        # 回退到 httpx 直接搜索
        logger.warning(f"DuckDuckGo failed, trying fallback for: {query}")
        fallback = await self._search_fallback(query, max_results)
        if fallback.success:
            return fallback

        return ToolResult(error=f"All search engines failed for: {query}")

    async def _search_duckduckgo(
        self, query: str, search_type: str, max_results: int, region: str, time_range: str
    ) -> ToolResult:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return ToolResult(error="duckduckgo-search not installed")

        try:
            results = await asyncio.to_thread(
                self._ddg_sync, query, search_type, max_results, region, time_range
            )
            if not results:
                return ToolResult(output=f"No results found for: {query}")

            return ToolResult(output=self._format_results(query, search_type, results))
        except Exception as e:
            return ToolResult(error=f"DuckDuckGo error: {e}")

    def _ddg_sync(
        self, query: str, search_type: str, max_results: int, region: str, time_range: str
    ) -> List[dict]:
        from duckduckgo_search import DDGS

        kwargs = {}
        if time_range:
            kwargs["timelimit"] = time_range

        with DDGS() as ddgs:
            if search_type == "text":
                return list(ddgs.text(query, max_results=max_results, region=region, **kwargs))
            elif search_type == "images":
                return list(ddgs.images(query, max_results=max_results, region=region, **kwargs))
            elif search_type == "news":
                return list(ddgs.news(query, max_results=max_results, region=region, **kwargs))
            else:
                return list(ddgs.text(query, max_results=max_results, region=region, **kwargs))

    async def _search_fallback(self, query: str, max_results: int) -> ToolResult:
        """回退搜索 - 使用 httpx 直接请求搜索引擎"""
        try:
            import httpx

            # 使用 DuckDuckGo HTML 版本作为回退
            url = "https://html.duckduckgo.com/html/"
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, data={"q": query})
                resp.raise_for_status()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for r in soup.select(".result")[:max_results]:
                title_el = r.select_one(".result__title a")
                snippet_el = r.select_one(".result__snippet")
                if title_el:
                    results.append({
                        "title": title_el.get_text(strip=True),
                        "href": title_el.get("href", ""),
                        "body": snippet_el.get_text(strip=True) if snippet_el else "",
                    })

            if results:
                return ToolResult(output=self._format_results(query, "text", results))
            return ToolResult(error="Fallback search returned no results")
        except Exception as e:
            return ToolResult(error=f"Fallback search error: {e}")

    def _format_results(self, query: str, search_type: str, results: List[dict]) -> str:
        lines = [f"Search results for: {query} (type: {search_type})\n"]

        for i, r in enumerate(results, 1):
            if search_type == "images":
                lines.append(f"{i}. {r.get('title', 'N/A')}")
                lines.append(f"   Image URL: {r.get('image', r.get('url', 'N/A'))}")
                lines.append(f"   Source: {r.get('source', r.get('url', 'N/A'))}")
                lines.append(f"   Size: {r.get('width', '?')}x{r.get('height', '?')}")
            elif search_type == "news":
                lines.append(f"{i}. {r.get('title', 'N/A')}")
                lines.append(f"   URL: {r.get('url', r.get('href', 'N/A'))}")
                lines.append(f"   Source: {r.get('source', 'N/A')}")
                lines.append(f"   Date: {r.get('date', 'N/A')}")
                lines.append(f"   {r.get('body', r.get('snippet', ''))}")
            else:
                lines.append(f"{i}. {r.get('title', 'N/A')}")
                lines.append(f"   URL: {r.get('href', r.get('link', r.get('url', 'N/A')))}")
                lines.append(f"   {r.get('body', r.get('snippet', ''))}")
            lines.append("")

        return "\n".join(lines)
