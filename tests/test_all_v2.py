"""
OpenManus-Max 综合测试 V2 - 覆盖所有模块（含新增模块）
"""

import asyncio
import json
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = 0
failed = 0
errors = []


def test(name):
    def decorator(func):
        global passed, failed
        try:
            if asyncio.iscoroutinefunction(func):
                asyncio.get_event_loop().run_until_complete(func())
            else:
                func()
            passed += 1
            print(f"  ✓ {name}")
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  ✗ {name}: {e}")
            traceback.print_exc()
        return func
    return decorator


print("=" * 60)
print("OpenManus-Max Comprehensive Test Suite V2")
print("=" * 60)

# ============================================================
# 1. Core: Schema
# ============================================================
print("\n--- Core: Schema ---")

@test("Message creation and serialization")
def _():
    from openmanus_max.core.schema import Message
    m = Message.user("hello")
    assert m.role.value == "user"
    assert m.content == "hello"
    d = m.to_dict()
    assert d["role"] == "user"
    assert d["content"] == "hello"

@test("Message types: system, assistant, tool_result")
def _():
    from openmanus_max.core.schema import Message
    s = Message.system("sys")
    assert s.role.value == "system"
    a = Message.assistant("hi")
    assert a.role.value == "assistant"
    t = Message.tool_result("result", "call_1")
    assert t.role.value == "tool"
    assert t.tool_call_id == "call_1"

@test("TaskNode and TaskGraph")
def _():
    from openmanus_max.core.schema import TaskGraph, TaskNode, TaskStatus
    g = TaskGraph(goal="test")
    n1 = TaskNode(id="t1", title="Task 1", description="First")
    n2 = TaskNode(id="t2", title="Task 2", dependencies=["t1"])
    g.add_node(n1)
    g.add_node(n2)
    assert len(g.nodes) == 2
    ready = g.get_ready_nodes()
    assert len(ready) == 1
    assert ready[0].id == "t1"
    g.mark_running("t1")
    assert g.nodes["t1"].status == TaskStatus.RUNNING
    g.mark_completed("t1", "done")
    assert g.nodes["t1"].status == TaskStatus.COMPLETED
    ready2 = g.get_ready_nodes()
    assert len(ready2) == 1
    assert ready2[0].id == "t2"

@test("TaskGraph progress and format_status")
def _():
    from openmanus_max.core.schema import TaskGraph, TaskNode
    g = TaskGraph(goal="test progress")
    g.add_node(TaskNode(id="t1", title="A"))
    g.add_node(TaskNode(id="t2", title="B", dependencies=["t1"]))
    g.mark_completed("t1", "ok")
    assert "1/2" in g.progress
    status = g.format_status()
    assert "t1" in status
    assert "t2" in status

@test("ToolResult success and error")
def _():
    from openmanus_max.core.schema import ToolResult
    r1 = ToolResult(output="ok")
    assert r1.success is True
    r2 = ToolResult(error="fail")
    assert r2.success is False


# ============================================================
# 2. Core: Config
# ============================================================
print("\n--- Core: Config ---")

@test("Config defaults")
def _():
    from openmanus_max.core.config import Config, get_config
    c = get_config()
    assert c.llm is not None
    assert c.max_steps > 0
    assert c.workspace_dir is not None

@test("Config TOML loading")
def _():
    from openmanus_max.core.config import Config
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
        f.write('[llm]\nmodel = "test-model"\napi_key = "test-key"\n')
        f.flush()
        c = Config.load(f.name)
        assert c.llm.model == "test-model"
    os.unlink(f.name)


# ============================================================
# 3. Core: LLM
# ============================================================
print("\n--- Core: LLM ---")

@test("LLM client initialization")
def _():
    from openmanus_max.core.llm import LLM
    llm = LLM()
    assert llm.client is not None
    assert llm.total_prompt_tokens == 0

@test("LLM has streaming methods")
def _():
    from openmanus_max.core.llm import LLM
    llm = LLM()
    assert hasattr(llm, 'ask_stream')
    assert hasattr(llm, 'ask_stream_iter')
    assert hasattr(llm, 'ask_vision')
    assert hasattr(llm, 'ask_vision_url')
    assert hasattr(llm, 'ask_tool')

