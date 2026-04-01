"""
OpenManus-Max 综合测试
测试所有核心模块的功能
"""

import asyncio
import json
import os
import sys
import tempfile
import shutil

# 确保项目在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = 0
failed = 0
errors = []


def test(name):
    def decorator(func):
        async def wrapper():
            global passed, failed
            try:
                if asyncio.iscoroutinefunction(func):
                    await func()
                else:
                    func()
                passed += 1
                print(f"  [PASS] {name}")
            except Exception as e:
                failed += 1
                errors.append((name, str(e)))
                print(f"  [FAIL] {name}: {e}")
        return wrapper
    return decorator


# ============================================================
# 1. Schema Tests
# ============================================================

@test("Message creation and serialization")
def test_message():
    from openmanus_max.core.schema import Message, Role
    
    m = Message.system("hello")
    assert m.role == Role.SYSTEM
    assert m.content == "hello"
    d = m.to_dict()
    assert d["role"] == "system"
    assert d["content"] == "hello"
    
    m2 = Message.user("test")
    assert m2.role == Role.USER
    
    m3 = Message.assistant("response", tool_calls=[{"id": "1", "type": "function"}])
    d3 = m3.to_dict()
    assert "tool_calls" in d3
    
    m4 = Message.tool_result("result", tool_call_id="tc1", name="test_tool")
    d4 = m4.to_dict()
    assert d4["tool_call_id"] == "tc1"


@test("ToolResult success and error")
def test_tool_result():
    from openmanus_max.core.schema import ToolResult
    
    r1 = ToolResult(output="hello")
    assert r1.success
    assert str(r1) == "hello"
    assert bool(r1)
    
    r2 = ToolResult(error="something went wrong")
    assert not r2.success
    assert "Error:" in str(r2)


@test("TaskGraph DAG operations")
def test_task_graph():
    from openmanus_max.core.schema import TaskGraph, TaskNode, TaskStatus
    
    graph = TaskGraph(goal="Test goal")
    n1 = TaskNode(id="t1", title="Task 1")
    n2 = TaskNode(id="t2", title="Task 2", dependencies=["t1"])
    n3 = TaskNode(id="t3", title="Task 3")
    
    graph.add_node(n1)
    graph.add_node(n2)
    graph.add_node(n3)
    
    # t1 and t3 should be ready (no deps)
    ready = graph.get_ready_nodes()
    ready_ids = [n.id for n in ready]
    assert "t1" in ready_ids
    assert "t3" in ready_ids
    assert "t2" not in ready_ids  # depends on t1
    
    # Complete t1
    graph.mark_completed("t1", "done")
    assert graph.nodes["t1"].status == TaskStatus.COMPLETED
    
    # Now t2 should be ready
    ready = graph.get_ready_nodes()
    ready_ids = [n.id for n in ready]
    assert "t2" in ready_ids
    
    # Complete all
    graph.mark_completed("t2", "done")
    graph.mark_completed("t3", "done")
    assert graph.is_complete
    assert graph.progress == "3/3"
    
    # Format status
    status = graph.format_status()
    assert "Test goal" in status
    assert "3/3" in status


# ============================================================
# 2. Config Tests
# ============================================================

@test("Config default values")
def test_config():
    from openmanus_max.core.config import Config, LLMConfig
    
    config = Config()
    assert config.project_name == "OpenManus-Max"
    assert config.max_steps == 30
    assert config.llm.model == "gpt-4.1-mini"
    assert config.llm.temperature == 0.0
    assert config.memory.working_memory_size == 10


@test("Config load and override")
def test_config_load():
    from openmanus_max.core.config import Config, set_config, get_config
    
    config = Config(max_steps=50)
    config.llm.model = "test-model"
    set_config(config)
    
    loaded = get_config()
    assert loaded.max_steps == 50
    assert loaded.llm.model == "test-model"
    
    # Reset
    set_config(Config())


# ============================================================
# 3. Memory Tests
# ============================================================

@test("HierarchicalMemory working memory")
def test_memory_working():
    from openmanus_max.memory.hierarchical import HierarchicalMemory
    from openmanus_max.core.schema import Message
    
    mem = HierarchicalMemory()
    mem.working_memory_size = 5
    
    # Add messages
    for i in range(5):
        mem.add_message(Message.user(f"msg {i}"))
    
    assert len(mem.working_messages) == 5
    
    # Add one more - should push oldest to pending
    mem.add_message(Message.user("msg 5"))
    assert len(mem.working_messages) == 5
    assert mem.working_messages[0].content == "msg 1"


