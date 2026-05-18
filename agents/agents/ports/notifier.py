"""Notifier port — out-of-band notifications to humans.

Default adapter: Slack.
Other adapters: Teams, Discord, Email, Webhook.
"""

from __future__ import annotations

from typing import Literal, Protocol

Severity = Literal["info", "warn", "page"]


class Notifier(Protocol):
    def send(
        self,
        *,
        channel: str,
        summary: str,
        details: dict | None = None,
        severity: Severity = "info",
    ) -> None:
        """Send a notification.

        `channel` is interpreted by the adapter: Slack `#name`, Discord
        webhook key, Teams webhook key, email distribution list, etc.

        `severity` controls routing:
        - `info` → channel only
        - `warn` → channel + amber colour
        - `page` → channel + PagerDuty integration (adapter-dependent)
        """
        ...