@test("LLM token usage tracking")
def _():
    from openmanus_max.core.llm import LLM
    llm = LLM()
    usage = llm.token_usage
    assert "prompt_tokens" in usage
    assert "completion_tokens" in usage
    assert "total_tokens" in usage


# ============================================================
# 4. Memory: Hierarchical
# ============================================================
print("\n--- Memory: Hierarchical ---")

@test("HierarchicalMemory working memory (add_message)")
def _():
    from openmanus_max.memory.hierarchical import HierarchicalMemory
    from openmanus_max.core.schema import Message
    mem = HierarchicalMemory(working_memory_size=20)
    for i in range(3):
        mem.add_message(Message.user(f"msg {i}"))
    assert len(mem.working_messages) == 3

@test("HierarchicalMemory compression trigger")
def _():
    from openmanus_max.memory.hierarchical import HierarchicalMemory
    from openmanus_max.core.schema import Message
    mem = HierarchicalMemory(working_memory_size=3, episodic_summary_threshold=2)
    for i in range(8):
        mem.add_message(Message.user(f"msg {i}"))
    # After many messages with small limit, episodic entries should exist
    assert len(mem.episodic_entries) > 0

@test("HierarchicalMemory blackboard (bb_set/bb_get)")
def _():
    from openmanus_max.memory.hierarchical import HierarchicalMemory
    mem = HierarchicalMemory()
    mem.bb_set("key1", "value1")
    assert mem.bb_get("key1") == "value1"
    assert mem.bb_get("missing") is None

@test("HierarchicalMemory stats")
def _():
    from openmanus_max.memory.hierarchical import HierarchicalMemory
    from openmanus_max.core.schema import Message
    mem = HierarchicalMemory()
    mem.add_message(Message.user("test"))
    stats = mem.stats
    assert "working_messages" in stats
    assert "episodic_entries" in stats  # note: key is episodic_entries not episodes
    assert "blackboard_keys" in stats
    assert stats["working_messages"] == 1

@test("HierarchicalMemory set_llm for smart compression")
def _():
    from openmanus_max.memory.hierarchical import HierarchicalMemory
    mem = HierarchicalMemory()
    assert hasattr(mem, 'set_llm')
    mem.set_llm(None)  # Should not crash

@test("HierarchicalMemory get_context_messages")
def _():
    from openmanus_max.memory.hierarchical import HierarchicalMemory
    from openmanus_max.core.schema import Message
    mem = HierarchicalMemory()
    mem.add_message(Message.system("sys prompt"))
    mem.add_message(Message.user("hello"))
    ctx = mem.get_context_messages()
    assert len(ctx) >= 2


# ============================================================
# 5. Flow: DAG Scheduler
# ============================================================
print("\n--- Flow: DAG Scheduler ---")

@test("DAGScheduler initialization")
def _():
    from openmanus_max.flow.dag_scheduler import DAGScheduler
    s = DAGScheduler()
    assert s.graph is None

@test("DAGScheduler execution with custom executor")
async def _():
    from openmanus_max.flow.dag_scheduler import DAGScheduler
    from openmanus_max.core.schema import TaskGraph, TaskNode
    s = DAGScheduler()
    g = TaskGraph(goal="test")
    g.add_node(TaskNode(id="t1", title="A"))
    g.add_node(TaskNode(id="t2", title="B", dependencies=["t1"]))
    async def executor(node, graph):
        return f"done_{node.id}"
    result = await s.execute(g, executor)
    assert result.nodes["t1"].result == "done_t1"
    assert result.nodes["t2"].result == "done_t2"
    assert result.is_complete

@test("DAGScheduler parallel execution")
async def _():
    from openmanus_max.flow.dag_scheduler import DAGScheduler
    from openmanus_max.core.schema import TaskGraph, TaskNode
    import time
    s = DAGScheduler()
    g = TaskGraph(goal="parallel test")
    g.add_node(TaskNode(id="t1", title="A"))
    g.add_node(TaskNode(id="t2", title="B"))
    g.add_node(TaskNode(id="t3", title="C", dependencies=["t1", "t2"]))
    async def executor(node, graph):
        await asyncio.sleep(0.1)
        return f"done_{node.id}"
    start = time.time()
    result = await s.execute(g, executor, max_concurrent=3)
    elapsed = time.time() - start
    assert result.is_complete
    assert elapsed < 0.35

