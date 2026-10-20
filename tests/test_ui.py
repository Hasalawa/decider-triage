import json
import threading
import urllib.request

import pytest

from triage_agent import ui
from triage_agent.decider_client import DeciderClient


@pytest.fixture
def server(fake_url):
    srv = ui.make_server(DeciderClient(fake_url), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def post(url, payload):
    req = urllib.request.Request(
        url, json.dumps(payload).encode(), {"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_page_is_served(server):
    with urllib.request.urlopen(server + "/") as r:
        assert r.status == 200 and b"Decider Triage" in r.read()


def test_triage_without_llm_makes_no_bedrock_call(server):
    status, body = post(server + "/api/handle", {"message": "How do I turn on dark mode?"})
    assert status == 200
    assert body["triage"]["route"] == "agent_cheap"
    assert body["ran_llm"] is False


def test_spam_dropped_and_human_queue_counts(server):
    _, spam = post(server + "/api/handle", {"message": "Earn crypto fast, click here to start."})
    assert spam["triage"]["route"] == "drop" and spam["reply"] is None
    _, human = post(server + "/api/handle", {"message": "I want to speak with a human agent now."})
    assert human["triage"]["route"] == "escalate" and len(human["human_queue"]) == 1
    post(server + "/api/reset", {})
    _, again = post(server + "/api/handle", {"message": "I want to speak with a human agent now."})
    assert len(again["human_queue"]) == 1  # reset cleared the first one


def test_bad_requests(server):
    assert post(server + "/api/handle", {"nope": 1})[0] == 400
    assert post(server + "/api/handle", {"message": "   "})[0] == 400


def test_run_once_propagates_runner_errors(fake_url):
    def boom(use_llm):
        raise RuntimeError("no AWS credentials")

    with pytest.raises(RuntimeError):
        ui.run_once(boom, "hi", True)
