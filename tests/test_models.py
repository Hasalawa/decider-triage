from triage_agent.models import list_claude_profiles, pick


class FakeBedrock:
    def __init__(self):
        self.pages = [
            {
                "inferenceProfileSummaries": [
                    {"inferenceProfileId": "eu.anthropic.claude-haiku-4-5-20251001-v1:0"},
                    {"inferenceProfileId": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"},
                    {"inferenceProfileId": "us.anthropic.claude-sonnet-4-5-20250929-v1:0"},
                    {"inferenceProfileId": "eu.amazon.nova-lite-v1:0"},
                ],
                "nextToken": "p2",
            },
            {
                "inferenceProfileSummaries": [
                    {"inferenceProfileId": "global.anthropic.claude-haiku-4-5-20251001-v1:0"},
                    {
                        "inferenceProfileId": "eu.anthropic.claude-old-v1:0",
                        "status": "INACTIVE",
                    },
                ]
            },
        ]

    def list_inference_profiles(self, **kw):
        return self.pages[1] if kw.get("nextToken") else self.pages[0]


def test_lists_only_active_claude_profiles_across_pages():
    ids = list_claude_profiles(FakeBedrock())
    assert len(ids) == 4 and all("anthropic.claude" in i for i in ids)
    assert not any("old" in i for i in ids)


def test_pick_prefers_region_prefix_then_global():
    ids = list_claude_profiles(FakeBedrock())
    assert pick(ids, "sonnet", "eu-north-1").startswith("eu.")
    assert pick(ids, "haiku", "eu-north-1").startswith("eu.")
    assert pick(ids, "haiku", "ap-southeast-2").startswith("global.")
    assert pick(ids, "opus", "eu-north-1") is None