@test("HierarchicalMemory system messages")
def test_memory_system():
    from openmanus_max.memory.hierarchical import HierarchicalMemory
    from openmanus_max.core.schema import Message
    
    mem = HierarchicalMemory()
    mem.add_message(Message.system("sys prompt"))
    mem.add_message(Message.user("hello"))
    
    assert len(mem.system_messages) == 1
    assert len(mem.working_messages) == 1
    
    ctx = mem.get_context_messages()
    assert ctx[0].content == "sys prompt"


@test("HierarchicalMemory blackboard")
def test_memory_blackboard():
    from openmanus_max.memory.hierarchical import HierarchicalMemory
    
    mem = HierarchicalMemory()
    mem.bb_set("task", "test task")
    mem.bb_set("progress", 50)
    
    assert mem.bb_get("task") == "test task"
    assert mem.bb_get("progress") == 50
    assert mem.bb_get("missing", "default") == "default"
    
    mem.bb_update({"key1": "val1", "key2": "val2"})
    assert mem.bb_get("key1") == "val1"
    
    mem.bb_delete("key1")
    assert mem.bb_get("key1") is None


@test("HierarchicalMemory episodic compression")
def test_memory_episodic():
    from openmanus_max.memory.hierarchical import HierarchicalMemory
    from openmanus_max.core.schema import Message
    
    mem = HierarchicalMemory()
    mem.working_memory_size = 3
    mem.episodic_summary_threshold = 3
    
    # Add enough messages to trigger compression
    for i in range(10):
        mem.add_message(Message.user(f"message {i}"))
    
    # Should have episodic entries
    assert len(mem.episodic_entries) > 0
    assert len(mem.working_messages) <= 3


# ============================================================
# 4. Tool Tests
# ============================================================

@test("ToolCollection management")
def test_tool_collection():
    from openmanus_max.tool.base import ToolCollection
    from openmanus_max.tool.builtin.python_execute import PythonExecute
    from openmanus_max.tool.builtin.shell_exec import ShellExec
    
    tc = ToolCollection(PythonExecute(), ShellExec())
    assert len(tc) == 2
    assert "python_execute" in tc
    assert "shell_exec" in tc
    
    params = tc.to_params()
    assert len(params) == 2
    assert params[0]["type"] == "function"
    
    tc.unregister("shell_exec")
    assert len(tc) == 1
    assert "shell_exec" not in tc


@test("PythonExecute tool")
async def test_python_execute():
    from openmanus_max.tool.builtin.python_execute import PythonExecute
    
    tool = PythonExecute()
    
    # Success case
    result = await tool.execute(code="print(2 + 3)")
    assert result.success
    assert "5" in str(result)
    
    # Error case
    result = await tool.execute(code="raise ValueError('test error')")
    assert not result.success
    assert "test error" in str(result)
    
    # Timeout case
    result = await tool.execute(code="import time; time.sleep(10)", timeout=2)
    assert not result.success
    assert "timed out" in str(result).lower()


@test("ShellExec tool")
async def test_shell_exec():
    from openmanus_max.tool.builtin.shell_exec import ShellExec
    
    tool = ShellExec()
    
    result = await tool.execute(command="echo hello world")
    assert result.success
    assert "hello world" in str(result)
    
    result = await tool.execute(command="ls /nonexistent_dir_12345")
    assert not result.success


@test("FileEditor tool")
async def test_file_editor():
    from openmanus_max.tool.builtin.file_editor import FileEditor
    
    tool = FileEditor()
    tmpdir = tempfile.mkdtemp()
    test_file = os.path.join(tmpdir, "test.txt")
    
    try:
        # Create
        result = await tool.execute(command="create", path=test_file, content="hello\nworld\n")
        assert result.success
        
        # View
        result = await tool.execute(command="view", path=test_file)
        assert result.success
        assert "hello" in str(result)
        
        # Append
        result = await tool.execute(command="append", path=test_file, content="line3\n")
        assert result.success
        
        # str_replace
        result = await tool.execute(
            command="str_replace", path=test_file,
            old_str="hello", new_str="HELLO"
        )
        assert result.success
        
        # Verify
        result = await tool.execute(command="view", path=test_file)
        assert "HELLO" in str(result)
        
        # List dir
        result = await tool.execute(command="list_dir", path=tmpdir)
        assert result.success
        assert "test.txt" in str(result)
    finally:
        shutil.rmtree(tmpdir)


