"""Strands tools the support agent can call. They are thin wrappers over the backend."""

from __future__ import annotations

from strands import tool

from . import backend


@tool
def lookup_order(order_id: str) -> dict:
    """Look up an order by its ID (for example A1001) and return item, total and status.

    Args:
        order_id: The order ID exactly as the customer gave it.
    """
    return backend.BACKEND.lookup_order(order_id)


@tool
def issue_refund(order_id: str, amount: float, reason: str) -> dict:
    """Refund money for an order. Only call this with an order ID the customer provided.

    Args:
        order_id: The order ID the customer provided.
        amount: The amount to refund, at most the order total.
        reason: A short reason for the refund.
    """
    return backend.BACKEND.issue_refund(order_id, amount, reason)


@tool
def create_ticket(summary: str, priority: str = "normal") -> dict:
    """Create a support ticket for engineering or billing follow-up.

    Args:
        summary: One or two sentences describing the problem.
        priority: One of low, normal, high.
    """
    return backend.BACKEND.create_ticket(summary, priority)


@tool
def escalate_to_human(reason: str) -> dict:
    """Hand the conversation to a human support agent.

    Args:
        reason: Why a human should take over.
    """
    return backend.BACKEND.escalate(reason)


ALL_TOOLS = [lookup_order, issue_refund, create_ticket, escalate_to_human]
# Tools that move money or change state are the ones worth guarding.
GUARDED_TOOLS = {"issue_refund", "create_ticket"}