@test("AgentRegistry")
def _():
    from openmanus_max.flow.dag_scheduler import AgentRegistry
    reg = AgentRegistry()
    reg.register("code", lambda: "code_agent")
    reg.set_default(lambda: "default_agent")
    assert reg.create("code") == "code_agent"
    assert reg.create("unknown") == "default_agent"
    assert "code" in reg.registered_types


# ============================================================
# 6. Tool System
# ============================================================
print("\n--- Tool System ---")

@test("BaseTool and ToolCollection")
def _():
    from openmanus_max.tool.base import BaseTool, ToolCollection
    from openmanus_max.core.schema import ToolResult
    class DummyTool(BaseTool):
        name: str = "dummy"
        description: str = "A dummy tool"
        parameters: dict = {"type": "object", "properties": {}}
        async def execute(self, **kwargs):
            return ToolResult(output="dummy result")
    t = DummyTool()
    tc = ToolCollection(t)
    assert len(tc) == 1
    assert tc.get("dummy") is not None
    schema = tc.to_params()  # correct method name
    assert len(schema) == 1

@test("ToolCollection register and dynamic add")
def _():
    from openmanus_max.tool.base import BaseTool, ToolCollection
    from openmanus_max.core.schema import ToolResult
    class T1(BaseTool):
        name: str = "t1"
        description: str = "T1"
        parameters: dict = {"type": "object", "properties": {}}
        async def execute(self, **kwargs):
            return ToolResult(output="t1")
    class T2(BaseTool):
        name: str = "t2"
        description: str = "T2"
        parameters: dict = {"type": "object", "properties": {}}
        async def execute(self, **kwargs):
            return ToolResult(output="t2")
    tc = ToolCollection(T1())
    assert len(tc) == 1
    tc.register(T2())
    assert len(tc) == 2
    assert tc.get("t2") is not None

@test("PythonExecute tool")
async def _():
    from openmanus_max.tool.builtin.python_execute import PythonExecute
    t = PythonExecute()
    r = await t.execute(code="print(2+3)")
    assert "5" in r.output

@test("ShellExec tool")
async def _():
    from openmanus_max.tool.builtin.shell_exec import ShellExec
    t = ShellExec()
    r = await t.execute(command="echo hello_world")
    assert "hello_world" in r.output

@test("FileEditor tool - write and read")
async def _():
    from openmanus_max.tool.builtin.file_editor import FileEditor
    t = FileEditor()
    path = "/tmp/test_openmanus_max_file.txt"
    r1 = await t.execute(command="write", path=path, content="hello world")
    assert r1.success
    r2 = await t.execute(command="view", path=path)
    assert "hello world" in r2.output
    os.unlink(path)

@test("PlanningTool - create and view")
async def _():
    from openmanus_max.tool.builtin.planning import PlanningTool
    t = PlanningTool()
    r = await t.execute(command="create", goal="test goal", steps=[
        {"id": "t1", "title": "Step 1", "description": "Do step 1"},
    ])
    assert r.success
    r2 = await t.execute(command="view")
    assert r2.success

@test("Terminate tool")
async def _():
    from openmanus_max.tool.builtin.terminate import Terminate
    t = Terminate()
    r = await t.execute(message="Task done")
    assert r.success
    assert "Task done" in r.output

@test("AskHuman tool")
async def _():
    from openmanus_max.tool.builtin.terminate import AskHuman
    t = AskHuman()
    assert t.name == "ask_human"
    assert "question" in json.dumps(t.parameters)

@test("ScheduleTool - create and list")
async def _():
    from openmanus_max.tool.builtin.schedule import ScheduleTool
    t = ScheduleTool()
    r = await t.execute(
        command="create",
        name="test_job",
        schedule_type="interval",
        schedule_expr="3600",
        prompt="Test task",
    )
    assert r.success
    r2 = await t.execute(command="list")
    assert r2.success

@test("ParallelMap tool")
def _():
    from openmanus_max.tool.builtin.parallel import ParallelMap
    t = ParallelMap()
    assert t.name == "parallel_map"
    assert "items" in json.dumps(t.parameters)


