from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from task_manager import AgentTaskManager
from agent import CalendarAgent
import click
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option("--host", default="localhost")
@click.option("--port", default=10007)
def main(host, port):
    try:
        # Check for API key only if Vertex AI is not configured
        if not os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            if not os.getenv("GOOGLE_API_KEY"):
                raise MissingAPIKeyError(
                    "GOOGLE_API_KEY environment variable not set and GOOGLE_GENAI_USE_VERTEXAI is not TRUE."
                )
        print(f"STARTUP: {os.getenv('AGENT_CLIENT_ID')}")
        capabilities = AgentCapabilities(streaming=True)
        availability_skill = AgentSkill(
            id="check_availability",
            name="Check Availability Tool",
            description="Helps check availability based on events booked on a user's calendar.",
            tags=["calendar"],
            examples=["What times am I free for coffee tomorrow?"],
        )
        booking_skill = AgentSkill(
            id="book_event",
            name="Book Event Tool",
            description="Helps book events on a user's calendar",
            tags=["calendar"],
            examples=["I'm having drinks with Mike this friday at 3pm."],
        )
        agent_card = AgentCard(
            name="Calendar Agent",
            description="This agent helps manage a user's calendar by booking events and checking availability.",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=CalendarAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=CalendarAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[availability_skill, booking_skill],
        )
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=CalendarAgent(card=agent_card, client_id=os.getenv("AGENT_CLIENT_ID"), client_secret=os.getenv("AGENT_CLIENT_SECRET"))),
            host=host,
            port=port,
        )
        server.start()
    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)
    
if __name__ == "__main__":
    main()
