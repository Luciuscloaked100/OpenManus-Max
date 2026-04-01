import argparse
import asyncio

from openmanus_max.agent.manus import ManusAgent
from openmanus_max.core.logger import get_logger
from openmanus_max.tool.mcp.client import MCPClient

logger = get_logger("openmanus_max")


async def run_mcp():
    parser = argparse.ArgumentParser(description="Run OpenManus-Max with MCP server connection")
    parser.add_argument(
        "--server",
        type=str,
        required=True,
        help="MCP server command (e.g., 'npx -y @modelcontextprotocol/server-filesystem /tmp')",
    )
    parser.add_argument(
        "--prompt", type=str, required=False, help="Input prompt for the agent"
    )
    args = parser.parse_args()

    agent = ManusAgent()

    try:
        # Connect to MCP server
        client = MCPClient(server_command=args.server)
        logger.info(f"Connecting to MCP server: {args.server}")
        tools = await client.connect()
        logger.info(f"Discovered {len(tools)} tools from MCP server")

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
    except Exception as e:
        logger.error(f"Error: {str(e)}")


if __name__ == "__main__":
    asyncio.run(run_mcp())
