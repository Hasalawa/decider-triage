import httpx
import pytest

from triage_agent.decider_client import Choice, DeciderClient, DeciderError, Noul, Score


def test_ask_parses_all_three_types(decider):
    d = decider.ask(
        "Customer support message:\nI want a refund for order A1001",
        {
            "cat": Choice("kind?", {"refund_request": "money back", "spam": "junk"}),
            "urg": Score("urgent?", ("low", "high")),
            "human": Noul("Does the customer ask for a human?"),
        },
    )
    assert d.choice("cat").label == "refund_request"
    assert 0 <= d.choice("cat").confidence <= 1
    assert d.score("urg").value >= 0
    assert 0 <= d.noul("human") <= 1
    assert d.latency_ms >= 0


def test_wrong_type_access_raises(decider):
    d = decider.ask("hello there", {"q": Noul("yes?")})
    with pytest.raises(DeciderError):
        d.choice("q")


def test_empty_state_rejected(decider):
    with pytest.raises(DeciderError):
        decider.ask("   ", {"q": Noul("yes?")})


def test_unreachable_server_raises():
    client = DeciderClient("http://127.0.0.1:1", timeout=0.5)
    with pytest.raises(DeciderError):
        client.ask("hi", {"q": Noul("yes?")})


def test_http_error_becomes_decider_error():
    transport = httpx.MockTransport(lambda req: httpx.Response(422, text="bad"))
    client = DeciderClient("http://x", http=httpx.Client(transport=transport))
    with pytest.raises(DeciderError, match="422"):
        client.ask("hi", {"q": Noul("yes?")})


def test_malformed_answer_raises():
    body = {"answers": {"q": {"type": "choice", "choice": "a"}}}  # no confidence
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    client = DeciderClient("http://x", http=httpx.Client(transport=transport))
    with pytest.raises(DeciderError, match="malformed"):
        client.ask("hi", {"q": Choice("pick", {"a": "A", "b": "B"})})


def test_missing_answer_raises():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"answers": {}}))
    client = DeciderClient("http://x", http=httpx.Client(transport=transport))
    with pytest.raises(DeciderError, match="missing"):
        client.ask("hi", {"q": Noul("yes?")})


def test_request_shape_matches_decider_api():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        import json

        seen["path"] = req.url.path
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"answers": {"q": {"type": "noul", "noul": 0.7}}})

    client = DeciderClient(
        "http://x/v1/systemone", http=httpx.Client(transport=httpx.MockTransport(handler))
    )
    client.ask("state", {"q": Noul("is it?", true="yes it is")})
    assert seen["path"] == "/v1/systemone"
    assert seen["body"]["questions"]["q"] == {
        "type": "noul",
        "instructions": "is it?",
        "criteria": {"true": "yes it is"},
    }
