"""A keyword stand-in for the Decider server. FOR CI AND OFFLINE DEMOS ONLY.

It speaks the same ``POST /v1/systemone`` wire format as ``strands-decider serve`` so the
whole pipeline can be exercised without downloading a 2B model. It does NOT use a model:
answers come from keyword rules, so any accuracy or latency number measured against it says
nothing about Strands Decider 2B. Real numbers need the real server.

    triage-fake-decider --port 8099
"""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_SPAM = re.compile(
    r"\b(winner|free gift|crypto|click here|limited offer|seo services|viagra)\b", re.I
)
_REFUND = re.compile(r"\b(refund|money back|charge me back|return)\b", re.I)
_BILLING = re.compile(r"\b(invoice|billed|billing|charged twice|payment method|receipt)\b", re.I)
_BUG = re.compile(r"\b(crash|bug|error|broken|not working|freezes|glitch)\b", re.I)
_ACCESS = re.compile(r"\b(log ?in|password|locked out|2fa|sign in|cannot access)\b", re.I)
_HUMAN = re.compile(
    r"\b(human|real person|lawyer|legal action|sue|chargeback|speak to a manager)\b", re.I
)
_URGENT = re.compile(r"\b(urgent|asap|immediately|right now|outage|down for)\b", re.I)
_CRITICAL = re.compile(r"\b(outage|security breach|hacked|data leak)\b", re.I)
_COMPLEX = re.compile(r"\b(and also|multiple|several|both|three|four|since last)\b", re.I)
_ORDER_ID = re.compile(r"\b[A-Z]\d{4}\b")


def _text(state: str) -> str:
    return state


def _category(text: str) -> tuple[str, float]:
    if _SPAM.search(text):
        return "spam", 0.95
    for pattern, label in (
        (_REFUND, "refund_request"),
        (_BILLING, "billing_issue"),
        (_BUG, "bug_report"),
        (_ACCESS, "account_access"),
    ):
        if pattern.search(text):
            return label, 0.88
    if "?" in text or re.search(r"\bhow (do|can|to)\b", text, re.I):
        return "how_to", 0.82
    return "how_to", 0.30  # nothing matched: low confidence on purpose


def _noul(question: str, state: str) -> float:
    q = question.lower()
    if "ask for a human" in q:
        return 0.93 if _HUMAN.search(state) else 0.05
    if "several steps" in q:
        return 0.85 if _COMPLEX.search(state) else 0.12
    if "grounded" in q:
        # The guard puts "assistant proposes: tool({...})" last. Grounded when an order ID
        # appears in the proposed args AND in the evidence above it.
        evidence, _, proposal = state.rpartition("assistant proposes:")
        proposed = set(_ORDER_ID.findall(proposal))
        if not proposed:
            return 0.80
        return 0.90 if proposed <= set(_ORDER_ID.findall(evidence)) else 0.08
    if "premature" in q:
        evidence, _, proposal = state.rpartition("assistant proposes:")
        proposed = set(_ORDER_ID.findall(proposal))
        if proposed and not proposed <= set(_ORDER_ID.findall(evidence)):
            return 0.80
        return 0.10
    return 0.5


def answer(request: dict) -> dict:
    state = str(request.get("state", ""))
    answers: dict[str, dict] = {}
    for name, q in request["questions"].items():
        kind = q["type"]
        if kind == "noul":
            answers[name] = {"type": "noul", "noul": _noul(str(q["instructions"]), state)}
        elif kind == "choice":
            label, conf = _category(state)
            options = list(q["criteria"])
            if label not in options:
                label = options[0]
            rest = (1 - conf) / max(len(options) - 1, 1)
            probs = {o: (conf if o == label else rest) for o in options}
            answers[name] = {
                "type": "choice",
                "choice": label,
                "probabilities": probs,
                "confidence": conf,
            }
        else:
            levels = q["criteria"]
            if _CRITICAL.search(state):
                value = 3.0
            elif _URGENT.search(state):
                value = 2.0
            else:
                value = 0.6
            answers[name] = {
                "type": "score",
                "score": value,
                "legend": {str(i): lvl for i, lvl in enumerate(levels)},
                "probabilities": {str(i): 1 / len(levels) for i in range(len(levels))},
                "confidence": 0.8,
            }
    return {
        "model": "fake-keyword-decider",
        "answers": answers,
        "usage": {"input_tokens": max(1, len(state) // 4), "output_tokens": 1},
        "latency_ms": 0.1,
    }


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._send(200, {"status": "ok", "model": "fake-keyword-decider"})
        else:
            self._send(404, {"detail": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/v1/systemone":
            self._send(404, {"detail": "not found"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            request = json.loads(self.rfile.read(length))
            if not isinstance(request.get("questions"), dict) or not request["questions"]:
                raise ValueError("questions required")
            self._send(200, answer(request))
        except (ValueError, KeyError, TypeError) as exc:
            self._send(422, {"detail": str(exc)})

    def log_message(self, *args):  # keep test output quiet
        pass


def make_server(host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), _Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()
    server = make_server(args.host, args.port)
    print(f"fake decider (keyword rules, not a model) on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