# ============================================================
# 7. NEW Tools
# ============================================================
print("\n--- NEW Tools ---")

@test("DataVisualization tool - bar chart")
async def _():
    from openmanus_max.tool.builtin.data_visualization import DataVisualization
    t = DataVisualization()
    output_path = "/tmp/test_chart.png"
    r = await t.execute(
        chart_type="bar",
        data={"labels": ["A", "B", "C"], "values": [10, 20, 30]},
        title="Test Chart",
        output_path=output_path,
    )
    assert r.success
    assert os.path.exists(output_path)
    os.unlink(output_path)

@test("DataVisualization tool - line chart")
async def _():
    from openmanus_max.tool.builtin.data_visualization import DataVisualization
    t = DataVisualization()
    output_path = "/tmp/test_line.png"
    r = await t.execute(
        chart_type="line",
        data={"x": [1, 2, 3, 4], "y": [10, 20, 15, 25]},
        output_path=output_path,
    )
    assert r.success
    os.unlink(output_path)

@test("DataVisualization tool - pie chart")
async def _():
    from openmanus_max.tool.builtin.data_visualization import DataVisualization
    t = DataVisualization()
    output_path = "/tmp/test_pie.png"
    r = await t.execute(
        chart_type="pie",
        data={"labels": ["X", "Y", "Z"], "values": [40, 35, 25]},
        output_path=output_path,
    )
    assert r.success
    os.unlink(output_path)

@test("DataVisualization tool - multi-series bar")
async def _():
    from openmanus_max.tool.builtin.data_visualization import DataVisualization
    t = DataVisualization()
    output_path = "/tmp/test_multi_bar.png"
    r = await t.execute(
        chart_type="bar",
        data={
            "labels": ["Q1", "Q2", "Q3"],
            "series": [
                {"name": "2024", "values": [10, 20, 30]},
                {"name": "2025", "values": [15, 25, 35]},
            ],
        },
        output_path=output_path,
    )
    assert r.success
    os.unlink(output_path)

