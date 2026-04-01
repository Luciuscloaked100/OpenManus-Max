"""
OpenManus-Max CLI
命令行交互入口 - 支持交互模式、单任务、DAG 规划、A2A 服务器、Routine 守护进程
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Optional

from openmanus_max.core.config import Config, get_config, set_config
from openmanus_max.core.logger import get_logger, logger


BANNER = r"""
  ___                   __  __                          __  __
 / _ \ _ __   ___ _ __ |  \/  | __ _ _ __  _   _ ___  |  \/  | __ ___  __
| | | | '_ \ / _ \ '_ \| |\/| |/ _` | '_ \| | | / __| | |\/| |/ _` \ \/ /
| |_| | |_) |  __/ | | | |  | | (_| | | | | |_| \__ \ | |  | | (_| |>  <
 \___/| .__/ \___|_| |_|_|  |_|\__,_|_| |_|\__,_|___/ |_|  |_|\__,_/_/\_\
      |_|
            Advanced Autonomous AI Agent Framework
            20+ Tools | DAG Scheduler | A2A Protocol | Permission Engine
"""


def create_full_agent(permission_mode: Optional[str] = None):
    """创建完整功能的 ManusAgent（包含所有高级工具 + 权限引擎 + Skill 系统）"""
    from openmanus_max.agent.manus import ManusAgent
    from openmanus_max.core.llm import LLM
    from openmanus_max.media.generator import ImageGenerator, TTSGenerator
    from openmanus_max.security.permission import PermissionEngine, PermissionMode
    from openmanus_max.slides.generator import SlidesGenerator
    from openmanus_max.tool.base import ToolCollection
    from openmanus_max.tool.builtin.parallel import ParallelMap
    from openmanus_max.tool.builtin.schedule import ScheduleTool
    from openmanus_max.webdev.scaffold import WebScaffold

    config = get_config()

    # 权限引擎
    mode_map = {
        "yolo": PermissionMode.YOLO,
        "standard": PermissionMode.STANDARD,
        "strict": PermissionMode.STRICT,
        "sandbox": PermissionMode.SANDBOX,
    }
    mode_str = permission_mode or config.permission.mode
    perm_mode = mode_map.get(mode_str.lower(), PermissionMode.STANDARD)
    perm_engine = PermissionEngine(
        mode=perm_mode,
        workspace_dir=config.permission.workspace_dir or config.workspace_dir,
    )

    llm = LLM()
    extra_tools = ToolCollection(
        ParallelMap(llm=llm),
        ScheduleTool(),
        ImageGenerator(),
        TTSGenerator(),
        SlidesGenerator(llm=llm),
        WebScaffold(),
    )

    agent = ManusAgent(
        llm=llm,
        extra_tools=extra_tools,
        permission_engine=perm_engine,
    )
    return agent


async def connect_mcp_servers(agent, mcp_configs: list):
    """连接 MCP Server 并注册工具到 Agent"""
    from openmanus_max.tool.mcp.client import MCPManager

    manager = MCPManager()
    for config in mcp_configs:
        try:
            tools = await manager.add_server(**config)
            for tool in tools:
                agent.tools.register(tool)
            logger.info(f"Connected MCP server: {config['name']} ({len(tools)} tools)")
        except Exception as e:
            logger.warning(f"Failed to connect MCP server {config.get('name', '?')}: {e}")
    return manager


async def interactive_mode(config_path: Optional[str] = None, permission_mode: Optional[str] = None):
    """交互式对话模式"""
    if config_path:
        set_config(Config.load(config_path))

    print(BANNER)
    config = get_config()
    perm_mode = permission_mode or config.permission.mode
    print(f"  Model:      {config.llm.model}")
    print(f"  Workspace:  {config.workspace_dir}")
    print(f"  Permission: {perm_mode.upper()}")
    print(f"  Max steps:  {config.max_steps}")
    print(f"\n  Type your task and press Enter. Type 'quit' to exit.")
    print(f"  Commands: /status, /tools, /memory, /skills, /permission, /routines, /help\n")

    agent = create_full_agent(permission_mode)

    while True:
        try:
            task = input("\n[You] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not task:
            continue
        if task.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        # 内置命令
        if task.startswith("/"):
            await _handle_command(task, agent)
            continue

        print(f"\n[Agent] Working on: {task[:80]}...\n")
        try:
            result = await agent.run(task)
            print(f"\n{'='*60}")
            print(f"[Result]\n{result}")
            print(f"{'='*60}")
            print(f"\nToken usage: {agent.llm.token_usage}")
        except Exception as e:
            print(f"\n[Error] {e}")
            logger.exception("Task execution failed")

        # 重置 agent 状态以便处理下一个任务
        agent = create_full_agent(permission_mode)


async def _handle_command(cmd: str, agent):
    """处理内置命令"""
    if cmd == "/tools":
        print("\nRegistered tools:")
        for name in sorted(agent.tools._tools.keys()):
            tool = agent.tools.get(name)
            desc = tool.description[:60] if tool else "?"
            print(f"  - {name}: {desc}")
        print(f"\nTotal: {len(agent.tools)} tools")

    elif cmd == "/memory":
        if agent.memory:
            stats = agent.memory.stats
            print(f"\nMemory stats: {stats}")
        else:
            print("\nNo memory system active")

    elif cmd == "/status":
        info = agent.status_info
        print(f"\n  Agent:      {info['name']}")
        print(f"  State:      {info['state']}")
        print(f"  Steps:      {info['current_step']}")
        print(f"  Tools:      {info['tool_count']}")
        print(f"  Permission: {info['permission_mode']}")
        print(f"  Skills:     {info['skill_count']} loaded, {len(info['active_skills'])} active")
        print(f"  Token usage: {agent.llm.token_usage}")

    elif cmd == "/permission":
        status = agent.permission.status
        print(f"\n  Mode:             {status['mode']}")
        print(f"  Workspace:        {status['workspace_dir']}")
        print(f"  Session approved: {status['session_approved'] or '(none)'}")
        print(f"  Always approved:  {status['always_approved'] or '(none)'}")
        print(f"  Writable paths:   {status['writable_paths']}")

    elif cmd == "/skills":
        if agent.skill_registry:
            skills = agent.skill_registry.list_skills()
            if skills:
                print("\nLoaded skills:")
                for s in skills:
                    trust = "TRUSTED" if s.trust == 1 else "INSTALLED"
                    print(f"  [{trust}] {s.manifest.name} v{s.manifest.version}: {s.manifest.description[:50]}")
            else:
                print("\nNo skills loaded. Add SKILL.md files to ~/.openmanus-max/skills/")
        else:
            print("\nSkill system is disabled")

    elif cmd == "/routines":
        try:
            from openmanus_max.scheduler.routine_engine import RoutineEngine, RoutineStore
            store = RoutineStore()
            routines = store.load_all()
            if routines:
                print("\nRegistered routines:")
                for r in routines:
                    print(f"  [{r.status.value}] {r.name} ({r.trigger.type.value}: {r.trigger.expression or r.trigger.interval_seconds}s) runs: {r.run_count}")
            else:
                print("\nNo routines registered")
        except Exception as e:
            print(f"\nError loading routines: {e}")

    elif cmd.startswith("/mode "):
        new_mode = cmd.split(" ", 1)[1].strip().lower()
        if new_mode in ("yolo", "standard", "strict", "sandbox"):
            from openmanus_max.security.permission import PermissionEngine, PermissionMode
            mode_map = {"yolo": PermissionMode.YOLO, "standard": PermissionMode.STANDARD,
                        "strict": PermissionMode.STRICT, "sandbox": PermissionMode.SANDBOX}
            agent.permission = PermissionEngine(
                mode=mode_map[new_mode],
                workspace_dir=agent.permission.workspace_dir,
            )
            print(f"\n  Permission mode changed to: {new_mode.upper()}")
        else:
            print(f"\n  Invalid mode. Choose: yolo, standard, strict, sandbox")

    elif cmd == "/help":
        print("\nCommands:")
        print("  /tools       - List all registered tools")
        print("  /memory      - Show memory statistics")
        print("  /status      - Show agent status")
        print("  /permission  - Show permission engine status")
        print("  /skills      - List loaded skills")
        print("  /routines    - List registered routines")
        print("  /mode <mode> - Switch permission mode (yolo/standard/strict/sandbox)")
        print("  /help        - Show this help")
        print("  quit         - Exit")
    else:
        print(f"Unknown command: {cmd}. Type /help for available commands.")


async def single_task_mode(task: str, config_path: Optional[str] = None, permission_mode: Optional[str] = None):
    """单任务执行模式"""
    if config_path:
        set_config(Config.load(config_path))

    agent = create_full_agent(permission_mode)
    result = await agent.run(task)
    print(result)
    return result


async def dag_mode(goal: str, config_path: Optional[str] = None, permission_mode: Optional[str] = None):
    """DAG 模式：将任务分解为 DAG 并执行"""
    if config_path:
        set_config(Config.load(config_path))

    from openmanus_max.core.llm import LLM
    from openmanus_max.flow.dag_scheduler import DAGScheduler

    llm = LLM()
    scheduler = DAGScheduler(llm=llm)

    factory = lambda: create_full_agent(permission_mode)
    scheduler.set_default_agent(factory)
    scheduler.register_agent("general", factory)
    scheduler.register_agent("code", factory)
    scheduler.register_agent("browser", factory)
    scheduler.register_agent("data_analysis", factory)
    scheduler.register_agent("research", factory)

    print(f"Planning DAG for: {goal}\n")
    graph = await scheduler.plan(goal)
    print(graph.format_status())
    print()

    graph = await scheduler.execute(graph)
    print(f"\n{'='*60}")
    print("Final DAG Status:")
    print(graph.format_status())
    return graph


async def routine_mode(config_path: Optional[str] = None, permission_mode: Optional[str] = None):
    """Routine 守护进程模式"""
    if config_path:
        set_config(Config.load(config_path))

    from openmanus_max.scheduler.routine_engine import RoutineEngine, RoutineStore

    config = get_config()
    store = RoutineStore(db_path=config.routine.db_path)

    async def agent_executor(prompt: str, max_steps: int = 10) -> str:
        agent = create_full_agent(permission_mode)
        return await agent.run(prompt)

    engine = RoutineEngine(store=store, poll_interval=config.routine.poll_interval)
    print(f"Starting Routine Engine...")
    print(f"  DB: {config.routine.db_path}")
    print(f"  Poll interval: {config.routine.poll_interval}s")

    routines = store.load_all()
    print(f"  Loaded {len(routines)} routines")
    for r in routines:
        print(f"    [{r.status.value}] {r.name} ({r.trigger.type.value})")

    print(f"\nRoutine engine running. Press Ctrl+C to stop.\n")
    await engine.start(executor=agent_executor)

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        await engine.stop()
        print("\nRoutine engine stopped.")


async def a2a_server_mode(host: str = "0.0.0.0", port: int = 5000):
    """A2A 协议服务器模式"""
    from openmanus_max.a2a.server import A2AServer

    server = A2AServer(
        agent_factory=create_full_agent,
        host=host,
        port=port,
    )
    print(f"Starting A2A server at http://{host}:{port}")
    print(f"Agent card: http://{host}:{port}/.well-known/agent.json")
    print(f"Health check: http://{host}:{port}/health")
    await server.start()


def main():
    parser = argparse.ArgumentParser(
        description="OpenManus-Max - Advanced Autonomous AI Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Permission Modes:
  --mode yolo       Full unrestricted access (no confirmations)
  --mode standard   High-risk operations need approval (default)
  --mode strict     All write/execute operations need approval
  --mode sandbox    Isolated execution in Docker containers

Examples:
  openmanus-max                              # Interactive mode (standard)
  openmanus-max --mode yolo                  # Full access mode
  openmanus-max --mode sandbox               # Sandboxed mode
  openmanus-max -t "Write a Python script"   # Single task
  openmanus-max --dag "Build a website"      # DAG planning mode
  openmanus-max --serve                      # A2A server mode
  openmanus-max --routine                    # Routine daemon mode
  openmanus-max -c config.toml              # With config file
        """,
    )
    parser.add_argument("-t", "--task", type=str, help="Execute a single task")
    parser.add_argument("--dag", type=str, help="Execute task in DAG planning mode")
    parser.add_argument("--serve", action="store_true", help="Start A2A protocol server")
    parser.add_argument("--routine", action="store_true", help="Start Routine daemon engine")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="A2A server host")
    parser.add_argument("--port", type=int, default=5000, help="A2A server port")
    parser.add_argument("-c", "--config", type=str, help="Path to config TOML file")
    parser.add_argument("--model", type=str, help="Override LLM model name")
    parser.add_argument("--mode", type=str, choices=["yolo", "standard", "strict", "sandbox"],
                        help="Permission mode")
    parser.add_argument("--max-steps", type=int, help="Override max steps")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        get_logger(level="DEBUG")

    # 加载配置
    if args.config:
        set_config(Config.load(args.config))

    # 应用命令行覆盖
    config = get_config()
    if args.model:
        config.llm.model = args.model
    if args.max_steps:
        config.max_steps = args.max_steps
    if args.mode:
        config.permission.mode = args.mode
    set_config(config)

    permission_mode = args.mode

    if args.task:
        asyncio.run(single_task_mode(args.task, args.config, permission_mode))
    elif args.dag:
        asyncio.run(dag_mode(args.dag, args.config, permission_mode))
    elif args.serve:
        asyncio.run(a2a_server_mode(args.host, args.port))
    elif args.routine:
        asyncio.run(routine_mode(args.config, permission_mode))
    else:
        asyncio.run(interactive_mode(args.config, permission_mode))


if __name__ == "__main__":
    main()