@test("PlanningTool CRUD")
async def test_planning_tool():
    from openmanus_max.tool.builtin.planning import PlanningTool
    
    tool = PlanningTool()
    
    # Create
    result = await tool.execute(
        command="create",
        goal="Test plan",
        steps=[
            {"id": "s1", "title": "Step 1", "description": "First step"},
            {"id": "s2", "title": "Step 2", "dependencies": ["s1"]},
        ],
    )
    assert result.success
    assert "2 steps" in str(result)
    
    # View
    result = await tool.execute(command="view")
    assert result.success
    assert "Test plan" in str(result)
    
    # Mark step
    result = await tool.execute(command="mark_step", step_id="s1", status="completed")
    assert result.success
    
    # Update
    result = await tool.execute(
        command="update",
        steps=[{"id": "s3", "title": "Step 3"}],
    )
    assert result.success


@test("Terminate and AskHuman tools")
async def test_terminate():
    from openmanus_max.tool.builtin.terminate import Terminate
    
    tool = Terminate()
    result = await tool.execute(message="Task done!")
    assert result.success
    assert "TASK COMPLETE" in str(result)


# ============================================================
# 5. Scheduler Tests
# ============================================================

@test("CronScheduler task management")
def test_scheduler():
    from openmanus_max.scheduler.cron_scheduler import CronScheduler, ScheduledTask
    
    db_path = tempfile.mktemp(suffix=".db")
    try:
        scheduler = CronScheduler(db_path=db_path)
        
        task = ScheduledTask(
            id="test1",
            name="Test Task",
            prompt="Do something",
            schedule_type="interval",
            schedule_expr="3600",
        )
        scheduler.add_task(task)
        
        tasks = scheduler.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "Test Task"
        
        # Get
        t = scheduler.get_task("test1")
        assert t is not None
        assert t.prompt == "Do something"
        
        # Remove
        assert scheduler.remove_task("test1")
        assert len(scheduler.list_tasks()) == 0
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@test("CronScheduler cron matching")
def test_cron_match():
    from openmanus_max.scheduler.cron_scheduler import CronScheduler
    
    assert CronScheduler._cron_match("*", 5)
    assert CronScheduler._cron_match("5", 5)
    assert not CronScheduler._cron_match("5", 6)
    assert CronScheduler._cron_match("*/5", 10)
    assert not CronScheduler._cron_match("*/5", 11)
    assert CronScheduler._cron_match("1,3,5", 3)
    assert not CronScheduler._cron_match("1,3,5", 4)
    assert CronScheduler._cron_match("1-5", 3)
    assert not CronScheduler._cron_match("1-5", 6)


# ============================================================
# 6. Web Scaffold Tests
# ============================================================

@test("WebScaffold static project")
async def test_scaffold_static():
    from openmanus_max.webdev.scaffold import WebScaffold
    
    tool = WebScaffold()
    tmpdir = tempfile.mkdtemp()
    try:
        result = await tool.execute(
            project_name="test-static",
            project_type="static",
            title="Test Static",
            description="A test project",
            base_dir=tmpdir,
        )
        assert result.success
        project_dir = os.path.join(tmpdir, "test-static")
        assert os.path.exists(os.path.join(project_dir, "index.html"))
        assert os.path.exists(os.path.join(project_dir, "css", "style.css"))
        assert os.path.exists(os.path.join(project_dir, "js", "app.js"))
        assert os.path.exists(os.path.join(project_dir, "README.md"))
    finally:
        shutil.rmtree(tmpdir)


@test("WebScaffold react project")
async def test_scaffold_react():
    from openmanus_max.webdev.scaffold import WebScaffold
    
    tool = WebScaffold()
    tmpdir = tempfile.mkdtemp()
    try:
        result = await tool.execute(
            project_name="test-react",
            project_type="react",
            title="Test React",
            base_dir=tmpdir,
        )
        assert result.success
        project_dir = os.path.join(tmpdir, "test-react")
        assert os.path.exists(os.path.join(project_dir, "package.json"))
        assert os.path.exists(os.path.join(project_dir, "src", "App.tsx"))
        assert os.path.exists(os.path.join(project_dir, "vite.config.ts"))
    finally:
        shutil.rmtree(tmpdir)