@test("DataVisualization tool - heatmap")
async def _():
    from openmanus_max.tool.builtin.data_visualization import DataVisualization
    t = DataVisualization()
    output_path = "/tmp/test_heatmap.png"
    r = await t.execute(
        chart_type="heatmap",
        data={
            "matrix": [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
            "x_labels": ["A", "B", "C"],
            "y_labels": ["X", "Y", "Z"],
        },
        output_path=output_path,
    )
    assert r.success
    os.unlink(output_path)

@test("VisionTool initialization")
def _():
    from openmanus_max.tool.builtin.vision import VisionTool
    t = VisionTool()
    assert t.name == "vision_analyze"
    assert hasattr(t, 'set_llm')

@test("VisionTool error without LLM")
async def _():
    from openmanus_max.tool.builtin.vision import VisionTool
    t = VisionTool()
    r = await t.execute(prompt="test", image_path="/nonexistent.png")
    assert not r.success

@test("WebCrawl tool initialization")
def _():
    from openmanus_max.tool.builtin.web_crawl import WebCrawl
    t = WebCrawl()
    assert t.name == "web_crawl"
    assert "url" in json.dumps(t.parameters)
    assert "markdown" in json.dumps(t.parameters)

@test("ComputerUseTool initialization")
def _():
    from openmanus_max.tool.builtin.computer_use import ComputerUseTool
    t = ComputerUseTool()
    assert t.name == "computer_use"
    assert "screenshot" in json.dumps(t.parameters)
    assert "left_click" in json.dumps(t.parameters)

@test("WebSearch multi-engine support")
def _():
    from openmanus_max.tool.builtin.web_search import WebSearch
    t = WebSearch()
    assert "images" in json.dumps(t.parameters)
    assert "news" in json.dumps(t.parameters)
    assert "region" in json.dumps(t.parameters)


# ============================================================
# 8. MCP Client
# ============================================================
print("\n--- MCP Client ---")

@test("MCPManager initialization")
def _():
    from openmanus_max.tool.mcp.client import MCPManager
    m = MCPManager()
    assert len(m.servers) == 0
    assert len(m.tools) == 0
    tc = m.get_tool_collection()
    assert len(tc) == 0

@test("MCPServerConnection initialization")
def _():
    from openmanus_max.tool.mcp.client import MCPServerConnection
    s = MCPServerConnection(name="test", transport="stdio", command="echo")
    assert s.name == "test"
    assert s.transport == "stdio"
    assert not s.is_connected


# ============================================================
# 9. Media & Slides
# ============================================================
print("\n--- Media & Slides ---")

@test("ImageGenerator tool")
def _():
    from openmanus_max.media.generator import ImageGenerator
    t = ImageGenerator()
    assert t.name == "image_generate"
    assert "prompt" in json.dumps(t.parameters)

@test("TTSGenerator tool (text_to_speech)")
def _():
    from openmanus_max.media.generator import TTSGenerator
    t = TTSGenerator()
    assert t.name == "text_to_speech"  # actual name
    assert "text" in json.dumps(t.parameters)

@test("SlidesGenerator tool (topic param)")
def _():
    from openmanus_max.slides.generator import SlidesGenerator
    t = SlidesGenerator()
    assert t.name == "slides_generate"
    assert "topic" in json.dumps(t.parameters)  # actual param name


# ============================================================
# 10. Web Scaffold
# ============================================================
print("\n--- Web Scaffold ---")

@test("WebScaffold tool")
def _():
    from openmanus_max.webdev.scaffold import WebScaffold
    t = WebScaffold()
    assert t.name == "web_scaffold"
    assert "project_name" in json.dumps(t.parameters)

@test("WebScaffold generate static project")
async def _():
    from openmanus_max.webdev.scaffold import WebScaffold
    t = WebScaffold()
    r = await t.execute(
        project_name="test_proj",
        project_type="static",
        base_dir="/tmp/test_scaffold",
    )
    assert r.success
    assert os.path.exists("/tmp/test_scaffold/test_proj/index.html")
    import shutil
    shutil.rmtree("/tmp/test_scaffold", ignore_errors=True)

@test("WebScaffold generate react project")
async def _():
    from openmanus_max.webdev.scaffold import WebScaffold
    t = WebScaffold()
    r = await t.execute(
        project_name="react_proj",
        project_type="react",
        base_dir="/tmp/test_scaffold_react",
    )
    assert r.success
    assert os.path.exists("/tmp/test_scaffold_react/react_proj/package.json")
    import shutil
    shutil.rmtree("/tmp/test_scaffold_react", ignore_errors=True)

@test("WebScaffold generate api project")
async def _():
    from openmanus_max.webdev.scaffold import WebScaffold
    t = WebScaffold()
    r = await t.execute(
        project_name="api_proj",
        project_type="api",
        base_dir="/tmp/test_scaffold_api",
    )
    assert r.success
    assert os.path.exists("/tmp/test_scaffold_api/api_proj/requirements.txt")
    import shutil
    shutil.rmtree("/tmp/test_scaffold_api", ignore_errors=True)


# ============================================================
# 11. Scheduler
# ============================================================
print("\n--- Scheduler ---")

@test("CronScheduler initialization")
def _():
    from openmanus_max.scheduler.cron_scheduler import CronScheduler
    s = CronScheduler()
    assert isinstance(s._tasks, dict)
    assert s._running is False

@test("CronScheduler add_task and list_tasks")
def _():
    from openmanus_max.scheduler.cron_scheduler import CronScheduler, ScheduledTask
    s = CronScheduler(db_path="/tmp/test_scheduler.db")
    task = ScheduledTask(
        id="test1", name="test_job", prompt="test",
        schedule_type="interval", schedule_expr="60",
    )
    s.add_task(task)
    tasks = s.list_tasks()
    assert len(tasks) >= 1
    assert any(t.name == "test_job" for t in tasks)
    # Cleanup
    s.remove_task("test1")
    os.unlink("/tmp/test_scheduler.db")


# ============================================================
# 12. A2A Server
# ============================================================
print("\n--- A2A Server ---")

@test("A2AServer initialization")
def _():
    from openmanus_max.a2a.server import A2AServer
    s = A2AServer()
    assert len(s.tasks) == 0
    card = s.get_agent_card()
    assert card["name"] == "OpenManus-Max"
    assert "skills" in card

@test("A2AServer task send and get")
async def _():
    from openmanus_max.a2a.server import A2AServer
    s = A2AServer()
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tasks/send",
        "params": {
            "id": "task_1",
            "message": {"parts": [{"type": "text", "text": "Hello"}]},
        },
    }
    resp = await s.handle_jsonrpc(req)
    assert resp["result"]["id"] == "task_1"
    get_req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tasks/get",
        "params": {"id": "task_1"},
    }
    get_resp = await s.handle_jsonrpc(get_req)
    assert get_resp["result"]["id"] == "task_1"

