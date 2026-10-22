"""Builds the Bedrock-backed Strands agent with the Decider guard attached."""

from __future__ import annotations

import os

from strands import Agent

from .decider_client import DeciderClient
from .decision_pattern import GroundingGuard
from .tools import ALL_TOOLS, GUARDED_TOOLS

# Override with env vars; check that these model IDs are enabled in your Bedrock region.
CHEAP_MODEL = os.environ.get(
    "TRIAGE_CHEAP_MODEL", "global.anthropic.claude-haiku-4-5-20251001-v1:0"
)
STRONG_MODEL = os.environ.get(
    "TRIAGE_STRONG_MODEL", "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
)

SYSTEM_PROMPT = """You are a customer support agent for an online hardware shop.
Use the tools to look up orders, issue refunds and create tickets.
Never invent an order ID or an amount: if the customer has not given you a detail you need,
ask for it. Keep replies short and friendly. If you cannot resolve something, use
escalate_to_human."""


def build_guard(decider: DeciderClient) -> GroundingGuard:
    return GroundingGuard(decider, tools=GUARDED_TOOLS)


def build_agent(model_id: str, guard: GroundingGuard) -> Agent:
    return Agent(
        model=model_id,
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        interventions=[guard],
        callback_handler=None,
    )
