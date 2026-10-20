Agent Experience Hackathon · Strands Decider

# Decider Triage

A customer-support agent where a small model decides what should happen to each message, and a big model only writes the replies that are worth writing.

## The idea in one picture

### Decider 2B: the one who ticks boxes

A small model (2 billion parameters) that cannot write a single sentence. You give it a message and a question with fixed answers, and it replies with an answer and how sure it is. Like a hospital receptionist who sorts patients before any doctor sees them.

### Amazon Bedrock model: the one who writes

A large language model that writes the actual reply and uses tools such as "refund this order". It is slower and costs money per call, so we only call it when the message needs it.

## What happens to one message

In

### Customer message

"I would like a refund for order A1001, the mouse arrived damaged."

→

Decider 2B · one call

### Five quick questions

- What kind of request is this?
- How urgent is it? (0 to 3)
- Does the customer want a human?
- Is it a security incident or outage?
- Does it need several steps?

→

**DROP**Spam. Nobody replies, no model is paid for.

**ESCALATE**A human takes over. No model call.

**AGENT_CHEAP**Small Bedrock model writes the reply.

**AGENT_STRONG**Bigger model, for money or complex cases.

The thresholds that turn the model's numbers into a route are plain Python in `triage.py`. The model gives numbers. People decide the rules.

## The second job: stop the agent guessing

Before a risky tool runs (refund, create ticket), a `GroundingGuard` asks Decider one more yes/no question: did the customer actually say these values? This is the file you copy into your own agent.

1 · Customer"I want a refund, my mouse broke."

no order ID given

2 · AgentWants to call a tool.

issue_refund(order_id="A9999")

3 · Guard asks Decider"Are the arguments grounded in what the customer said?"

grounded = low

4 · ResultGuide: the agent gets its turn back and asks "Which order is it?"

refund never runs

If the customer had said "order A1001", the guard answers high, returns Proceed, and the refund runs. Guide corrects the agent. Deny would only block it.

## Real results from the laptop run

Measured on the 30-message hold-out set, using the real Decider 2B served on a laptop CPU. These 30 messages were written before the model was run on them.

24 / 30

routes correct (80%)

14.3 s

median time per message on a laptop CPU. The official figure on an RTX 3090 GPU is 115 ms.

20 / 30

messages needed a Bedrock call. The rest were dropped or sent to a human.

Before the "security incident" question was added, the first run on the 24 development messages scored 79.2%, and the outage and hacked-account messages went to the cheap agent. In this hold-out run, all 7 human-escalation messages were routed correctly. Seven messages is a small sample.

## Play with the rules

These are the 6 messages the model got wrong on the hold-out set, with the real numbers it returned. Move a threshold and see which routes change. Fixing these 6 may break messages you cannot see here, which is why the policy is judged on messages it was not tuned on.

Numbers come from the project's own `triage-bench` runs. Latency depends on hardware. Cost figures in the repo use placeholder prices, check current Bedrock pricing before quoting them.