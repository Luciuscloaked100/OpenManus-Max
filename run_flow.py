import asyncio
import time

from openmanus_max.agent.manus import ManusAgent
from openmanus_max.core.logger import get_logger
from openmanus_max.flow.dag_scheduler import DAGScheduler

logger = get_logger("openmanus_max")


async def run_flow():
    agent = ManusAgent()

    try:
        prompt = input("Enter your prompt: ")
        if not prompt.strip():
            logger.warning("Empty prompt provided.")
            return

        scheduler = DAGScheduler()

        logger.info("Processing your request with DAG planning...")
        try:
            start_time = time.time()
            result = await asyncio.wait_for(
                scheduler.execute(prompt),
                timeout=3600,
            )
            elapsed_time = time.time() - start_time
            logger.info(f"Request processed in {elapsed_time:.2f} seconds")
            if result:
                print(result)
        except asyncio.TimeoutError:
            logger.error("Request processing timed out after 1 hour")
            logger.info(
                "Operation terminated due to timeout. Please try a simpler request."
            )
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user.")
    except Exception as e:
        logger.error(f"Error: {str(e)}")


if __name__ == "__main__":
    asyncio.run(run_flow())
