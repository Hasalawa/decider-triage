from types import SimpleNamespace

from strands.interventions import Deny, Guide, Proceed

from triage_agent.decider_client import DeciderClient
from triage_agent.decision_pattern import GroundingGuard, build_evidence, build_state


def event(messages, tool="issue_refund", args=None):
    return SimpleNamespace(
        agent=SimpleNamespace(messages=messages),
        tool_use={"name": tool, "input": args or {}, "toolUseId": "t1"},
    )


def user(text):
    return {"role": "user", "content": [{"text": text}]}


def test_evidence_keeps_user_and_tool_results_but_not_assistant_text():
    messages = [
        user("refund please"),
        {"role": "assistant", "content": [{"text": "Let me refund A9999"}]},
        {"role": "user", "content": [{"toolResult": {"content": [{"json": {"id": "A1001"}}]}}]},
    ]
    evidence = build_evidence(messages)
    assert "A9999" not in evidence
    assert "user: refund please" in evidence
    assert "A1001" in evidence


def test_state_ends_with_the_proposed_call():
    state = build_state([user("hi")], "issue_refund", {"order_id": "A1001"})
    assert state.endswith('assistant proposes: issue_refund({"order_id": "A1001"})')


def test_guesses_are_guided_back(decider):
    guard = GroundingGuard(decider)
    result = guard.before_tool_call(
        event([user("I want a refund")], args={"order_id": "A1001", "amount": 10})
    )
    assert isinstance(result, Guide)
    assert guard.records[-1].action == "guide"


def test_grounded_call_proceeds(decider):
    guard = GroundingGuard(decider)
    result = guard.before_tool_call(
        event([user("refund order A1001 please")], args={"order_id": "A1001", "amount": 10})
    )
    assert isinstance(result, Proceed)
    assert guard.records[-1].action == "proceed"


def test_unguarded_tools_skip_the_decider(decider):
    guard = GroundingGuard(decider, tools={"issue_refund"})
    result = guard.before_tool_call(event([user("hi")], tool="lookup_order"))
    assert isinstance(result, Proceed)
    assert guard.records[-1].action == "skipped"


def test_decider_down_denies_by_default_and_can_fail_open():
    dead = DeciderClient("http://127.0.0.1:1", timeout=0.3)
    ev = event([user("refund A1001")], args={"order_id": "A1001"})
    assert isinstance(GroundingGuard(dead).before_tool_call(ev), Deny)
    assert isinstance(GroundingGuard(dead, fail_open=True).before_tool_call(ev), Proceed)
