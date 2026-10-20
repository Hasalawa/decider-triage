"""A small local web page for trying the triage agent without a terminal.

    python -m triage_agent.ui                # decider on http://127.0.0.1:8099
    python -m triage_agent.ui --url http://127.0.0.1:8099 --port 8088

Open http://127.0.0.1:8088. Type a message, press Triage. Tick "Also run the Bedrock agent"
to run the full flow (needs AWS credentials with Bedrock access); otherwise only the Decider
is used and no AWS call is made. Standard library only, it listens on localhost.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from . import backend
from .agent import CHEAP_MODEL, STRONG_MODEL
from .decider_client import DeciderClient, DeciderError
from .pipeline import SupportPipeline

MAX_BODY = 20_000


def _no_llm(model_id, guard, message):
    return "(Bedrock agent not run: tick the box to run it)"


def run_once(pipeline_factory, message: str, use_llm: bool) -> dict:
    """Run one message and return a JSON-ready dict. Pure enough to test without HTTP."""
    pipeline = pipeline_factory(use_llm)
    outcome = pipeline.handle(message)
    return {
        "triage": outcome.decision.to_dict(),
        "reply": outcome.reply,
        "model_id": outcome.model_id,
        "llm_calls": outcome.llm_calls,
        "guard": [asdict(r) for r in outcome.guard_records],
        "refunds": list(backend.BACKEND.refunds),
        "human_queue": list(backend.BACKEND.human_queue),
        "ran_llm": use_llm and outcome.llm_calls > 0,
    }


def make_handler(decider: DeciderClient):
    def factory(use_llm: bool) -> SupportPipeline:
        kwargs = {} if use_llm else {"runner": _no_llm}
        return SupportPipeline(
            decider, cheap_model=CHEAP_MODEL, strong_model=STRONG_MODEL, **kwargs
        )

    page = resources.files("triage_agent.data").joinpath("ui.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(body)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, json.dumps(payload).encode())

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html"):
                self._send(200, page, "text/html; charset=utf-8")
            elif self.path == "/api/health":
                try:
                    self._json(200, decider.health())
                except DeciderError as exc:
                    self._json(503, {"error": str(exc)})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path == "/api/reset":
                backend.reset_backend()
                return self._json(200, {"ok": True})
            if self.path != "/api/handle":
                return self._json(404, {"error": "not found"})
            try:
                length = int(self.headers.get("content-length", "0"))
                if length > MAX_BODY:
                    return self._json(413, {"error": "message too long"})
                data = json.loads(self.rfile.read(length))
                message = str(data["message"]).strip()
                if not message:
                    raise ValueError("empty message")
            except (ValueError, KeyError, TypeError):
                return self._json(400, {"error": "send JSON like {'message': '...'}"})
            use_llm = bool(data.get("use_llm"))
            try:
                self._json(200, run_once(factory, message, use_llm))
            except Exception as exc:  # show Bedrock/credential problems on the page
                self._json(502, {"error": f"{type(exc).__name__}: {exc}"})

        def log_message(self, *args):
            pass

    return Handler


def make_server(decider: DeciderClient, host: str = "127.0.0.1", port: int = 8088):
    return ThreadingHTTPServer((host, port), make_handler(decider))


def main() -> None:
    parser = argparse.ArgumentParser(description="Local web page for the triage agent.")
    parser.add_argument(
        "--url", default=None, help="decider URL (default STRANDS_DECIDER_URL or :8099)"
    )
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()
    server = make_server(DeciderClient(args.url), port=args.port)
    print(f"Open http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
