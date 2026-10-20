"""A tiny in-memory support backend so the demo runs with no external systems."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count


def _seed_orders() -> dict[str, dict]:
    return {
        "A1001": {"item": "Wireless mouse", "total": 42.50, "status": "delivered", "refunded": 0.0},
        "A1002": {
            "item": "Mechanical keyboard",
            "total": 89.99,
            "status": "shipped",
            "refunded": 0.0,
        },
        "A1003": {
            "item": "27-inch monitor",
            "total": 219.00,
            "status": "delivered",
            "refunded": 0.0,
        },
    }


@dataclass
class SupportBackend:
    orders: dict[str, dict] = field(default_factory=_seed_orders)
    refunds: list[dict] = field(default_factory=list)
    tickets: list[dict] = field(default_factory=list)
    human_queue: list[dict] = field(default_factory=list)
    _ids: count = field(default_factory=lambda: count(1), repr=False)

    def lookup_order(self, order_id: str) -> dict:
        order = self.orders.get(order_id.strip().upper())
        if order is None:
            return {"error": f"no order {order_id!r}"}
        return {"order_id": order_id.strip().upper(), **order}

    def issue_refund(self, order_id: str, amount: float, reason: str) -> dict:
        key = order_id.strip().upper()
        order = self.orders.get(key)
        if order is None:
            return {"error": f"no order {order_id!r}"}
        if amount <= 0:
            return {"error": "amount must be positive"}
        refundable = round(order["total"] - order["refunded"], 2)
        if amount > refundable:
            return {"error": f"amount exceeds refundable balance {refundable:.2f}"}
        order["refunded"] = round(order["refunded"] + amount, 2)
        refund = {
            "refund_id": f"R{next(self._ids):04d}",
            "order_id": key,
            "amount": amount,
            "reason": reason,
        }
        self.refunds.append(refund)
        return refund

    def create_ticket(self, summary: str, priority: str = "normal") -> dict:
        ticket = {"ticket_id": f"T{next(self._ids):04d}", "summary": summary, "priority": priority}
        self.tickets.append(ticket)
        return ticket

    def escalate(self, reason: str, message: str = "") -> dict:
        item = {"queue_id": f"H{next(self._ids):04d}", "reason": reason, "message": message}
        self.human_queue.append(item)
        return item


BACKEND = SupportBackend()


def reset_backend() -> SupportBackend:
    """Replace the shared backend with a fresh one (used by tests and the benchmark)."""
    global BACKEND
    BACKEND = SupportBackend()
    return BACKEND
