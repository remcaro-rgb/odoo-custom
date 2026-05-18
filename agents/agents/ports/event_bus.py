"""EventBus port — webhook / cron / push triggers.

Default adapter: GitHubWebhook.
Other adapters: Redis, NATS, LocalCron.

The bus normalises events into the `Event` dataclass below so agent code
sees the same shape regardless of source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class Event:
    type: str                       # e.g. "issue_comment.created", "push", "cron"
    actor: str                      # who/what triggered
    payload: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)  # original payload (debug)


@dataclass(frozen=True)
class Subscription:
    id: str
    event_type: str


class EventBus(Protocol):
    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], None],
    ) -> Subscription:
        """Subscribe to events of a type. Handler is called per event."""
        ...

    def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...
