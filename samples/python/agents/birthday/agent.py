import json
import random
from typing import Any, AsyncIterable, Dict, Optional
from common.client import A2AClient, A2ACardResolver, RemoteAgentConnections
import uuid
from common.types import (
    AgentCard,
    Message,
    TaskState,
    Task,
    TaskSendParams,
    TextPart,
    DataPart,
    Part,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
)
import asyncio

from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig
from google.adk.tools import LongRunningFunctionTool
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Local cache of created request_ids for demo purposes.
request_ids = set()

class BirthdayAgent:
  """An agent that handles planning birthday parties."""

  SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

  def __init__(self, remote_agents):
    agent_cards = [A2ACardResolver(ra).get_agent_card() for ra in remote_agents]
    self.cards = agent_cards
    self.remote_agent_connections = {card.name: A2AClient(card) for card in agent_cards}
    self._agent = self._build_agent(agent_cards=agent_cards)
    self._user_id = "remote_agent"
    self._runner = Runner(
        app_name=self._agent.name,
        agent=self._agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )

  def invoke(self, query, session_id) -> str:
    session = self._runner.session_service.get_session(
        app_name=self._agent.name, user_id=self._user_id, session_id=session_id
    )
    content = types.Content(
        role="user", parts=[types.Part.from_text(text=query)]
    )
    if session is None:
      session = self._runner.session_service.create_session(
          app_name=self._agent.name,
          user_id=self._user_id,
          state={},
          session_id=session_id,
      )
    events = list(self._runner.run(
        user_id=self._user_id, session_id=session.id, new_message=content
    ))
    if not events or not events[-1].content or not events[-1].content.parts:
      return ""
    return "\n".join([p.text for p in events[-1].content.parts if p.text])

  async def stream(self, query, session_id) -> AsyncIterable[Dict[str, Any]]:
    session = self._runner.session_service.get_session(
        app_name=self._agent.name, user_id=self._user_id, session_id=session_id
    )
    content = types.Content(
        role="user", parts=[types.Part.from_text(text=query)]
    )
    if session is None:
      session = self._runner.session_service.create_session(
          app_name=self._agent.name,
          user_id=self._user_id,
          state={},
          session_id=session_id,
      )

    request_queue = LiveRequestQueue()
    request_queue.send_content(content)
    # request_queue.close()
    async for event in self._runner.run_async(
      user_id=self._user_id,
      session_id=session_id,
      new_message=content
    ):
      # TODO: Process the event into a task update event. Need to understand ADK events better to know
      # how to interpret them.
      print(f"======= EVENT =========\n{event}\n========")
      response = ""
      if (
          event.content
          and event.content.parts
          and event.content.parts[0].text
      ):
        response = "\n".join([p.text for p in event.content.parts if p.text])
      elif (
          event.content
          and event.content.parts
          and any([True for p in event.content.parts if p.function_response])):
        response = next((p.function_response.model_dump() for p in event.content.parts))
      if event.is_final_response():
        request_queue.close()
      key = "content" if event.is_final_response() else "updates"
      yield {
          "is_task_complete": event.is_final_response(),
          key: response,
      }

  def _build_agent(self, agent_cards) -> LlmAgent:
    """Builds the LLM agent for the birthday agent."""
    agent_info = []
    for ra in agent_cards:
      agent_info.append(json.dumps({"name": ra.name, "description": ra.description}))
    agents_desc = '\n'.join(agent_info)
    return LlmAgent(
        model="gemini-2.0-flash-exp",
        name="birthday_agent",
        description=(
            "This agent can help you plan a fun birthday party. It helps think of ideas and can"
             " even schedule the event on your calendar."
        ),
        instruction=f"""
    You are an agent who helps plan birthday parties.

    You should provide input on:
    - Fun activities to plan for the party
    - Good days of the week to hold the party, depending on the age of the attendees and conditions.
    - Good times of day to hold the party

    Use the tools available to you when appropriate, such as for checking available dates
    or the weather on certain days.

    You have access to the following agents to help you perform your work:
    {agents_desc}

    You may use these agents to help perform tasks that users request from you.
    You interact with agents by sending them tasks using the `send_task` tool.
    """,
        tools=[
          LongRunningFunctionTool(func=self.send_task),
          self.check_weather,
        ],
    )
  
  def check_weather(self, date: str) -> Dict[str, Any]:
    """Check the weather for a given date."""
    return {"weather": "sunny", "date": date}

  async def send_task(
      self,
      agent_name: str,
      message: str,
      tool_context: ToolContext):
    """Sends a task either streaming (if supported) or non-streaming.

    This will send a message to the remote agent named agent_name.

    Args:
      agent_name: The name of the agent to send the task to.
      message: The message to send to the agent for the task.
      tool_context: The tool context this method runs in.

    Yields:
      A dictionary of JSON data.
    """
    if agent_name not in self.remote_agent_connections:
      raise ValueError(f"Agent {agent_name} not found")
    state = tool_context.state
    state['agent'] = agent_name
    client = self.remote_agent_connections[agent_name]
    if not client:
      raise ValueError(f"Client not available for {agent_name}")
    if 'task_id' in state:
      taskId = state['task_id']
    else:
      taskId = str(uuid.uuid4())
    sessionId = tool_context._invocation_context.session.id
    messageId = ""
    metadata = {}
    if 'input_message_metadata' in state:
      metadata.update(**state['input_message_metadata'])
      if 'message_id' in state['input_message_metadata']:
        messageId = state['input_message_metadata']['message_id']
    if not messageId:
      messageId = str(uuid.uuid4())
    metadata.update(**{'conversation_id': sessionId, 'message_id': messageId})
    request: TaskSendParams = TaskSendParams(
        id=taskId,
        sessionId=sessionId,
        message=Message(
            role="user",
            parts=[TextPart(text=message)],
            metadata=metadata,
        ),
        acceptedOutputModes=["text", "text/plain", "image/png"],
        # pushNotification=None,
        metadata={'conversation_id': sessionId},
    )
    response = []
    async for sresp in client.send_task_streaming(request.model_dump()):
      result = sresp.result
      print(f"++++++++++++Received CALENDAR AGENT update+++++\n{sresp}")
      if hasattr(result, "status") and result.status.state == TaskState.INPUT_REQUIRED:
        # Force user input back
        tool_context.actions.skip_summarization = True
        tool_context.actions.escalate = True
        return convert_parts(result.status.message.parts, tool_context)
      if hasattr(result, "status") and result.status.message:
        response.extend(convert_parts(result.status.message.parts, tool_context))
      if hasattr(result, "attributes"):
        for artifact in result.artifacts:
          response.extend(convert_parts(artifact.parts, tool_context))
    return response

def convert_parts(parts: list[Part], tool_context: ToolContext):
    rval = []
    for p in parts:
        rval.append(convert_part(p, tool_context))
    return rval


def convert_part(part: Part, tool_context: ToolContext):
    if part.type == 'text':
        return part.text
    if part.type == 'data':
        return part.data
    if part.type == 'file':
        # Repackage A2A FilePart to google.genai Blob
        # Currently not considering plain text as files
        file_id = part.file.name
        file_bytes = base64.b64decode(part.file.bytes)
        file_part = types.Part(
            inline_data=types.Blob(
                mime_type=part.file.mimeType, data=file_bytes
            )
        )
        tool_context.save_artifact(file_id, file_part)
        tool_context.actions.skip_summarization = True
        tool_context.actions.escalate = True
        return DataPart(data={'artifact-file-id': file_id})
    return f'Unknown type: {p.type}'