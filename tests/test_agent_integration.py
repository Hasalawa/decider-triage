"""Runs the guard inside a real Strands Agent loop with a scripted model (no AWS)."""

import pytest

pytest.importorskip("strands")

from strands import Agent  # noqa: E402
from strands.models import Model  # noqa: E402

from triage_agent import backend  # noqa: E402
from triage_agent.decision_pattern import GroundingGuard  # noqa: E402
from triage_agent.tools import ALL_TOOLS  # noqa: E402


class ScriptedModel(Model):
    """Turn 1 proposes a refund with a given order id, turn 2 answers in text."""

    def __init__(self, order_id):
        self.order_id = order_id
        self.calls = 0

    def update_config(self, **kw):
        pass

    def get_config(self):
        return {}

    async def structured_output(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kw):
        self.calls += 1
        yield {"messageStart": {"role": "assistant"}}
        # Call the tool only until a tool result (or guidance) is in the history.
        if self.calls == 1:
            yield {
                "contentBlockStart": {
                    "start": {"toolUse": {"toolUseId": "tu1", "name": "issue_refund"}}
                }
            }
            args = f'{{"order_id": "{self.order_id}", "amount": 10.0, "reason": "damaged"}}'
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": args}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockDelta": {"delta": {"text": "done"}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "metrics": {"latencyMs": 1},
            }
        }


def run(decider, user_text, order_id):
    guard = GroundingGuard(decider, tools={"issue_refund"})
    agent = Agent(
        model=ScriptedModel(order_id),
        tools=ALL_TOOLS,
        interventions=[guard],
        callback_handler=None,
    )
    agent(user_text)
    return guard


def test_guessed_order_id_is_stopped_before_the_refund_runs(decider):
    guard = run(decider, "I want a refund, my mouse broke", "A9999")
    assert guard.records and guard.records[0].action == "guide"
    assert backend.BACKEND.refunds == []


def test_grounded_order_id_lets_the_refund_run(decider):
    guard = run(decider, "Refund order A1001 please, my mouse broke", "A1001")
    assert guard.records[0].action == "proceed"
    assert len(backend.BACKEND.refunds) == 1
