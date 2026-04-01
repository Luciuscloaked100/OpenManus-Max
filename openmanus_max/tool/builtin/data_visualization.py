"""
OpenManus-Max Data Visualization Tool
数据可视化工具 - 支持 matplotlib/plotly 图表生成
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List, Optional

from openmanus_max.core.schema import ToolResult
from openmanus_max.tool.base import BaseTool


class DataVisualization(BaseTool):
    """数据可视化工具 - 生成各类图表"""

    name: str = "data_visualization"
    description: str = (
        "Generate data visualizations and charts. Supports bar, line, pie, scatter, "
        "heatmap, histogram, and box plots. Provide data as JSON arrays and specify "
        "chart type and options. Returns the path to the generated image file."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "description": "Type of chart: bar, line, pie, scatter, heatmap, histogram, box, area",
                "enum": ["bar", "line", "pie", "scatter", "heatmap", "histogram", "box", "area"],
            },
            "data": {
                "type": "object",
                "description": "Chart data. For most charts: {labels: [...], values: [...]} or {x: [...], y: [...]}. "
                "For scatter: {x: [...], y: [...]}. For heatmap: {matrix: [[...], ...], x_labels: [...], y_labels: [...]}. "
                "For multi-series: {series: [{name: str, values: [...]}], labels: [...]}",
            },
            "title": {
                "type": "string",
                "description": "Chart title",
                "default": "",
            },
            "x_label": {
                "type": "string",
                "description": "X-axis label",
                "default": "",
            },
            "y_label": {
                "type": "string",
                "description": "Y-axis label",
                "default": "",
            },
            "output_path": {
                "type": "string",
                "description": "Output file path (PNG). If not specified, saves to temp dir.",
                "default": "",
            },
            "style": {
                "type": "string",
                "description": "Matplotlib style: default, seaborn, ggplot, dark_background, bmh",
                "default": "seaborn-v0_8",
            },
            "figsize": {
                "type": "array",
                "description": "Figure size [width, height] in inches",
                "default": [10, 6],
            },
        },
        "required": ["chart_type", "data"],
    }

    async def execute(
        self,
        chart_type: str,
        data: dict,
        title: str = "",
        x_label: str = "",
        y_label: str = "",
        output_path: str = "",
        style: str = "seaborn-v0_8",
        figsize: list = None,
        **kwargs,
    ) -> ToolResult:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import numpy as np
        except ImportError:
            return ToolResult(error="matplotlib and numpy are required. Install with: pip install matplotlib numpy")

        if figsize is None:
            figsize = [10, 6]

        if not output_path:
            output_path = os.path.join(tempfile.gettempdir(), f"chart_{chart_type}.png")

        try:
            # 设置样式
            try:
                plt.style.use(style)
            except Exception:
                plt.style.use("default")

            fig, ax = plt.subplots(figsize=tuple(figsize))

            if chart_type == "bar":
                self._draw_bar(ax, data)
            elif chart_type == "line":
                self._draw_line(ax, data)
            elif chart_type == "pie":
                self._draw_pie(ax, data)
            elif chart_type == "scatter":
                self._draw_scatter(ax, data)
            elif chart_type == "heatmap":
                self._draw_heatmap(fig, ax, data)
            elif chart_type == "histogram":
                self._draw_histogram(ax, data)
            elif chart_type == "box":
                self._draw_box(ax, data)
            elif chart_type == "area":
                self._draw_area(ax, data)
            else:
                return ToolResult(error=f"Unsupported chart type: {chart_type}")

            if title:
                ax.set_title(title, fontsize=14, fontweight="bold")
            if x_label:
                ax.set_xlabel(x_label)
            if y_label:
                ax.set_ylabel(y_label)

            plt.tight_layout()
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
            plt.close(fig)

            return ToolResult(
                output=f"Chart saved to: {output_path}",
                files=[output_path],
            )
        except Exception as e:
            plt.close("all")
            return ToolResult(error=f"Chart generation failed: {e}")

    def _draw_bar(self, ax, data):
        import numpy as np
        labels = data.get("labels", [])
        if "series" in data:
            # Multi-series bar
            series = data["series"]
            x = np.arange(len(labels))
            width = 0.8 / len(series)
            for i, s in enumerate(series):
                offset = (i - len(series) / 2 + 0.5) * width
                ax.bar(x + offset, s["values"], width, label=s.get("name", f"Series {i+1}"))
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=45, ha="right")
            ax.legend()
        else:
            values = data.get("values", [])
            colors = data.get("colors", None)
            ax.bar(labels, values, color=colors)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=45, ha="right")

    def _draw_line(self, ax, data):
        if "series" in data:
            labels = data.get("labels", None)
            for s in data["series"]:
                x = labels if labels else range(len(s["values"]))
                ax.plot(x, s["values"], marker="o", label=s.get("name", ""))
            ax.legend()
        else:
            x = data.get("x", data.get("labels", range(len(data.get("values", [])))))
            y = data.get("y", data.get("values", []))
            ax.plot(x, y, marker="o")

    def _draw_pie(self, ax, data):
        labels = data.get("labels", [])
        values = data.get("values", [])
        colors = data.get("colors", None)
        explode = data.get("explode", None)
        ax.pie(values, labels=labels, colors=colors, explode=explode,
               autopct="%1.1f%%", startangle=90)
        ax.axis("equal")

    def _draw_scatter(self, ax, data):
        x = data.get("x", [])
        y = data.get("y", [])
        sizes = data.get("sizes", None)
        colors = data.get("colors", None)
        ax.scatter(x, y, s=sizes, c=colors, alpha=0.7)

    def _draw_heatmap(self, fig, ax, data):
        import numpy as np
        matrix = np.array(data.get("matrix", []))
        x_labels = data.get("x_labels", [])
        y_labels = data.get("y_labels", [])
        im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto")
        fig.colorbar(im, ax=ax)
        if x_labels:
            ax.set_xticks(range(len(x_labels)))
            ax.set_xticklabels(x_labels, rotation=45, ha="right")
        if y_labels:
            ax.set_yticks(range(len(y_labels)))
            ax.set_yticklabels(y_labels)

    def _draw_histogram(self, ax, data):
        values = data.get("values", [])
        bins = data.get("bins", 20)
        ax.hist(values, bins=bins, edgecolor="black", alpha=0.7)

    def _draw_box(self, ax, data):
        if "series" in data:
            box_data = [s["values"] for s in data["series"]]
            labels = [s.get("name", f"S{i+1}") for i, s in enumerate(data["series"])]
            ax.boxplot(box_data, labels=labels)
        else:
            ax.boxplot(data.get("values", []))

    def _draw_area(self, ax, data):
        if "series" in data:
            labels = data.get("labels", None)
            for s in data["series"]:
                x = labels if labels else range(len(s["values"]))
                ax.fill_between(range(len(s["values"])), s["values"], alpha=0.5, label=s.get("name", ""))
            ax.legend()
        else:
            x = data.get("x", range(len(data.get("values", []))))
            y = data.get("y", data.get("values", []))
            ax.fill_between(range(len(y)), y, alpha=0.5)
