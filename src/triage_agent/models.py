"""List the Claude models your AWS account can call through Bedrock, in your region.

    python -m triage_agent.models

Bedrock model IDs depend on the region (``us.``, ``eu.``, ``global.`` prefixes). Run this once
after ``aws configure``. It prints IDs that really exist for you and the two lines that tell
the agent which ones to use.
"""

from __future__ import annotations

import sys

PREFERRED_PREFIX = {"eu": "eu.", "us": "us.", "ap": "apac."}


def list_claude_profiles(client) -> list[str]:
    """Return the IDs of active Anthropic Claude inference profiles."""
    ids: list[str] = []
    token = None
    while True:
        kwargs = {"maxResults": 100, "typeEquals": "SYSTEM_DEFINED"}
        if token:
            kwargs["nextToken"] = token
        resp = client.list_inference_profiles(**kwargs)
        for item in resp.get("inferenceProfileSummaries", []):
            pid = item.get("inferenceProfileId", "")
            if "anthropic.claude" in pid and item.get("status", "ACTIVE") == "ACTIVE":
                ids.append(pid)
        token = resp.get("nextToken")
        if not token:
            return sorted(set(ids))


def pick(ids: list[str], family: str, region: str) -> str | None:
    """Newest model of a family (haiku / sonnet), preferring this region's own prefix."""
    matches = [i for i in ids if family in i]
    if not matches:
        return None
    prefix = PREFERRED_PREFIX.get(region.split("-")[0], "")
    for wanted in (prefix, "global."):
        pool = [i for i in matches if wanted and i.startswith(wanted)]
        if pool:
            return max(pool)
    return max(matches)


def main() -> None:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    session = boto3.session.Session()
    region = session.region_name or "us-east-1"
    try:
        ids = list_claude_profiles(session.client("bedrock", region_name=region))
    except (BotoCoreError, ClientError) as exc:
        print(f"Could not list Bedrock models in {region}: {exc}")
        print("Check `aws sts get-caller-identity` works, and that the user may use Bedrock.")
        sys.exit(1)

    print(f"Region: {region}")
    if not ids:
        print("No Claude models found here. Try another region (e.g. us-east-1).")
        sys.exit(1)
    print("Claude models you can use:")
    for i in ids:
        print(f"  {i}")
    cheap, strong = pick(ids, "haiku", region), pick(ids, "sonnet", region)
    print("\nPaste these two lines into PowerShell, then restart the agent / UI:")
    if cheap:
        print(f'  $env:TRIAGE_CHEAP_MODEL = "{cheap}"')
    if strong:
        print(f'  $env:TRIAGE_STRONG_MODEL = "{strong}"')


if __name__ == "__main__":
    main()
