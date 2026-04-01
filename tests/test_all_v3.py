"""
OpenManus-Max V3 综合测试
覆盖所有模块（包括新增的权限引擎、Skill 系统、执行引擎、Routine 引擎）
"""

import asyncio
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================
# 1. 权限引擎测试
# ============================================================

class TestPermissionEngine(unittest.TestCase):
    """权限引擎测试"""

    def test_permission_modes(self):
        from openmanus_max.security.permission import PermissionMode
        self.assertEqual(PermissionMode.YOLO, 0)
        self.assertEqual(PermissionMode.STANDARD, 1)
        self.assertEqual(PermissionMode.STRICT, 2)
        self.assertEqual(PermissionMode.SANDBOX, 3)
        self.assertTrue(PermissionMode.SANDBOX > PermissionMode.YOLO)

    def test_tool_risk_levels(self):
        from openmanus_max.security.permission import ToolRisk
        self.assertEqual(ToolRisk.READ_ONLY, 0)
        self.assertEqual(ToolRisk.DESTRUCTIVE, 4)
        self.assertTrue(ToolRisk.EXECUTE > ToolRisk.WORKSPACE)

    def test_default_tool_risks(self):
        from openmanus_max.security.permission import DEFAULT_TOOL_RISKS, ToolRisk
        self.assertEqual(DEFAULT_TOOL_RISKS["web_search"], ToolRisk.READ_ONLY)
        self.assertEqual(DEFAULT_TOOL_RISKS["shell_exec"], ToolRisk.EXECUTE)
        self.assertEqual(DEFAULT_TOOL_RISKS["computer_use"], ToolRisk.SYSTEM)

    def test_yolo_mode_no_approval(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        engine = PermissionEngine(mode=PermissionMode.YOLO)
        self.assertFalse(engine.needs_approval("shell_exec"))
        self.assertFalse(engine.needs_approval("computer_use"))
        self.assertFalse(engine.needs_approval("anything"))

    def test_standard_mode_approval(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        engine = PermissionEngine(mode=PermissionMode.STANDARD)
        self.assertFalse(engine.needs_approval("web_search"))   # READ_ONLY
        self.assertFalse(engine.needs_approval("file_editor"))  # WORKSPACE
        self.assertFalse(engine.needs_approval("python_execute"))  # EXECUTE
        self.assertTrue(engine.needs_approval("computer_use"))  # SYSTEM

    def test_strict_mode_approval(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        engine = PermissionEngine(mode=PermissionMode.STRICT)
        self.assertFalse(engine.needs_approval("web_search"))   # READ_ONLY
        self.assertTrue(engine.needs_approval("file_editor"))   # WORKSPACE
        self.assertTrue(engine.needs_approval("shell_exec"))    # EXECUTE

    def test_sandbox_mode_approval(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        engine = PermissionEngine(mode=PermissionMode.SANDBOX)
        self.assertFalse(engine.needs_approval("web_search"))
        self.assertTrue(engine.needs_approval("file_editor"))

    def test_path_policy_yolo(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        engine = PermissionEngine(mode=PermissionMode.YOLO)
        ok, _ = engine.check_path_write("/etc/passwd")
        self.assertTrue(ok)

    def test_path_policy_standard(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        engine = PermissionEngine(mode=PermissionMode.STANDARD, workspace_dir="/tmp/test-ws")
        ok, _ = engine.check_path_write("/tmp/test-ws/file.txt")
        self.assertTrue(ok)
        ok, _ = engine.check_path_write("/etc/passwd")
        self.assertFalse(ok)

    def test_path_policy_sandbox(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        engine = PermissionEngine(mode=PermissionMode.SANDBOX, workspace_dir="/tmp/test-ws")
        ok, _ = engine.check_path_read("/tmp/test-ws/data.csv")
        self.assertTrue(ok)
        ok, _ = engine.check_path_read("/etc/hosts")
        self.assertFalse(ok)

    def test_command_policy_blocks_dangerous(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        engine = PermissionEngine(mode=PermissionMode.STANDARD)
        ok, reason = engine.check_command("rm -rf /")
        self.assertFalse(ok)
        ok, reason = engine.check_command(":(){ :|:& };:")
        self.assertFalse(ok)

    def test_command_policy_allows_normal(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        engine = PermissionEngine(mode=PermissionMode.STANDARD)
        ok, _ = engine.check_command("ls -la /tmp")
        self.assertTrue(ok)
        ok, _ = engine.check_command("python3 script.py")
        self.assertTrue(ok)

    def test_session_approval_cache(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        engine = PermissionEngine(mode=PermissionMode.STRICT)
        self.assertTrue(engine.needs_approval("shell_exec"))
        engine._session_approved.add("shell_exec")
        self.assertFalse(engine.needs_approval("shell_exec"))
        engine.reset_session()
        self.assertTrue(engine.needs_approval("shell_exec"))

    def test_always_approval_cache(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        engine = PermissionEngine(mode=PermissionMode.STRICT)
        engine._always_approved.add("file_editor")
        self.assertFalse(engine.needs_approval("file_editor"))

    def test_check_and_approve_yolo(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        engine = PermissionEngine(mode=PermissionMode.YOLO)
        approved, reason = asyncio.get_event_loop().run_until_complete(
            engine.check_and_approve("shell_exec", "test")
        )
        self.assertTrue(approved)
        self.assertIn("YOLO", reason)

    def test_custom_tool_risks(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode, ToolRisk
        engine = PermissionEngine(
            mode=PermissionMode.STANDARD,
            tool_risks={"my_tool": ToolRisk.DESTRUCTIVE},
        )
        self.assertEqual(engine.get_tool_risk("my_tool"), ToolRisk.DESTRUCTIVE)
        self.assertTrue(engine.needs_approval("my_tool"))

    def test_status(self):
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        engine = PermissionEngine(mode=PermissionMode.STANDARD)
        status = engine.status
        self.assertEqual(status["mode"], "STANDARD")
        self.assertIn("workspace_dir", status)

    def test_approval_request_summary(self):
        from openmanus_max.security.permission import ApprovalRequest, ToolRisk
        req = ApprovalRequest(
            tool_name="shell_exec",
            risk_level=ToolRisk.EXECUTE,
            description="Run ls -la",
        )
        self.assertIn("shell_exec", req.summary)
        self.assertIn("EXECUTE", req.summary)


# ============================================================
# 2. Skill 系统测试
# ============================================================

class TestSkillSystem(unittest.TestCase):
    """Skill 系统测试"""

    def test_skill_trust_levels(self):
        from openmanus_max.skills.engine import SkillTrust
        self.assertEqual(SkillTrust.INSTALLED, 0)
        self.assertEqual(SkillTrust.TRUSTED, 1)
        self.assertTrue(SkillTrust.TRUSTED > SkillTrust.INSTALLED)

    def test_parse_skill_md_simple(self):
        from openmanus_max.skills.engine import SkillParser, SkillTrust
        content = """---
name: test-skill
version: "1.0.0"
description: A test skill
---
# Test Skill Instructions
Do something useful.
"""
        skill = SkillParser.parse(content, source_path="/test/SKILL.md", trust=SkillTrust.TRUSTED)
        self.assertEqual(skill.manifest.name, "test-skill")
        self.assertEqual(skill.manifest.version, "1.0.0")
        self.assertIn("Do something useful", skill.prompt_content)
        self.assertEqual(skill.trust, SkillTrust.TRUSTED)

    def test_parse_skill_md_no_frontmatter(self):
        from openmanus_max.skills.engine import SkillParser, SkillTrust
        content = "Just plain instructions"
        skill = SkillParser.parse(content, source_path="/test/myskill/SKILL.md", trust=SkillTrust.INSTALLED)
        self.assertEqual(skill.manifest.name, "myskill")
        self.assertEqual(skill.trust, SkillTrust.INSTALLED)

    def test_attenuate_no_skills(self):
        from openmanus_max.skills.engine import attenuate_tools
        result = attenuate_tools(["shell_exec", "web_search", "file_editor"], [])
        self.assertEqual(len(result.allowed_tools), 3)
        self.assertEqual(len(result.removed_tools), 0)

    def test_attenuate_trusted_skills(self):
        from openmanus_max.skills.engine import attenuate_tools, LoadedSkill, SkillManifest, SkillTrust
        skill = LoadedSkill(
            manifest=SkillManifest(name="trusted-skill"),
            prompt_content="instructions",
            trust=SkillTrust.TRUSTED,
            source_path="/test",
        )
        result = attenuate_tools(["shell_exec", "web_search"], [skill])
        self.assertEqual(len(result.allowed_tools), 2)  # No attenuation

    def test_attenuate_installed_skills(self):
        from openmanus_max.skills.engine import attenuate_tools, LoadedSkill, SkillManifest, SkillTrust
        skill = LoadedSkill(
            manifest=SkillManifest(name="external-skill"),
            prompt_content="instructions",
            trust=SkillTrust.INSTALLED,
            source_path="/test",
        )
        result = attenuate_tools(
            ["shell_exec", "web_search", "python_execute", "file_editor", "planning"],
            [skill],
        )
        # shell_exec, python_execute, file_editor should be removed
        self.assertIn("web_search", result.allowed_tools)
        self.assertIn("planning", result.allowed_tools)
        self.assertNotIn("shell_exec", result.allowed_tools)
        self.assertNotIn("python_execute", result.allowed_tools)
        self.assertTrue(len(result.removed_tools) > 0)

    def test_score_skill_keywords(self):
        from openmanus_max.skills.engine import score_skill, LoadedSkill, SkillManifest, SkillTrust, ActivationCriteria
        skill = LoadedSkill(
            manifest=SkillManifest(
                name="data-skill",
                activation=ActivationCriteria(keywords=["data", "analysis", "csv"]),
            ),
            prompt_content="instructions",
            trust=SkillTrust.TRUSTED,
            source_path="/test",
        )
        score = score_skill("Please analyze this CSV data", skill)
        self.assertGreater(score, 0)

    def test_score_skill_exclude(self):
        from openmanus_max.skills.engine import score_skill, LoadedSkill, SkillManifest, SkillTrust, ActivationCriteria
        skill = LoadedSkill(
            manifest=SkillManifest(
                name="data-skill",
                activation=ActivationCriteria(
                    keywords=["data"],
                    exclude_keywords=["delete"],
                ),
            ),
            prompt_content="instructions",
            trust=SkillTrust.TRUSTED,
            source_path="/test",
        )
        score = score_skill("delete all data", skill)
        self.assertEqual(score, 0.0)

    def test_select_skills(self):
        from openmanus_max.skills.engine import select_skills, LoadedSkill, SkillManifest, SkillTrust, ActivationCriteria
        skills = [
            LoadedSkill(
                manifest=SkillManifest(
                    name="web-skill",
                    activation=ActivationCriteria(keywords=["web", "website"]),
                ),
                prompt_content="web instructions",
                trust=SkillTrust.TRUSTED,
                source_path="/test",
            ),
            LoadedSkill(
                manifest=SkillManifest(
                    name="data-skill",
                    activation=ActivationCriteria(keywords=["data", "csv"]),
                ),
                prompt_content="data instructions",
                trust=SkillTrust.TRUSTED,
                source_path="/test",
            ),
        ]
        selected = select_skills("build a website", skills)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].manifest.name, "web-skill")

    def test_skill_registry_discover(self):
        from openmanus_max.skills.engine import SkillRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a skill directory
            skill_dir = os.path.join(tmpdir, "test-skill")
            os.makedirs(skill_dir)
            with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
                f.write("---\nname: test-skill\n---\nInstructions here")

            registry = SkillRegistry(user_skills_dir=tmpdir, installed_skills_dir="/nonexistent")
            skills = registry.discover_all()
            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].manifest.name, "test-skill")

    def test_skill_content_hash(self):
        from openmanus_max.skills.engine import LoadedSkill, SkillManifest, SkillTrust
        skill = LoadedSkill(
            manifest=SkillManifest(name="test"),
            prompt_content="hello world",
            trust=SkillTrust.TRUSTED,
            source_path="/test",
        )
        self.assertTrue(len(skill.content_hash) > 0)


# ============================================================
# 3. 执行引擎测试
# ============================================================

class TestExecutionEngine(unittest.TestCase):
    """双引擎执行器测试"""

    def test_exec_result_model(self):
        from openmanus_max.sandbox.executor import ExecResult
        r = ExecResult(exit_code=0, stdout="hello", backend="local")
        self.assertTrue(r.success)
        self.assertEqual(r.output, "hello")

    def test_exec_result_blocked(self):
        from openmanus_max.sandbox.executor import ExecResult
        r = ExecResult(blocked=True, block_reason="Dangerous command")
        self.assertFalse(r.success)
        self.assertIn("BLOCKED", r.output)

    def test_backend_resolution_auto_standard(self):
        from openmanus_max.sandbox.executor import ExecutionEngine, ExecutionBackend
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        perm = PermissionEngine(mode=PermissionMode.STANDARD)
        engine = ExecutionEngine(permission_engine=perm, backend=ExecutionBackend.AUTO)
        self.assertEqual(engine._resolve_backend(), "local")

    def test_backend_resolution_auto_sandbox(self):
        from openmanus_max.sandbox.executor import ExecutionEngine, ExecutionBackend
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        perm = PermissionEngine(mode=PermissionMode.SANDBOX)
        engine = ExecutionEngine(permission_engine=perm, backend=ExecutionBackend.AUTO)
        self.assertEqual(engine._resolve_backend(), "docker")

    def test_backend_resolution_forced(self):
        from openmanus_max.sandbox.executor import ExecutionEngine, ExecutionBackend
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        perm = PermissionEngine(mode=PermissionMode.YOLO)
        engine = ExecutionEngine(permission_engine=perm, backend=ExecutionBackend.DOCKER)
        self.assertEqual(engine._resolve_backend(), "docker")

    def test_execute_shell_yolo(self):
        from openmanus_max.sandbox.executor import ExecutionEngine, ExecutionBackend
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        perm = PermissionEngine(mode=PermissionMode.YOLO)
        engine = ExecutionEngine(permission_engine=perm, backend=ExecutionBackend.LOCAL)
        result = asyncio.get_event_loop().run_until_complete(
            engine.execute_shell("echo hello_world")
        )
        self.assertTrue(result.success)
        self.assertIn("hello_world", result.stdout)

    def test_execute_shell_blocked_command(self):
        from openmanus_max.sandbox.executor import ExecutionEngine, ExecutionBackend
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        perm = PermissionEngine(mode=PermissionMode.STANDARD)
        engine = ExecutionEngine(permission_engine=perm, backend=ExecutionBackend.LOCAL)
        result = asyncio.get_event_loop().run_until_complete(
            engine.execute_shell("rm -rf /")
        )
        self.assertTrue(result.blocked)

    def test_execute_python_yolo(self):
        from openmanus_max.sandbox.executor import ExecutionEngine, ExecutionBackend
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        perm = PermissionEngine(mode=PermissionMode.YOLO)
        engine = ExecutionEngine(permission_engine=perm, backend=ExecutionBackend.LOCAL)
        result = asyncio.get_event_loop().run_until_complete(
            engine.execute_python("print(2 + 3)")
        )
        self.assertTrue(result.success)
        self.assertIn("5", result.stdout)

    def test_engine_status(self):
        from openmanus_max.sandbox.executor import ExecutionEngine, ExecutionBackend
        from openmanus_max.security.permission import PermissionEngine, PermissionMode
        perm = PermissionEngine(mode=PermissionMode.STANDARD)
        engine = ExecutionEngine(permission_engine=perm)
        status = engine.status
        self.assertEqual(status["permission_mode"], "STANDARD")
        self.assertIn("backend", status)


# ============================================================
# 4. Routine 引擎测试
# ============================================================

class TestRoutineEngine(unittest.TestCase):
    """Routine 守护进程引擎测试"""

    def test_routine_model(self):
        from openmanus_max.scheduler.routine_engine import (
            Routine, RoutineTrigger, RoutineAction, TriggerType,
        )
        r = Routine(
            name="test-routine",
            trigger=RoutineTrigger(type=TriggerType.INTERVAL, interval_seconds=60),
            action=RoutineAction(prompt="Do something"),
        )
        self.assertTrue(len(r.id) > 0)
        self.assertEqual(r.name, "test-routine")
        self.assertEqual(r.trigger.type, TriggerType.INTERVAL)

    def test_cron_matches_wildcard(self):
        from openmanus_max.scheduler.routine_engine import cron_matches
        # "* * * * * *" should always match
        self.assertTrue(cron_matches("* * * * * *"))

    def test_cron_matches_specific(self):
        from openmanus_max.scheduler.routine_engine import cron_matches
        dt = datetime(2026, 3, 17, 9, 30, 0)  # Tuesday
        # second=0, minute=30, hour=9
        self.assertTrue(cron_matches("0 30 9 * * *", dt))
        self.assertFalse(cron_matches("0 0 10 * * *", dt))

    def test_cron_matches_step(self):
        from openmanus_max.scheduler.routine_engine import cron_matches
        dt = datetime(2026, 3, 17, 9, 0, 0)
        self.assertTrue(cron_matches("0 */30 * * * *", dt))  # minute 0 matches */30

    def test_cron_matches_range(self):
        from openmanus_max.scheduler.routine_engine import cron_matches
        dt = datetime(2026, 3, 17, 10, 0, 0)
        self.assertTrue(cron_matches("0 0 9-17 * * *", dt))
        dt2 = datetime(2026, 3, 17, 20, 0, 0)
        self.assertFalse(cron_matches("0 0 9-17 * * *", dt2))

    def test_routine_store_crud(self):
        from openmanus_max.scheduler.routine_engine import (
            Routine, RoutineStore, RoutineTrigger, RoutineAction, TriggerType,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_routines.db")
            store = RoutineStore(db_path=db_path)

            r = Routine(
                name="test",
                trigger=RoutineTrigger(type=TriggerType.INTERVAL, interval_seconds=300),
                action=RoutineAction(prompt="test prompt"),
            )
            store.save(r)

            loaded = store.load_all()
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].name, "test")

            store.delete(r.id)
            loaded = store.load_all()
            self.assertEqual(len(loaded), 0)

    def test_routine_store_log_run(self):
        from openmanus_max.scheduler.routine_engine import (
            Routine, RoutineStore, RoutineTrigger, RoutineAction, TriggerType,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_routines.db")
            store = RoutineStore(db_path=db_path)

            r = Routine(
                name="test",
                trigger=RoutineTrigger(type=TriggerType.INTERVAL, interval_seconds=300),
                action=RoutineAction(prompt="test"),
            )
            store.save(r)
            store.log_run(r.id, True, "output text")

            history = store.get_history(r.id)
            self.assertEqual(len(history), 1)
            self.assertTrue(history[0]["success"])

    def test_routine_engine_add_remove(self):
        from openmanus_max.scheduler.routine_engine import (
            Routine, RoutineEngine, RoutineStore, RoutineTrigger, RoutineAction, TriggerType,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_routines.db")
            store = RoutineStore(db_path=db_path)
            engine = RoutineEngine(store=store)

            r = Routine(
                name="my-routine",
                trigger=RoutineTrigger(type=TriggerType.CRON, expression="0 0 9 * * *"),
                action=RoutineAction(prompt="morning check"),
            )
            engine.add_routine(r)
            self.assertEqual(len(engine.list_routines()), 1)

            engine.remove_routine(r.id)
            self.assertEqual(len(engine.list_routines()), 0)

    def test_routine_engine_pause_resume(self):
        from openmanus_max.scheduler.routine_engine import (
            Routine, RoutineEngine, RoutineStore, RoutineTrigger, RoutineAction,
            TriggerType, RoutineStatus,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_routines.db")
            store = RoutineStore(db_path=db_path)
            engine = RoutineEngine(store=store)

            r = Routine(
                name="pausable",
                trigger=RoutineTrigger(type=TriggerType.INTERVAL, interval_seconds=60),
                action=RoutineAction(prompt="test"),
            )
            engine.add_routine(r)
            engine.pause_routine(r.id)
            self.assertEqual(engine.get_routine(r.id).status, RoutineStatus.PAUSED)
            engine.resume_routine(r.id)
            self.assertEqual(engine.get_routine(r.id).status, RoutineStatus.ACTIVE)


# ============================================================
# 5. 配置系统测试（更新后）
# ============================================================

class TestConfigUpdated(unittest.TestCase):
    """更新后的配置系统测试"""

    def test_config_has_permission(self):
        from openmanus_max.core.config import Config
        config = Config()
        self.assertEqual(config.permission.mode, "standard")
        self.assertEqual(config.permission.execution_backend, "auto")

    def test_config_has_skill(self):
        from openmanus_max.core.config import Config
        config = Config()
        self.assertTrue(config.skill.enabled)
        self.assertEqual(config.skill.max_skills_per_task, 3)

    def test_config_has_routine(self):
        from openmanus_max.core.config import Config
        config = Config()
        self.assertFalse(config.routine.enabled)
        self.assertEqual(config.routine.poll_interval, 1.0)

    def test_permission_workspace_follows_global(self):
        from openmanus_max.core.config import Config
        config = Config(workspace_dir="/tmp/test-global-ws")
        self.assertEqual(config.permission.workspace_dir, "/tmp/test-global-ws")


# ============================================================
# 6. 已有模块回归测试
# ============================================================

class TestExistingModules(unittest.TestCase):
    """确保已有模块在更新后仍正常工作"""

    def test_schema_imports(self):
        from openmanus_max.core.schema import Message, ToolResult, TaskNode, TaskGraph, AgentState
        msg = Message(role="user", content="hello")
        self.assertEqual(msg.role, "user")

    def test_llm_init(self):
        from openmanus_max.core.llm import LLM
        llm = LLM()
        self.assertIsNotNone(llm)

    def test_tool_collection(self):
        from openmanus_max.tool.base import ToolCollection
        from openmanus_max.tool.builtin.terminate import Terminate
        tc = ToolCollection(Terminate())
        self.assertEqual(len(tc), 1)
        self.assertIn("terminate", tc)

    def test_hierarchical_memory(self):
        from openmanus_max.memory.hierarchical import HierarchicalMemory
        from openmanus_max.core.schema import Message
        mem = HierarchicalMemory(working_memory_size=5)
        mem.add_message(Message(role="user", content="test"))
        self.assertEqual(len(mem.working_messages), 1)

    def test_dag_scheduler_imports(self):
        from openmanus_max.flow.dag_scheduler import DAGScheduler
        self.assertIsNotNone(DAGScheduler)

    def test_manus_agent_creation(self):
        from openmanus_max.agent.manus import ManusAgent
        agent = ManusAgent()
        self.assertIsNotNone(agent)
        self.assertTrue(len(agent.tools) > 0)
        self.assertIsNotNone(agent.permission)

    def test_manus_agent_has_permission(self):
        from openmanus_max.agent.manus import ManusAgent
        from openmanus_max.security.permission import PermissionMode
        agent = ManusAgent()
        self.assertEqual(agent.permission.mode, PermissionMode.STANDARD)

    def test_manus_agent_status_info(self):
        from openmanus_max.agent.manus import ManusAgent
        agent = ManusAgent()
        info = agent.status_info
        self.assertIn("permission_mode", info)
        self.assertIn("active_skills", info)
        self.assertIn("tool_count", info)


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
