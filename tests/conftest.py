import threading

import pytest

from triage_agent import backend
from triage_agent.decider_client import DeciderClient
from triage_agent.fake_decider import make_server


@pytest.fixture(scope="session")
def fake_url():
    server = make_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def decider(fake_url):
    client = DeciderClient(fake_url)
    yield client
    client.close()


@pytest.fixture(autouse=True)
def fresh_backend():
    return backend.reset_backend()
