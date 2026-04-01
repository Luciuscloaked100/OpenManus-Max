"""
OpenManus-Max 入口文件
支持 CLI 交互模式和 IPC 模式（供 Electron 桌面端调用）
"""

import argparse
import asyncio

from openmanus_max.core.logger import get_logger

logger = get_logger("openmanus_max")


async def main():
    parser = argparse.ArgumentParser(description="Run OpenManus-Max agent")
    parser.add_argument("--prompt", type=str, required=False, help="Input prompt for the agent")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["yolo", "standard", "strict", "sandbox", "ipc"],
        default="standard",
        help="Run mode: permission mode or 'ipc' for Electron desktop communication",
    )
    args = parser.parse_args()

    if args.mode == "ipc":
        # IPC 模式：通过 stdin/stdout JSON 协议与 Electron 桌面端通信
        from openmanus_max.cli import create_full_agent
        from openmanus_max.ipc_server import run_ipc_server

        await run_ipc_server(agent_factory=create_full_agent)
    else:
        # 普通 CLI 模式
        from openmanus_max.agent.manus import ManusAgent

        agent = ManusAgent()

        try:
            prompt = args.prompt if args.prompt else input("Enter your prompt: ")
            if not prompt.strip():
                logger.warning("Empty prompt provided.")
                return

            logger.info("Processing your request...")
            result = await agent.run(prompt)
            logger.info("Request processing completed.")
            if result:
                print(result)
        except KeyboardInterrupt:
            logger.warning("Operation interrupted.")


if __name__ == "__main__":
    asyncio.run(main())
