# Hackathon submission checklist (deadline Oct 23, 11:59 PM PDT = Oct 24, 12:29 PM Sri Lanka time)

Check the Rules tab on the hackathon page for anything that differs from this list.

- [ ] Public GitHub repo with this code (agent + `decision_pattern.py`)
- [ ] Run the agent once for real on Bedrock (`python examples/demo.py`), fix model IDs if needed
- [ ] Run `triage-bench` against the REAL decider, keep the output for the article
- [ ] Demo video under 3 minutes, publicly viewable (suggested script below)
- [ ] Article on AWS Builder Center (outline below)
- [ ] Tags on the submission: `#strands-decider-2b` and `#policy`
- [ ] Original agent, not published before

## Demo video script (about 2:30)

1. (0:00) Problem: support agents burn an LLM call on spam and guess tool arguments.
2. (0:20) `triage-agent --triage-only` on spam, "real person", routine, refund: show route + ms.
3. (1:00) `python examples/demo.py`: the refund with no order ID is guided back, then the one with A1001 goes through.
4. (1:50) `triage-bench` output: LLM calls avoided, decider latency.
5. (2:15) Show `decision_pattern.py` (the reusable file) and the green CI run.

## Article outline (Builder Center)

1. What I built and which decision I handed to Decider 2B
2. Why a decision model (numbers, thresholds, no negotiating with prose)
3. The four triage questions and the policy table
4. The grounding guard: evidence rule, Guide vs Deny
5. Results: paste real `triage-bench` output, state hardware, mention the cold-start call
6. What did not work / what I learned (be specific, e.g. thresholds, failure cases from `mistakes`)
7. How to reuse the pattern (copy `decision_pattern.py`, 5 lines)
