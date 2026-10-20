"""Demo for the video: shows the guard stopping a guessed refund, then allowing a real one.

Needs: a Decider server on :8099 and AWS credentials with Bedrock access.
    strands-decider serve StrandsAgents/strands-decider-2B-hobson-v19 --port 8099
    python examples/demo.py
"""

from triage_agent import backend
from triage_agent.agent import CHEAP_MODEL, STRONG_MODEL
from triage_agent.decider_client import DeciderClient
from triage_agent.pipeline import SupportPipeline

MESSAGES = [
    "Earn crypto fast, click here to start.",
    "I need to speak to a real person, I will file a chargeback.",
    "How do I turn on dark mode?",
    # no order ID: the guard must stop a guess
    "I want a refund, the mouse I bought arrived broken.",
    # grounded: the refund may run
    "Please refund order A1001, the mouse arrived broken.",
]

pipeline = SupportPipeline(DeciderClient(), cheap_model=CHEAP_MODEL, strong_model=STRONG_MODEL)

for message in MESSAGES:
    print(f"\n> {message}")
    out = pipeline.handle(message)
    d = out.decision
    print(f"  route={d.route.value} ({d.reason}), {d.latency_ms:.0f} ms, llm_calls={out.llm_calls}")
    for r in out.guard_records:
        print(f"  guard: {r.tool} -> {r.action} (grounded={r.grounded}, premature={r.premature})")
    print(f"  reply: {out.reply}")

print(f"\nrefunds issued: {backend.BACKEND.refunds}")
print(f"human queue   : {len(backend.BACKEND.human_queue)} item(s)")