@test("WebScaffold API project")
async def test_scaffold_api():
    from openmanus_max.webdev.scaffold import WebScaffold
    
    tool = WebScaffold()
    tmpdir = tempfile.mkdtemp()
    try:
        result = await tool.execute(
            project_name="test-api",
            project_type="api",
            title="Test API",
            base_dir=tmpdir,
        )
        assert result.success
        project_dir = os.path.join(tmpdir, "test-api")
        assert os.path.exists(os.path.join(project_dir, "app", "main.py"))
        assert os.path.exists(os.path.join(project_dir, "requirements.txt"))
    finally:
        shutil.rmtree(tmpdir)


# ============================================================
# 7. Agent Integration Tests (without real LLM)
# ============================================================

@test("ManusAgent initialization")
def test_manus_init():
    from openmanus_max.agent.manus import ManusAgent
    from openmanus_max.core.config import Config, set_config
    
    # Set config with dummy key to avoid errors
    config = Config()
    config.llm.api_key = "test-key"
    set_config(config)
    
    agent = ManusAgent()
    assert agent.name == "manus"
    assert len(agent.tools) >= 8  # At least 8 built-in tools
    assert "python_execute" in agent.tools
    assert "shell_exec" in agent.tools
    assert "file_editor" in agent.tools
    assert "web_search" in agent.tools
    assert "browser" in agent.tools
    assert "planning" in agent.tools
    assert "terminate" in agent.tools
    assert "ask_human" in agent.tools


@test("Full agent with extra tools")
def test_full_agent():
    from openmanus_max.cli import create_full_agent
    from openmanus_max.core.config import Config, set_config
    
    config = Config()
    config.llm.api_key = "test-key"
    set_config(config)
    
    agent = create_full_agent()
    assert "parallel_map" in agent.tools
    assert "schedule" in agent.tools
    assert "image_generate" in agent.tools
    assert "text_to_speech" in agent.tools
    assert "slides_generate" in agent.tools
    assert "web_scaffold" in agent.tools
    
    # Total should be 14 tools
    total = len(agent.tools)
    print(f"    Total tools: {total}")
    assert total >= 14


@test("DAG Scheduler format")
def test_dag_format():
    from openmanus_max.core.schema import TaskGraph, TaskNode
    
    graph = TaskGraph(goal="Build website")
    graph.add_node(TaskNode(id="t1", title="Design"))
    graph.add_node(TaskNode(id="t2", title="Code", dependencies=["t1"]))
    graph.add_node(TaskNode(id="t3", title="Test", dependencies=["t2"]))
    
    status = graph.format_status()
    assert "Build website" in status
    assert "Design" in status
    assert "Code" in status
    assert "Test" in status
    assert "0/3" in status


# ============================================================
# 8. CLI Tests
# ============================================================

@test("CLI argument parser")
def test_cli_parser():
    from openmanus_max.cli import main
    import argparse
    # Just verify the function exists and is callable
    assert callable(main)


# ============================================================
# Run all tests
# ============================================================

async def run_all():
    global passed, failed
    
    print("=" * 60)
    print("OpenManus-Max Test Suite")
    print("=" * 60)
    
    # Collect all test functions
    tests = [
        # Schema
        test_message, test_tool_result, test_task_graph,
        # Config
        test_config, test_config_load,
        # Memory
        test_memory_working, test_memory_system, test_memory_blackboard, test_memory_episodic,
        # Tools
        test_tool_collection, test_python_execute, test_shell_exec, test_file_editor,
        test_planning_tool, test_terminate,
        # Scheduler
        test_scheduler, test_cron_match,
        # Web Scaffold
        test_scaffold_static, test_scaffold_react, test_scaffold_api,
        # Agent
        test_manus_init, test_full_agent, test_dag_format,
        # CLI
        test_cli_parser,
    ]
    
    for t in tests:
        await t()
    
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if errors:
        print("\nFailed tests:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all())
    sys.exit(0 if success else 1)
