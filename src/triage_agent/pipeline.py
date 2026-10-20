"""End to end flow: triage with the decider, then act on the route.

message -> triage (Decider 2B, ~100 ms, no LLM)
             |-- DROP          -> nothing sent
             |-- ESCALATE      -> human queue, no LLM call
             |-- AGENT_CHEAP   -> small Bedrock model + grounding guard
             '-- AGENT_STRONG  -> stronger Bedrock model + grounding guard
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from . import backend
from .decider_client import DeciderClient
from .decision_pattern import GroundingGuard, GuardRecord
from .triage import Route, TriageDecision, TriagePolicy, triage

# An "agent runner" takes (model_id, guard, message) and returns the reply text.
# The default one calls Bedrock through Strands; tests and the offline demo inject a stub.
AgentRunner = Callable[[str, GroundingGuard, str], str]


@dataclass
class Outcome:
    decision: TriageDecision
    reply: str | None
    model_id: str | None
    llm_calls: int
    guard_records: list[GuardRecord] = field(default_factory=list)


def bedrock_runner(model_id: str, guard: GroundingGuard, message: str) -> str:
    from .agent import build_agent  # imported lazily so tests never need AWS

    agent = build_agent(model_id, guard)
    return str(agent(message)).strip()


class SupportPipeline:
    def __init__(
        self,
        decider: DeciderClient,
        *,
        cheap_model: str,
        strong_model: str,
        policy: TriagePolicy | None = None,
        runner: AgentRunner = bedrock_runner,
        guard_fail_open: bool = False,
    ) -> None:
        self.decider = decider
        self.cheap_model = cheap_model
        self.strong_model = strong_model
        self.policy = policy or TriagePolicy()
        self.runner = runner
        self.guard_fail_open = guard_fail_open

    def handle(self, message: str) -> Outcome:
        decision = triage(self.decider, message, self.policy)

        if decision.route is Route.DROP:
            return Outcome(decision, reply=None, model_id=None, llm_calls=0)

        if decision.route is Route.ESCALATE:
            backend.BACKEND.escalate(decision.reason, message)
            reply = "Thanks for reaching out. A member of our team will contact you shortly."
            return Outcome(decision, reply=reply, model_id=None, llm_calls=0)

        model_id = self.strong_model if decision.route is Route.AGENT_STRONG else self.cheap_model
        from .agent import build_guard

        guard = build_guard(self.decider)
        guard.fail_open = self.guard_fail_open
        reply = self.runner(model_id, guard, message)
        return Outcome(
            decision,
            reply=reply,
            model_id=model_id,
            llm_calls=1,
            guard_records=list(guard.records),
        )
