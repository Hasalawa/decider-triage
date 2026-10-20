"""Command line entry point: ``triage-agent "message"``."""

from __future__ import annotations

import argparse
import json

from . import backend
from .agent import CHEAP_MODEL, STRONG_MODEL
from .decider_client import DeciderClient, DeciderError
from .pipeline import SupportPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Triage one support message.")
    parser.add_argument("message", help="the customer message")
    parser.add_argument(
        "--url", default=None, help="decider URL (default STRANDS_DECIDER_URL or :8099)"
    )
    parser.add_argument("--triage-only", action="store_true", help="classify, do not call Bedrock")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args()

    decider = DeciderClient(args.url)
    try:
        decider.health()
    except DeciderError as exc:
        print(
            f"warning: {exc}\nstart it with: strands-decider serve "
            "StrandsAgents/strands-decider-2B-hobson-v19 --port 8099"
        )

    def no_llm(model_id, guard, message):
        return "(--triage-only: no Bedrock call made)"

    pipeline = SupportPipeline(
        decider,
        cheap_model=CHEAP_MODEL,
        strong_model=STRONG_MODEL,
        **({"runner": no_llm} if args.triage_only else {}),
    )
    outcome = pipeline.handle(args.message)

    if args.json:
        print(
            json.dumps(
                {
                    "triage": outcome.decision.to_dict(),
                    "reply": outcome.reply,
                    "model_id": outcome.model_id,
                    "llm_calls": outcome.llm_calls,
                    "guard": [r.__dict__ for r in outcome.guard_records],
                    "human_queue": backend.BACKEND.human_queue,
                    "refunds": backend.BACKEND.refunds,
                },
                indent=2,
            )
        )
        return

    d = outcome.decision
    print(f"route    : {d.route.value} ({d.reason})")
    print(f"category : {d.category} (conf {d.category_confidence:.2f}), urgency {d.urgency:.2f}")
    print(f"decider  : {d.latency_ms:.0f} ms")
    for r in outcome.guard_records:
        print(f"guard    : {r.tool} -> {r.action} (grounded={r.grounded}, premature={r.premature})")
    print(f"reply    : {outcome.reply if outcome.reply is not None else '(none, message dropped)'}")


if __name__ == "__main__":
    main()
