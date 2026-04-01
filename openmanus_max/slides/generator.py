"""
OpenManus-Max Slides Generator
基于 HTML/CSS 的幻灯片生成工具
生成独立的 HTML 文件，可直接在浏览器中演示
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from openmanus_max.core.llm import LLM
from openmanus_max.core.logger import logger
from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


SLIDES_PROMPT = """You are a professional presentation designer. Create slide content based on the user's topic.

Return a JSON array of slides. Each slide has:
- "title": slide title
- "content": HTML content for the slide body (use <ul><li>, <p>, <h3>, <blockquote> etc.)
- "notes": speaker notes (optional)
- "layout": one of "title", "content", "two-column", "image", "quote"

Create {slide_count} slides. Make the content informative, well-structured, and visually balanced.

Output ONLY the JSON array, no other text."""


SLIDE_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #1a1a2e; color: #eee; }}
.slide {{ width: 100vw; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 60px 80px; scroll-snap-align: start; position: relative; }}
.slide:nth-child(odd) {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); }}
.slide:nth-child(even) {{ background: linear-gradient(135deg, #16213e 0%, #0f3460 100%); }}
.slide-number {{ position: absolute; bottom: 20px; right: 30px; font-size: 14px; opacity: 0.5; }}
h1 {{ font-size: 3em; margin-bottom: 20px; background: linear-gradient(90deg, #e94560, #0f3460); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; }}
h2 {{ font-size: 2.2em; margin-bottom: 30px; color: #e94560; text-align: center; }}
.content {{ font-size: 1.3em; line-height: 1.8; max-width: 900px; width: 100%; }}
.content ul {{ list-style: none; padding-left: 0; }}
.content li {{ padding: 8px 0 8px 30px; position: relative; }}
.content li::before {{ content: "▸"; position: absolute; left: 0; color: #e94560; font-weight: bold; }}
.content p {{ margin-bottom: 15px; }}
.content blockquote {{ border-left: 4px solid #e94560; padding: 15px 20px; margin: 20px 0; background: rgba(233,69,96,0.1); border-radius: 0 8px 8px 0; font-style: italic; }}
.content h3 {{ color: #e94560; margin: 20px 0 10px; font-size: 1.4em; }}
.container {{ scroll-snap-type: y mandatory; overflow-y: scroll; height: 100vh; }}
.two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 40px; width: 100%; max-width: 1000px; }}
@media print {{ .slide {{ page-break-after: always; }} }}
</style>
</head>
<body>
<div class="container">
{slides_html}
</div>
<script>
document.addEventListener('keydown', (e) => {{
  const container = document.querySelector('.container');
  if (e.key === 'ArrowDown' || e.key === 'ArrowRight' || e.key === ' ') {{
    e.preventDefault();
    container.scrollBy({{ top: window.innerHeight, behavior: 'smooth' }});
  }} else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {{
    e.preventDefault();
    container.scrollBy({{ top: -window.innerHeight, behavior: 'smooth' }});
  }}
}});
</script>
</body>
</html>"""


class SlidesGenerator(BaseTool):
    name: str = "slides_generate"
    description: str = """Generate a professional HTML slide presentation.
Provide a topic and number of slides. The tool will create a complete, 
self-contained HTML file that can be opened in any browser.
Navigate slides with arrow keys or scroll."""
    parameters: dict = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The topic or outline for the presentation",
            },
            "slide_count": {
                "type": "integer",
                "description": "Number of slides to generate (default: 8)",
                "default": 8,
            },
            "save_path": {
                "type": "string",
                "description": "Path to save the HTML file",
            },
        },
        "required": ["topic"],
    }

    _llm: Optional[LLM] = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, llm: Optional[LLM] = None, **data):
        super().__init__(**data)
        self._llm = llm or LLM()

    async def execute(
        self,
        topic: str,
        slide_count: int = 8,
        save_path: Optional[str] = None,
    ) -> ToolResult:
        try:
            # 1. 用 LLM 生成幻灯片内容
            prompt = SLIDES_PROMPT.format(slide_count=slide_count)
            response = await self._llm.ask(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Create a presentation about: {topic}"},
                ],
                temperature=0.7,
            )

            # 解析 JSON
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            slides_data = json.loads(text)

            # 2. 生成 HTML
            slides_html_parts = []
            for i, slide in enumerate(slides_data):
                title = slide.get("title", f"Slide {i+1}")
                content = slide.get("content", "")
                slide_html = f"""
<div class="slide">
    <h2>{title}</h2>
    <div class="content">
        {content}
    </div>
    <div class="slide-number">{i+1} / {len(slides_data)}</div>
</div>"""
                slides_html_parts.append(slide_html)

            full_html = SLIDE_HTML_TEMPLATE.format(
                title=topic,
                slides_html="\n".join(slides_html_parts),
            )

            # 3. 保存文件
            if not save_path:
                from openmanus_max.core.config import get_config
                workspace = get_config().workspace_dir
                os.makedirs(workspace, exist_ok=True)
                safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in topic)[:50]
                save_path = os.path.join(workspace, f"slides_{safe_name.strip()}.html")

            with open(save_path, "w", encoding="utf-8") as f:
                f.write(full_html)

            return ToolResult(
                output=f"Presentation generated: {save_path}\n"
                       f"Slides: {len(slides_data)}\n"
                       f"Open in browser to view. Use arrow keys to navigate.",
                files=[save_path],
            )

        except json.JSONDecodeError as e:
            return self.fail(f"Failed to parse slide content: {e}")
        except Exception as e:
            return self.fail(f"Slides generation failed: {str(e)}")
