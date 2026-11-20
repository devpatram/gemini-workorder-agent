"""Work-order assistant: an Agent Development Kit (ADK) agent on Gemini.

A maintenance planner asks about an asset ("what keeps failing on Crimper 1?") and the agent answers from the
work-order history through four tools, citing order numbers. The tools are in tools.py; this file only wires them
to the model. `adk web` and `adk run` look for `root_agent` here.
"""
import os

from google.adk.agents import Agent
from google.adk.models import Gemini

from .tools import TOOLS

MODEL = os.getenv("MODEL", "gemini-3.5-flash")
# Where the model is called. "global" works the same in Cloud Shell and once deployed to a region.
MODEL_LOCATION = os.getenv("MODEL_LOCATION", "global")

INSTRUCTION = (
    "You help maintenance planners understand equipment history. "
    "Answer only from the tools: list_assets, find_work_orders, failure_summary and breakdown_intervals. "
    "Always cite the work order numbers you used, like (WO4105, WO4122). "
    "If a tool returns not_found, say so and suggest list_assets. If it returns ambiguous, ask which asset. "
    "Never invent orders, dates, hours or costs, and never estimate a number the tools did not return. "
    "breakdown_intervals is a rough calendar average, not a reliability model; say so when you use it. "
    "Keep answers short: the answer first, then the evidence."
)

root_agent = Agent(
    name="work_order_assistant",
    model=Gemini(model=MODEL, client_kwargs={"location": MODEL_LOCATION}),
    description="Answers maintenance questions about an asset from its work-order history.",
    instruction=INSTRUCTION,
    tools=TOOLS,
)
