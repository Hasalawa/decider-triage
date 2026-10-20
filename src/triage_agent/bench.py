"""Benchmark the triage decision on a small labeled set.

Reports routing accuracy against the gold labels, decider latency (p50 / p95, after a
warm-up call), and the LLM spend avoided versus sending everything to the strong model.

Cost uses PRICE ARGUMENTS you pass in (USD per 1K tokens). The defaults are placeholders,
not real Bedrock prices: check current pricing for your models before quoting a number.

If you run this against ``triage-fake-decider`` the accuracy and latency describe the
keyword stub, not Strands Decider 2B. The report prints the decider's reported model name
so a result is never mistaken for a real one.
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass
from importlib import resources

from .decider_client import DeciderClient
from .triage import Route, TriagePolicy, triage

TOKENS_PER_REQUEST = 600  # rough size of one agent conversation, adjust to your traffic


@dataclass
class BenchReport:
    model_name: str
    total: int
    correct: int
    p50_ms: float
    p95_ms: float
    llm_calls: int
    cost_always_strong: float
    cost_routed: float
    mistakes: list[dict]

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def savings_pct(self) -> float:
        if self.cost_always_strong == 0:
            return 0.0
        return 100 * (1 - self.cost_routed / self.cost_always_strong)

    def to_dict(self) -> dict:
        return {
            "decider_model": self.model_name,
            "examples": self.total,
            "routing_accuracy": round(self.accuracy, 4),
            "decider_latency_ms": {"p50": round(self.p50_ms, 1), "p95": round(self.p95_ms, 1)},
            "llm_calls": {"always_strong": self.total, "routed": self.llm_calls},
            "cost_usd": {
                "always_strong": round(self.cost_always_strong, 5),
                "routed": round(self.cost_routed, 5),
                "savings_pct": round(self.savings_pct, 1),
            },
            "mistakes": self.mistakes,
        }


def load_set() -> list[dict]:
    text = resources.files("triage_agent.data").joinpath("triage_set.jsonl").read_text("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))
    return ordered[index]


def run_bench(
    decider: DeciderClient,
    examples: list[dict],
    *,
    price_cheap: float,
    price_strong: float,
    policy: TriagePolicy | None = None,
) -> BenchReport:
    try:
        model_name = str(decider.health().get("model", "unknown"))
    except Exception:  # health is optional, do not fail the benchmark over it
        model_name = "unknown"

    triage(decider, "warm up: how do I reset my password?", policy)  # first call pays compile cost

    latencies: list[float] = []
    correct = llm_calls = 0
    cost_routed = 0.0
    mistakes: list[dict] = []
    for ex in examples:
        d = triage(decider, ex["text"], policy)
        latencies.append(d.latency_ms)
        if d.route.value == ex["route"]:
            correct += 1
        else:
            mistakes.append(
                {
                    "text": ex["text"],
                    "gold": ex["route"],
                    "got": d.route.value,
                    "numbers": {
                        "category": d.category,
                        "category_conf": round(d.category_confidence, 2),
                        "urgency": round(d.urgency, 2),
                        "wants_human": round(d.wants_human, 2),
                        "complex": round(d.complex, 2),
                    },
                }
            )
        if d.route is Route.AGENT_CHEAP:
            llm_calls += 1
            cost_routed += price_cheap * TOKENS_PER_REQUEST / 1000
        elif d.route is Route.AGENT_STRONG:
            llm_calls += 1
            cost_routed += price_strong * TOKENS_PER_REQUEST / 1000

    return BenchReport(
        model_name=model_name,
        total=len(examples),
        correct=correct,
        p50_ms=statistics.median(latencies) if latencies else 0.0,
        p95_ms=_percentile(latencies, 95),
        llm_calls=llm_calls,
        cost_always_strong=len(examples) * price_strong * TOKENS_PER_REQUEST / 1000,
        cost_routed=cost_routed,
        mistakes=mistakes,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Decider triage routing.")
    parser.add_argument("--url", default=None, help="decider base URL (default env/8099)")
    parser.add_argument("--price-cheap", type=float, default=0.001, help="USD per 1K tokens")
    parser.add_argument("--price-strong", type=float, default=0.010, help="USD per 1K tokens")
    parser.add_argument("--json", action="store_true", help="print JSON only")
    parser.add_argument("--verbose", action="store_true", help="show the model numbers per miss")
    parser.add_argument("--min-accuracy", type=float, default=0.0, help="exit 1 below this")
    args = parser.parse_args()

    report = run_bench(
        DeciderClient(args.url),
        load_set(),
        price_cheap=args.price_cheap,
        price_strong=args.price_strong,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        r = report
        print(f"decider model      : {r.model_name}")
        print(f"routing accuracy   : {r.correct}/{r.total} = {r.accuracy:.1%}")
        print(f"decider latency    : p50 {r.p50_ms:.1f} ms, p95 {r.p95_ms:.1f} ms")
        print(f"LLM calls          : {r.llm_calls} routed vs {r.total} always-strong")
        print(
            f"cost (placeholder prices): ${r.cost_routed:.4f} vs ${r.cost_always_strong:.4f}"
            f" ({r.savings_pct:.0f}% lower)"
        )
        for m in r.mistakes:
            print(f"  MISS gold={m['gold']:<12} got={m['got']:<12} {m['text']!r}")
            if args.verbose:
                print(f"       {m['numbers']}")
    if report.accuracy < args.min_accuracy:
        raise SystemExit(1)


if __name__ == "__main__":
    main()