import json
import random
from typing import Any, AsyncIterable, Dict, Optional
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Local cache of created request_ids for demo purposes.
request_ids = set()


def create_request_form(date: Optional[str] = None, amount: Optional[str] = None, purpose: Optional[str] = None) -> dict[str, Any]:
  """
   Create a request form for the employee to fill out.
   
   Args:
       date (str): The date of the request. Can be an empty string.
       amount (str): The requested amount. Can be an empty string.
       purpose (str): The purpose of the request. Can be an empty string.
       
   Returns:
       dict[str, Any]: A dictionary containing the request form data.
   """
  request_id = "request_id_" + str(random.randint(1000000, 9999999))
  request_ids.add(request_id)
  return {
      "request_id": request_id,
      "date": "<transaction date>" if not date else date,
      "amount": "<transaction dollar amount>" if not amount else amount,
      "purpose": "<business justification/purpose of the transaction>" if not purpose else purpose,
  }

def return_form(
    form_request: dict[str, Any],    
    tool_context: ToolContext,
    instructions: Optional[str] = None) -> dict[str, Any]:
  """
   Returns a structured json object indicating a form to complete.
   
   Args:
       form_request (dict[str, Any]): The request form data.
       tool_context (ToolContext): The context in which the tool operates.
       instructions (str): Instructions for processing the form. Can be an empty string.       
       
   Returns:
       dict[str, Any]: A JSON dictionary for the form response.
   """  
  if isinstance(form_request, str):
    form_request = json.loads(form_request)

  tool_context.actions.skip_summarization = True
  tool_context.actions.escalate = True
  form_dict = {
      'type': 'form',
      'form': {
        'type': 'object',
        'properties': {
            'date': {
                'type': 'string',
                'format': 'date',
                'description': 'Date of expense',
                'title': 'Date',
            },
            'amount': {
                'type': 'string',
                'format': 'number',
                'description': 'Amount of expense',
                'title': 'Amount',
            },
            'purpose': {
                'type': 'string',
                'description': 'Purpose of expense',
                'title': 'Purpose',
            },
            'request_id': {
                'type': 'string',
                'description': 'Request id',
                'title': 'Request ID',
            },
        },
        'required': list(form_request.keys()),
      },
      'form_data': form_request,
      'instructions': instructions,
  }
  return json.dumps(form_dict)

def reimburse(request_id: str) -> dict[str, Any]:
  """Reimburse the amount of money to the employee for a given request_id."""
  if request_id not in request_ids:
    return {"request_id": request_id, "status": "Error: Invalid request_id."}
  return {"request_id": request_id, "status": "approved"}


class ReimbursementAgent:
  """An agent that handles reimbursement requests."""

  SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

  def __init__(self):
    self._agent = self._build_agent()
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
    async for event in self._runner.run_async(
        user_id=self._user_id, session_id=session.id, new_message=content
    ):
      if event.is_final_response():
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
            "updates": "Processing the reimbursement request...",
        }

  def _build_agent(self) -> LlmAgent:
    """Builds the LLM agent for the birthday agent."""
    return LlmAgent(
        model="gemini-2.0-flash-001",
        name="birthday_agent",
        description=(
            "This agent can help you plan a fun birthday party. It helps think of ideas and can"
             " even schedule the event on your calendar."
        ),
        instruction="""
    You are an agent who helps plan birthday parties.

    You should provide input on:
    - Fun activities to plan for the party
    - Good days of the week to hold the party, depending on the age of the attendees
    - Good times of day to hold the party

    You have access to an 
    """,
        tools=[
            create_request_form,
            reimburse,
            return_form,
        ],
    )

