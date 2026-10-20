from triage_agent import backend
from triage_agent.backend import SupportBackend
from triage_agent.bench import load_set, run_bench
from triage_agent.pipeline import SupportPipeline


def make(decider, replies):
    def runner(model_id, guard, message):
        replies.append(model_id)
        return "stub reply"

    return SupportPipeline(decider, cheap_model="cheap", strong_model="strong", runner=runner)


def test_spam_dropped_with_no_llm(decider):
    used = []
    out = make(decider, used).handle("Earn crypto fast, click here to start.")
    assert out.reply is None and out.llm_calls == 0 and used == []


def test_human_request_escalates_with_no_llm(decider):
    used = []
    out = make(decider, used).handle("I need to speak to a real person about my account.")
    assert out.llm_calls == 0 and used == []
    assert len(backend.BACKEND.human_queue) == 1


def test_routine_uses_cheap_and_refund_uses_strong(decider):
    used = []
    p = make(decider, used)
    p.handle("How do I turn on dark mode?")
    p.handle("I would like a refund for order A1001.")
    assert used == ["cheap", "strong"]


def test_backend_refund_rules():
    b = SupportBackend()
    assert "error" in b.issue_refund("A1001", 999, "x")
    assert "error" in b.issue_refund("NOPE", 1, "x")
    assert b.issue_refund("a1001", 40.0, "damaged")["amount"] == 40.0
    assert "error" in b.issue_refund("A1001", 5.0, "x")  # only 2.50 left


def test_bench_on_stub_reports_consistent_numbers(decider):
    r = run_bench(decider, load_set("dev"), price_cheap=0.001, price_strong=0.01)
    assert r.total == len(load_set("dev")) == 24
    assert r.model_name == "fake-keyword-decider"
    assert r.llm_calls < r.total  # drop and escalate never reach an LLM
    assert r.cost_routed < r.cost_always_strong
    assert r.accuracy >= 0.9, r.mistakes
