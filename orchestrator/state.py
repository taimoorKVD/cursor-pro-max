"""Formal task status transitions."""
from __future__ import annotations

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "failed"}),
    "running": frozenset({"review", "failed", "awaiting_clarification"}),
    "awaiting_clarification": frozenset({"queued", "rejected", "failed"}),
    "review": frozenset({"publishing", "rejected", "queued", "failed"}),
    "publishing": frozenset({"published", "publish_failed", "failed"}),
    "published": frozenset(),
    "publish_failed": frozenset({"review", "publishing"}),
    "rejected": frozenset(),
    "failed": frozenset({"queued"}),
}

TERMINAL = frozenset({"published", "rejected"})


def can_transition(current: str, new: str) -> bool:
    if current == new:
        return True
    return new in ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_transition(current: str, new: str) -> None:
    if not can_transition(current, new):
        raise ValueError(f"Illegal task transition: {current} → {new}")


# Restart recovery only. Normal update_task cannot use these extra edges.
RECOVERY_TRANSITIONS: dict[str, frozenset[str]] = {
    "running": frozenset({"failed", "queued"}),
    "publishing": frozenset({"publish_failed"}),
    "queued": frozenset({"queued"}),
}


def assert_recovery(current: str, new: str) -> None:
    if current == new or new in RECOVERY_TRANSITIONS.get(current, frozenset()):
        return
    if can_transition(current, new):
        return
    raise ValueError(f"Illegal recovery transition: {current} → {new}")
