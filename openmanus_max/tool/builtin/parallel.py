"""
OpenManus-Max Parallel Processing Tool
Map-Reduce 风格的并行子任务处理
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from openmanus_max.core.llm import LLM
from openmanus_max.core.logger import logger
from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


class ParallelMap(BaseTool):
    name: str = "parallel_map"
    description: str = """Execute the same prompt template across multiple inputs in parallel.
Like Pool.map() in Python multiprocessing. Each input is processed independently.
Use this for batch processing, parallel research, or any task that can be split into independent subtasks.
Returns results as a JSON array."""
    parameters: dict = {
        "type": "object",
        "properties": {
            "prompt_template": {
                "type": "string",
                "description": "Prompt template with {{input}} placeholder. Each input replaces {{input}}.",
            },
            "inputs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of input strings to process in parallel",
            },
            "max_concurrent": {
                "type": "integer",
                "description": "Maximum concurrent tasks (default: 5)",
                "default": 5,
            },
        },
        "required": ["prompt_template", "inputs"],
    }

    _llm: Optional[LLM] = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, llm: Optional[LLM] = None, **data):
        super().__init__(**data)
        self._llm = llm or LLM()

    async def execute(
        self,
        prompt_template: str,
        inputs: List[str],
        max_concurrent: int = 5,
    ) -> ToolResult:
        if not inputs:
            return self.fail("No inputs provided")

        semaphore = asyncio.Semaphore(max_concurrent)
        results = [None] * len(inputs)

        async def process_one(idx: int, input_val: str):
            async with semaphore:
                prompt = prompt_template.replace("{{input}}", input_val)
                try:
                    response = await self._llm.ask(
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.0,
                    )
                    results[idx] = {"input": input_val, "output": response, "success": True}
                except Exception as e:
                    results[idx] = {"input": input_val, "output": str(e), "success": False}

        logger.info(f"[parallel_map] Processing {len(inputs)} inputs with max_concurrent={max_concurrent}")

        tasks = [process_one(i, inp) for i, inp in enumerate(inputs)]
        await asyncio.gather(*tasks)

        success_count = sum(1 for r in results if r and r.get("success"))
        fail_count = len(inputs) - success_count

        output_lines = [f"Parallel Map Results: {success_count}/{len(inputs)} succeeded\n"]
        for i, r in enumerate(results):
            if r:
                status = "OK" if r["success"] else "FAIL"
                output_lines.append(f"[{i+1}] ({status}) Input: {r['input'][:50]}")
                output_lines.append(f"    Output: {r['output'][:200]}")
                output_lines.append("")

        return self.success("\n".join(output_lines))