@test("A2AServer FastAPI app creation")
def _():
    from openmanus_max.a2a.server import A2AServer
    s = A2AServer()
    app = s.create_fastapi_app()
    assert app is not None
    assert app.title == "OpenManus-Max A2A Server"


# ============================================================
# 13. Agent Layer
# ============================================================
print("\n--- Agent Layer ---")

@test("BaseAgent is abstract (think + act required)")
def _():
    from openmanus_max.agent.base import BaseAgent
    try:
        class IncompleteAgent(BaseAgent):
            pass
        IncompleteAgent(name="test")
        assert False, "Should have raised"
    except TypeError as e:
        assert "abstract" in str(e).lower()

@test("ToolCallAgent initialization")
def _():
    from openmanus_max.agent.toolcall import ToolCallAgent
    a = ToolCallAgent(name="tc")
    assert a.name == "tc"
    assert a.tools is not None

@test("ReflectAgent initialization (reflect_every)")
def _():
    from openmanus_max.agent.reflect import ReflectAgent
    a = ReflectAgent(name="ref", reflect_every=3)
    assert a.name == "ref"
    assert a.reflect_every == 3  # public attribute

@test("ManusAgent initialization with all built-in tools")
def _():
    from openmanus_max.agent.manus import ManusAgent
    a = ManusAgent()
    assert a.name == "manus"
    tool_names = list(a.tools._tools.keys())
    expected = [
        "python_execute", "shell_exec", "file_editor",
        "web_search", "web_crawl", "browser",
        "planning", "ask_human", "terminate",
        "vision_analyze", "data_visualization", "computer_use",
    ]
    for e in expected:
        assert e in tool_names, f"Missing tool: {e}"

@test("ManusAgent with extra tools")
def _():
    from openmanus_max.agent.manus import ManusAgent
    from openmanus_max.tool.base import ToolCollection
    from openmanus_max.tool.builtin.parallel import ParallelMap
    from openmanus_max.tool.builtin.schedule import ScheduleTool
    extra = ToolCollection(ParallelMap(), ScheduleTool())
    a = ManusAgent(extra_tools=extra)
    assert "parallel_map" in a.tools._tools
    assert "schedule" in a.tools._tools


# ============================================================
# 14. CLI
# ============================================================
print("\n--- CLI ---")

@test("CLI create_full_agent with all 18 tools")
def _():
    from openmanus_max.cli import create_full_agent
    a = create_full_agent()
    assert a.name == "manus"
    tool_names = list(a.tools._tools.keys())
    # Built-in tools from ManusAgent
    for name in ["python_execute", "shell_exec", "file_editor",
                 "web_search", "web_crawl", "browser", "planning",
                 "ask_human", "terminate", "vision_analyze",
                 "data_visualization", "computer_use"]:
        assert name in tool_names, f"Missing built-in: {name}"
    # Extra tools from CLI
    for name in ["parallel_map", "schedule", "image_generate",
                 "text_to_speech", "slides_generate", "web_scaffold"]:
        assert name in tool_names, f"Missing extra: {name}"
    total = len(tool_names)
    assert total >= 18, f"Expected >= 18 tools, got {total}: {sorted(tool_names)}"

@test("CLI _handle_command")
def _():
    from openmanus_max.cli import _handle_command, create_full_agent
    a = create_full_agent()
    _handle_command("/tools", a)
    _handle_command("/status", a)
    _handle_command("/memory", a)
    _handle_command("/help", a)
    _handle_command("/unknown", a)


# ============================================================
# Summary
# ============================================================
print(f"\n{'='*60}")
print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
print(f"{'='*60}")

if errors:
    print("\nFailed tests:")
    for name, err in errors:
        print(f"  ✗ {name}: {err}")
    sys.exit(1)
else:
    print("\nAll tests passed! ✓")
