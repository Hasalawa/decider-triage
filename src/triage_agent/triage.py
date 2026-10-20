"""Policy decision: classify an incoming support message *before* any LLM sees it.

One decider call answers four typed questions about the same text (the text is read once,
each extra question only adds its own tokens). Plain Python then turns the numbers into a
route. The model classifies; the thresholds below are policy and belong to the code.

Routes:
    DROP          spam, no reply, no LLM call
    ESCALATE      a human should own it, no LLM call
    AGENT_CHEAP   routine request, small Bedrock model
    AGENT_STRONG  complex or money-related request, stronger Bedrock model
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

from .decider_client import Choice, DeciderClient, DeciderError, Noul, Score

MAX_MESSAGE_CHARS = 4000


class Route(str, Enum):
    DROP = "drop"
    ESCALATE = "escalate"
    AGENT_CHEAP = "agent_cheap"
    AGENT_STRONG = "agent_strong"


CATEGORIES: dict[str, str] = {
    "refund_request": "The customer asks for money back for an order or a charge.",
    "billing_issue": "A problem or question about an invoice, a charge or a payment method, "
    "but not a request for money back.",
    "bug_report": "Something in the product is broken, crashing or behaving unexpectedly.",
    "account_access": "The customer cannot log in, is locked out, or has a password/2FA problem.",
    "how_to": "A question about how to use a feature, or a general product question.",
    "spam": "Unsolicited promotion, phishing, or an irrelevant bulk message.",
}

URGENCY_LEVELS: tuple[str, ...] = (
    "low: no time pressure",
    "medium: wants an answer soon",
    "high: blocked, or losing money right now",
    "critical: outage, security incident or legal threat",
)

TRIAGE_QUESTIONS = {
    "category": Choice("Which kind of support request is this customer message?", CATEGORIES),
    "urgency": Score("How urgent is this for the customer?", URGENCY_LEVELS),
    "wants_human": Noul(
        "Does the customer ask for a human, or threaten legal action or a chargeback?"
    ),
    "severe": Noul(
        "Does this describe a security incident, an outage, or data loss?",
        true="account compromise, a breach, a data leak, or a system that is down",
        false="an ordinary request or an individual inconvenience",
    ),
    "complex": Noul("Does resolving this need several steps, several systems, or a judgment call?"),
}


@dataclass(frozen=True)
class TriagePolicy:
    """Every knob here is a business decision, not something the model learned."""

    wants_human_min: float = 0.5  # P(yes) at or above this -> human
    severe_min: float = 0.5  # P(yes) at or above this -> human
    critical_urgency_min: float = 2.5  # expected urgency level (0..3) at or above -> human
    spam_min_confidence: float = 0.8  # only drop spam when the model is this sure
    category_min_confidence: float = 0.5  # below this we do not guess, a human decides
    complex_min: float = 0.5  # P(yes) at or above this -> strong model
    strong_categories: frozenset[str] = frozenset({"refund_request"})  # money -> strong model


@dataclass(frozen=True)
class TriageDecision:
    route: Route
    reason: str
    category: str
    category_confidence: float
    urgency: float
    wants_human: float
    severe: float
    complex: float
    latency_ms: float

    def to_dict(self) -> dict:
        data = asdict(self)
        data["route"] = self.route.value
        return data


def decide_route(
    *,
    category: str,
    category_confidence: float,
    urgency: float,
    wants_human: float,
    severe: float,
    complex_: float,
    policy: TriagePolicy,
) -> tuple[Route, str]:
    """Pure function: model numbers in, route out. Order matters, first match wins."""
    if wants_human >= policy.wants_human_min:
        return Route.ESCALATE, "customer asked for a human or threatened escalation"
    if severe >= policy.severe_min:
        return Route.ESCALATE, "security incident or outage"
    if urgency >= policy.critical_urgency_min:
        return Route.ESCALATE, "critical urgency"
    if category == "spam" and category_confidence >= policy.spam_min_confidence:
        return Route.DROP, "confident spam"
    if category_confidence < policy.category_min_confidence:
        return Route.ESCALATE, "low confidence, a human decides instead of a guess"
    if category in policy.strong_categories:
        return Route.AGENT_STRONG, f"{category} involves money"
    if complex_ >= policy.complex_min:
        return Route.AGENT_STRONG, "complex request"
    return Route.AGENT_CHEAP, "routine request"


def triage(
    decider: DeciderClient,
    message: str,
    policy: TriagePolicy | None = None,
) -> TriageDecision:
    """Classify one message. If the decider is down we fail safe to a human."""
    policy = policy or TriagePolicy()
    text = message.strip()
    if not text:
        raise ValueError("message must not be empty")

    try:
        d = decider.ask("Customer support message:\n" + text[:MAX_MESSAGE_CHARS], TRIAGE_QUESTIONS)
    except DeciderError as exc:
        return TriageDecision(
            route=Route.ESCALATE,
            reason=f"decider unavailable ({exc})",
            category="unknown",
            category_confidence=0.0,
            urgency=0.0,
            wants_human=0.0,
            severe=0.0,
            complex=0.0,
            latency_ms=0.0,
        )

    category = d.choice("category")
    urgency = d.score("urgency").value
    wants_human = d.noul("wants_human")
    severe = d.noul("severe")
    complex_ = d.noul("complex")
    route, reason = decide_route(
        category=category.label,
        category_confidence=category.confidence,
        urgency=urgency,
        wants_human=wants_human,
        severe=severe,
        complex_=complex_,
        policy=policy,
    )
    return TriageDecision(
        route=route,
        reason=reason,
        category=category.label,
        category_confidence=category.confidence,
        urgency=urgency,
        wants_human=wants_human,
        severe=severe,
        complex=complex_,
        latency_ms=d.latency_ms,
    )
