"""Slack notifier adapter — the default Notifier.

Maps severity to icon + colour. Page severity additionally integrates with
PagerDuty if `PAGERDUTY_TOKEN` is set in the secret store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import Config
from ..ports import Notifier, Severity

if TYPE_CHECKING:
    pass


class SlackAdapter:
    """Notifier backed by Slack's chat.postMessage API."""

    SEVERITY_COLOUR = {
        "info": "#36a64f",   # green
        "warn": "#f2c744",   # amber
        "page": "#d72631",   # red
    }
    SEVERITY_ICON = {
        "info": ":information_source:",
        "warn": ":warning:",
        "page": ":rotating_light:",
    }

    def __init__(self, *, token: str, default_channel: str,
                 pagerduty_token: str | None = None) -> None:
        self._default_channel = default_channel
        self._pagerduty_token = pagerduty_token
        from slack_sdk import WebClient  # type: ignore[import-untyped]
        self._slack = WebClient(token=token)

    @classmethod
    def from_config(cls, config: Config) -> SlackAdapter:
        from .secrets_envvar import EnvVarSecretStore
        secrets = EnvVarSecretStore()
        slack_cfg = config.extras.get("slack", {})
        return cls(
            token=secrets.get_or_raise(
                slack_cfg.get("workspace_secret", "SLACK_BOT_TOKEN")
            ),
            default_channel=slack_cfg.get("default_channel", "#devops-agents"),
            pagerduty_token=secrets.get("PAGERDUTY_TOKEN"),
        )

    def send(
        self,
        *,
        channel: str,
        summary: str,
        details: dict | None = None,
        severity: Severity = "info",
    ) -> None:
        channel = channel or self._default_channel
        attachments = [{
            "color": self.SEVERITY_COLOUR.get(severity, "#36a64f"),
            "text": summary,
            "fields": [
                {"title": k, "value": str(v), "short": len(str(v)) < 40}
                for k, v in (details or {}).items()
            ],
        }]
        self._slack.chat_postMessage(
            channel=channel,
            text=f"{self.SEVERITY_ICON.get(severity, '')} {summary}",
            attachments=attachments,
        )
        if severity == "page" and self._pagerduty_token:
            self._page_pagerduty(summary, details or {})

    def _page_pagerduty(self, summary: str, details: dict) -> None:
        # Triggers an Events-API v2 incident. Stub — adapter user must
        # configure the routing key in details['routing_key'] or PAGERDUTY_ROUTING_KEY env.
        import httpx
        routing_key = details.get("routing_key") or details.get("pd_routing_key")
        if not routing_key:
            return
        httpx.post(
            "https://events.pagerduty.com/v2/enqueue",
            json={
                "routing_key": routing_key,
                "event_action": "trigger",
                "payload": {
                    "summary": summary,
                    "source": "odoo-saas-agents",
                    "severity": "critical",
                    "custom_details": details,
                },
            },
            timeout=10,
        )


_ = Notifier  # Protocol check
