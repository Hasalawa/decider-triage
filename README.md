# decider-triage

[![CI](https://github.com/YOUR_USER/decider-triage/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USER/decider-triage/actions/workflows/ci.yml)

A customer-support agent where **Strands Decider 2B makes the routine decisions** and
**Amazon Bedrock only writes text**. Built for the Agent Experience Hackathon: Strands Decider.

Tags: `#strands-decider-2b` `#policy` (it also uses a grounding guardrail, see below)

## What the Decider decides

| Decision | Where | Question type | Result |
|---|---|---|---|
| Category, urgency, "wants a human", "is it complex" | before any LLM | `choice`, `score`, `noul` x2 | route the message |
| "Are the tool arguments grounded in what the user said?" / "Is it premature?" | right before `issue_refund` / `create_ticket` | `noul` x2 | proceed, or hand the turn back to the agent |

```
message -> triage (Decider 2B, one call, 4 questions)
             |-- drop          spam, no reply, no LLM call
             |-- escalate      human queue, no LLM call
             |-- agent_cheap   small Bedrock model
             '-- agent_strong  stronger Bedrock model (money / complex)
                                   |
                        tool call proposed ---> GroundingGuard (Decider 2B)
                                   |-- grounded  -> Proceed
                                   '-- guessed   -> Guide ("ask the customer for the order ID")
```

The model only returns numbers. **Thresholds are plain Python in `triage.py`**
(`TriagePolicy`), so you can read, test and change the policy without touching a model.
If the Decider is unreachable, triage fails safe to a human and the guard denies the tool call.

## Reusable decision pattern

`src/triage_agent/decision_pattern.py` is a single file you can drop into any Strands agent:

```python
from triage_agent.decider_client import DeciderClient
from triage_agent.decision_pattern import GroundingGuard

guard = GroundingGuard(DeciderClient(), tools={"issue_refund"})
agent = Agent(model=..., tools=[issue_refund], interventions=[guard])
```

- **Typed questions:** `args_grounded` and `premature` (both `noul`)
- **Wiring:** a Strands `InterventionHandler.before_tool_call`
- **Verdicts:** `Proceed`, `Guide` (model gets its turn back with feedback), `Deny` (only if the Decider is down)
- **Evidence rule:** the guard shows the Decider only user text and tool results, never the
  assistant's own words, so a guessed argument cannot vouch for itself

## Quick start

```bash
git clone https://github.com/YOUR_USER/decider-triage && cd decider-triage
pip install -e ".[dev]"
pip install strands-decider              # the real model (needs torch)

strands-decider serve StrandsAgents/strands-decider-2B-hobson-v19 --port 8099
# AWS credentials with Bedrock model access must be set for the agent part

triage-agent --triage-only "I would like a refund for order A1001"   # decider only, no Bedrock
triage-agent "How do I turn on dark mode?"                           # full flow
python examples/demo.py                                              # the demo from the video
triage-bench                                                         # accuracy / latency / cost
```

Model IDs default to Claude Haiku 4.5 (cheap) and Sonnet 4.5 (strong) as Bedrock
inference-profile IDs. Override with `TRIAGE_CHEAP_MODEL` / `TRIAGE_STRONG_MODEL` and make
sure the models are enabled in your region.

## Run without downloading the model

`triage-fake-decider` is a **keyword stub** with the same HTTP API. CI and the unit tests use it.
It is not a model: accuracy or latency measured against it says nothing about Decider 2B.
`triage-bench` prints the server's model name so this cannot be confused.

## Measuring the benefit

`triage-bench` runs `src/triage_agent/data/triage_set.jsonl` (24 hand-labeled messages, small on
purpose) and reports routing accuracy, decider p50/p95 latency, and LLM calls avoided vs
sending everything to the strong model. Cost uses placeholder per-token prices you pass with
`--price-cheap` / `--price-strong`; **use current Bedrock pricing before quoting a number**.
Run it against the real server (or the `Real Decider benchmark` workflow) for the numbers
you publish. Latency on a cold first call is much higher than the warm median, so the
benchmark does a warm-up call first.

## CI/CD (GitHub Actions)

| Workflow | When | What |
|---|---|---|
| `ci.yml` | push, PR | ruff lint + format, tests on Python 3.10-3.13 with coverage, pipeline smoke test, build + `twine check` |
| `real-decider.yml` | manual, weekly | serves the real Decider 2B on CPU and runs `triage-bench`, writes the JSON to the job summary |
| `release.yml` | tag `v*` | checks tag == package version, tests, builds, publishes to PyPI via Trusted Publishing, creates a GitHub release |
| `deploy-lambda.yml` | manual | optional, builds a Lambda zip and deploys it with GitHub OIDC (no stored AWS keys) |
| `dependabot.yml` | weekly | pip and Actions updates |

See [docs/DEPLOY.md](docs/DEPLOY.md) for the one-time setup of each.

## Layout

```
src/triage_agent/
  decider_client.py   typed client for POST /v1/systemone (httpx only)
  triage.py           policy decision: questions + thresholds -> route
  decision_pattern.py REUSABLE: GroundingGuard InterventionHandler
  pipeline.py         route -> drop / escalate / cheap / strong
  agent.py, tools.py  Bedrock-backed Strands agent and its tools
  backend.py          in-memory orders, refunds, tickets, human queue
  bench.py            accuracy / latency / cost report
  fake_decider.py     keyword stub for CI (not a model)
tests/                31 tests, no AWS and no model download needed
```

## Limitations (honest list)

- Decider 2B is an experimental model (about 72% on JevBench overall). Thresholds here were
  picked by hand, not tuned, and the 24-message set is too small to prove anything about
  production accuracy.
- The backend is in-memory demo data.
- The Bedrock part and the real-Decider path need credentials and a model download, so they
  are not exercised by the default CI; the benchmark workflow covers the Decider side.

License: MIT
