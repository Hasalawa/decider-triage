"""The reusable Decider 2B decision pattern: a grounding guard for tool calls.

Copy this file into your own Strands agent. It has three parts:

1. The typed questions: two yes/no (``noul``) questions, ``args_grounded`` and ``premature``.
2. The wiring: a Strands ``InterventionHandler`` whose ``before_tool_call`` runs right
   before any tool executes, asks the decider, and returns a typed action.
3. The policy: two thresholds (``grounded_min``, ``premature_max``) that you own in code.

Verdicts:
    Proceed  -> the call runs
    Guide    -> the model gets its turn back with feedback ("ask the customer first")
    Deny     -> only when the decider is unreachable and ``fail_open`` is False

Use it on your own agent::

    from triage_agent.decider_client import DeciderClient
    from triage_agent.decision_pattern import GroundingGuard

    guard = GroundingGuard(DeciderClient(), tools={"issue_refund"})
    agent = Agent(model=..., tools=[issue_refund], interventions=[guard])

Why ``Guide`` and not ``Deny``: a denied call just fails. A guided call hands the model
back its turn, so it asks the user for the missing detail instead of giving up.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from strands.interventions import Deny, Guide, InterventionHandler, Proceed

from .decider_client import DeciderClient, DeciderError, Noul

QUESTIONS = {
    "args_grounded": Noul(
        "Are the tool's argument values grounded in facts the user actually provided?",
        true="every argument value was stated by the user or returned by a tool",
        false="at least one argument value was guessed, invented or assumed by the assistant",
    ),
    "premature": Noul(
        "Is it premature to call this tool now, before clarifying with the user?",
        true="the assistant should ask a clarifying question before calling the tool",
        false="there is nothing left to clarify",
    ),
}


@dataclass(frozen=True)
class GuardRecord:
    """One decision, kept so a run can report what the guard did."""

    tool: str
    grounded: float | None
    premature: float | None
    action: str  # proceed | guide | deny | skipped
    latency_ms: float


def _blocks(message: dict) -> Iterable[dict]:
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                yield block


def build_evidence(messages: list[dict]) -> str:
    """What the assistant is allowed to rely on: user text and tool results.

    The assistant's own text is left out on purpose. If it says "let me check Seattle"
    that would make a guessed argument look grounded.
    """
    lines: list[str] = []
    for message in messages:
        if message.get("role") != "user":
            continue
        for block in _blocks(message):
            if "text" in block:
                lines.append(f"user: {block['text']}")
            result = block.get("toolResult")
            if isinstance(result, dict):
                for part in result.get("content", []):
                    if "text" in part:
                        lines.append(f"tool result: {part['text']}")
                    elif "json" in part:
                        lines.append(f"tool result: {json.dumps(part['json'], sort_keys=True)}")
    return "\n".join(lines)


def build_state(messages: list[dict], tool_name: str, tool_input: Any) -> str:
    evidence = build_evidence(messages) or "user: (no user text)"
    args = json.dumps(tool_input, sort_keys=True, default=str)
    return f"{evidence}\n\nassistant proposes: {tool_name}({args})"


class GroundingGuard(InterventionHandler):
    """Blocks tool calls built on guessed arguments, using Decider 2B as the judge."""

    name = "decider-grounding-guard"

    def __init__(
        self,
        decider: DeciderClient,
        *,
        tools: Iterable[str] | None = None,
        grounded_min: float = 0.5,
        premature_max: float = 0.5,
        fail_open: bool = False,
    ) -> None:
        self._decider = decider
        self._tools = frozenset(tools) if tools is not None else None
        self.grounded_min = grounded_min
        self.premature_max = premature_max
        self.fail_open = fail_open
        self.records: list[GuardRecord] = []

    def before_tool_call(self, event, **kwargs):
        tool_name = event.tool_use["name"]
        if self._tools is not None and tool_name not in self._tools:
            self.records.append(GuardRecord(tool_name, None, None, "skipped", 0.0))
            return Proceed()

        state = build_state(event.agent.messages, tool_name, event.tool_use.get("input", {}))
        try:
            decision = self._decider.ask(state, QUESTIONS)
        except DeciderError as exc:
            if self.fail_open:
                self.records.append(GuardRecord(tool_name, None, None, "proceed", 0.0))
                return Proceed(reason=f"decider unavailable, failing open: {exc}")
            self.records.append(GuardRecord(tool_name, None, None, "deny", 0.0))
            return Deny(reason=f"safety check unavailable, not running {tool_name}: {exc}")

        grounded = decision.noul("args_grounded")
        premature = decision.noul("premature")

        if grounded < self.grounded_min:
            action, feedback = (
                "guide",
                (
                    f"Do not call {tool_name} yet. Some of its arguments were not stated by the "
                    "customer or returned by a tool. Ask the customer for the missing details "
                    "(for example the order ID) and try again."
                ),
            )
        elif premature >= self.premature_max:
            action, feedback = (
                "guide",
                (
                    f"It is too early to call {tool_name}. Ask the customer a clarifying "
                    "question first."
                ),
            )
        else:
            action, feedback = "proceed", ""

        self.records.append(
            GuardRecord(tool_name, grounded, premature, action, decision.latency_ms)
        )
        if action == "guide":
            return Guide(
                feedback=feedback,
                reason=f"args_grounded={grounded:.2f} premature={premature:.2f}",
            )
        return Proceed(reason=f"args_grounded={grounded:.2f} premature={premature:.2f}")
