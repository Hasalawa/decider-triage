"""AWS Lambda entry point: POST {"message": "..."} -> triage + (optional) agent reply.

Env vars:
    DECIDER_URL         where a Decider server is reachable (required)
    TRIAGE_CHEAP_MODEL  Bedrock model id for routine requests (optional)
    TRIAGE_STRONG_MODEL Bedrock model id for complex or money requests (optional)
"""

import json
import os

from triage_agent.agent import CHEAP_MODEL, STRONG_MODEL
from triage_agent.decider_client import DeciderClient
from triage_agent.pipeline import SupportPipeline

_pipeline = SupportPipeline(
    DeciderClient(os.environ["DECIDER_URL"]),
    cheap_model=CHEAP_MODEL,
    strong_model=STRONG_MODEL,
)


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}") if "body" in event else event
        message = str(body["message"])
    except (KeyError, ValueError, TypeError):
        return {"statusCode": 400, "body": json.dumps({"error": "send {'message': '...'}"})}
    outcome = _pipeline.handle(message)
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "triage": outcome.decision.to_dict(),
                "reply": outcome.reply,
                "llm_calls": outcome.llm_calls,
            }
        ),
    }
