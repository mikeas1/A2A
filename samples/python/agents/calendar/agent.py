import asyncio
import json
import random
from typing import Any, AsyncIterable, Dict, Optional
from helpers import get_auth_request_function_call, get_auth_config
from common.types import AgentCard
from urllib.parse import urlparse, parse_qs
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.events import Event
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.google_api_tool import calendar_tool_set
from google.genai import types

# Local cache of created request_ids for demo purposes.
request_ids = set()

class CalendarAgent:
  """An agent that manages a calendar."""

  SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
  _card: AgentCard
  _waiting_sessions: Dict[str, asyncio.Future]

  def __init__(self, card, client_id, client_secret):
    self._agent = self._build_agent()
    self._user_id = "remote_agent"
    self._card = card
    self._waiting_sessions = {}
    print(f"USING OAUTH CREDS:\n client_id = {client_id}\nclient_secret={client_secret}")
    calendar_tool_set.configure_auth(client_id=client_id, client_secret=client_secret)
    self._runner = Runner(
        app_name=self._agent.name,
        agent=self._agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )

  async def handle_auth(self, state, auth_response_uri):
    waiting_func_details = self._waiting_sessions[state]
    auth_config = waiting_func_details["auth_config"]
    oauth2_obj = auth_config["exchanged_auth_credential"]["oauth2"]
    oauth2_obj["auth_response_uri"] = auth_response_uri
    oauth2_obj["redirect_uri"] = waiting_func_details["redirect_uri"]
    auth_content = types.Content(
      role='user',
      parts=[
          types.Part(
              function_response=types.FunctionResponse(
                  id=waiting_func_details["auth_request_function_call_id"],
                  name='adk_request_credential',
                  response=auth_config
              )
          )
      ],
    )
    session_id = waiting_func_details["session_id"]
    # Go run the model. This is problematic, but without immediately running the model,
    # ADK seems to ignore the FunctionResponse event.
    # This is going to complete running the function, process the response with the LLM, then
    # ignore the results.
    async for event in self._process_events(session_id, auth_content):
      print(f"====== AUTH EVENT ======\n{event}\n========")
    del self._waiting_sessions[state]
    return

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
    """Process a request and stream results out."""
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
    async for event in self._process_events(session_id, content):
      yield event

  async def _process_events(self, session_id, content) -> AsyncIterable[Dict[str, Any]]:
    auth_request_function_call_id, auth_config, redirect_uri, state_token, future = None, None, None, None, None
    async for event in self._runner.run_async(
        user_id=self._user_id, session_id=session_id, new_message=content
    ):
      print(f"====== EVENT =====\n{event}\n=========")
      if (auth_request_function_call := get_auth_request_function_call(event)):
          print("Found an authenticated function call requirement")
          self._debug_auth(session_id)
          if not (auth_request_function_call_id := auth_request_function_call.id):
            raise ValueError(f'Cannot get function call id from function call: {auth_request_function_call}')
          auth_config = get_auth_config(auth_request_function_call)
          if not (auth_config and auth_request_function_call_id):
            raise ValueError(f'Cannot get auth config from function call: {auth_request_function_call}')
          base_auth_uri = auth_config["exchanged_auth_credential"]["oauth2"]["auth_uri"]
          if not base_auth_uri:
            raise ValueError(f'Cannot get auth uri from auth config: {auth_config}')
          redirect_uri = f'{self._card.url}authenticate'
          parsed_auth_uri = urlparse(base_auth_uri)
          query_params_dict = parse_qs(parsed_auth_uri.query)
          state_token = query_params_dict['state'][0]
          auth_request_uri = base_auth_uri + f'&redirect_uri={redirect_uri}'
          # Map auth state token to the suspended function call.
          self._waiting_sessions[state_token] = {
            "auth_request_function_call_id": auth_request_function_call_id,
            "auth_config": auth_config,
            "redirect_uri": redirect_uri,
            "session_id": session_id,
            "invocation_id": event.invocation_id,
          }
          yield {
            "is_task_complete": False,
            "input_required": True,
            "updates": f"Authorization is required to continue. Visit {auth_request_uri}",
          }
          break
          
      elif event.is_final_response():
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
        yield {
            "is_task_complete": True,
            "content": response,
        }
      else:
        yield {
          "is_task_complete": False,
          "updates": "Processing the request...",
        }

  def _debug_auth(self, session_id):
    session = self._runner.session_service.get_session(app_name=self._agent.name, user_id=self._user_id, session_id=session_id)
    for event in session.events:
      print(f"====== PAST EVENT =====\n{event}\n=========")

  def _build_agent(self) -> LlmAgent:
    """Builds the LLM agent for the calendar agent."""
    return LlmAgent(
        model="gemini-2.0-flash-001",
        name="calendar_agent",
        description=(
            "This agent helps manage a user's calendar by checking availability and booking events"
        ),
        instruction="""
    You are an agent that helps manage a user's calendar. You have access to tools to interact with
    the calendar, which you should use to help service requests from the user.

    Format requests to interact with the calendar using well-formed RFC3339 dates.

    Today is Monday, May 5, 2025.
    """,
        tools=calendar_tool_set.get_tools(),
    )

