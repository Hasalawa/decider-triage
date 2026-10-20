import pytest

from triage_agent.decider_client import DeciderClient
from triage_agent.triage import Route, TriagePolicy, decide_route, triage

P = TriagePolicy()


def route(**over):
    base = dict(
        category="how_to",
        category_confidence=0.9,
        urgency=0.5,
        wants_human=0.1,
        severe=0.1,
        complex_=0.1,
        policy=P,
    )
    base.update(over)
    return decide_route(**base)[0]


def test_routine_goes_cheap():
    assert route() is Route.AGENT_CHEAP


def test_human_request_wins_over_everything():
    assert route(wants_human=0.9, category="spam") is Route.ESCALATE


def test_severe_incident_escalates():
    assert route(severe=0.9) is Route.ESCALATE
    assert route(severe=0.2) is Route.AGENT_CHEAP


def test_critical_urgency_escalates():
    assert route(urgency=3.0) is Route.ESCALATE


def test_confident_spam_dropped_unsure_spam_not():
    assert route(category="spam", category_confidence=0.95) is Route.DROP
    assert route(category="spam", category_confidence=0.6) is Route.AGENT_CHEAP


def test_low_confidence_escalates():
    assert route(category_confidence=0.3) is Route.ESCALATE


def test_money_and_complexity_use_strong_model():
    assert route(category="refund_request") is Route.AGENT_STRONG
    assert route(complex_=0.8) is Route.AGENT_STRONG


def test_thresholds_are_policy_not_model():
    strict = TriagePolicy(wants_human_min=0.05)
    assert (
        decide_route(
            category="how_to",
            category_confidence=0.9,
            urgency=0.1,
            wants_human=0.1,
            severe=0.1,
            complex_=0.1,
            policy=strict,
        )[0]
        is Route.ESCALATE
    )


def test_triage_end_to_end_with_stub_server(decider):
    d = triage(decider, "I would like a refund for order A1001")
    assert d.route is Route.AGENT_STRONG
    assert d.category == "refund_request"
    assert triage(decider, "You are a winner! Claim your free gift, click here").route is Route.DROP


def test_empty_message_rejected(decider):
    with pytest.raises(ValueError):
        triage(decider, "  ")


def test_decider_down_fails_safe_to_human():
    d = triage(DeciderClient("http://127.0.0.1:1", timeout=0.3), "how do I log in?")
    assert d.route is Route.ESCALATE
    assert "unavailable" in d.reason
