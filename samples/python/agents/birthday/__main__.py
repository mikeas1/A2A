from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from task_manager import AgentTaskManager
from agent import BirthdayAgent
import click
import os
import logging
import traceback
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option("--host", default="localhost")
@click.option("--port", default=10008)
def main(host, port):
    try:
        # Check for API key only if Vertex AI is not configured
        if not os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            if not os.getenv("GOOGLE_API_KEY"):
                raise MissingAPIKeyError(
                    "GOOGLE_API_KEY environment variable not set and GOOGLE_GENAI_USE_VERTEXAI is not TRUE."
                )
        
        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
            id="generate_events",
            name="Event Planner",
            description="Think of fun, age-appropriate events to do during a birthday party.",
            tags=["birthday", "creative"],
            examples=["What kind of things should we do during the party?"],
        )
        skill2 = AgentSkill(
            id="plan_dates",
            name="Date Planner",
            description="Find good dates when the birthday party could be held.",
            tags=["birthday", "creative"],
            examples=["When should I hold the party?"],
        )
        agent_card = AgentCard(
            name="Birthday Agent",
            description="This agent helps plan super fun birthday parties.",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=BirthdayAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=BirthdayAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill, skill2],
        )
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=BirthdayAgent(["http://localhost:10007"])),
            host=host,
            port=port,
        )
        server.start()
    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        traceback.print_exc()
        exit(1)
    
if __name__ == "__main__":
    main()
