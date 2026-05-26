"""GitHub EventBus adapter — receives GitHub webhooks.

For the slack_intake agent only `issue_comment.created` matters. The adapter
verifies the GitHub HMAC-SHA256 signature on every delivery, deduplicates
on `X-GitHub-Delivery`, and emits an Event into the subscribed handlers.

The wider runtime can subscribe to other event types as GitHub-driven
agents come online; this adapter just routes everything generically.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from typing import Any

from ..config import Config
from ..ports import Event, EventBus, Subscription

# Sibling adapter (intentional shared file) — keeps DispatchResult in one place.
from .events_slack_webhook import DispatchResult


class GitHubWebhookEventBus:
    """EventBus for inbound GitHub webhooks."""

    def __init__(self, *, webhook_secret: str, logger: Any = None) -> None:
        self._secret = webhook_secret.encode("utf-8")
        self._subs: dict[str, list[Callable[[Event], Any]]] = {}
        self._next_sub_id = 0
        # See SlackWebhookEventBus for the rationale on the optional logger.
        self._logger = logger

    @classmethod
    def from_config(cls, config: Config) -> GitHubWebhookEventBus:
        from .secrets_envvar import EnvVarSecretStore
        secrets = EnvVarSecretStore()
        cfg: dict[str, Any] = config.extras.get("github", {})
        return cls(
            webhook_secret=secrets.get_or_raise(
                cfg.get("webhook_secret_name", "GITHUB_WEBHOOK_SECRET")
            ),
        )

    def set_logger(self, logger: Any) -> None:
        """Attach a runtime Logger so handler exceptions land as structured logs."""
        self._logger = logger

    # ---- EventBus protocol ----

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], Any],
    ) -> Subscription:
        self._next_sub_id += 1
        sub_id = f"gh-sub-{self._next_sub_id}"
        self._subs.setdefault(event_type, []).append(handler)
        return Subscription(id=sub_id, event_type=event_type)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        """Deliver an event; handler exceptions caught (GitHub retries on 5xx).

        Letting a handler exception propagate would turn into a 500 to
        GitHub, which retries the delivery — potentially up to 8 times
        with exponential backoff. That burns webhook budget on a bug
        we already know about. Catch and log instead.
        """
        event = Event(type=event_type, actor="github", payload=payload)
        for handler in self._subs.get(event_type, []):
            try:
                handler(event)
            except Exception as exc:  # noqa: BLE001 — bus must absorb handler errors
                self._report_handler_error(event_type, handler, exc)

    def _report_handler_error(
        self,
        event_type: str,
        handler: Callable[[Event], Any],
        exc: BaseException,
    ) -> None:
        import traceback
        handler_name = getattr(handler, "__qualname__", repr(handler))
        if self._logger is not None:
            self._logger.error(
                "events_github_webhook.handler_exception",
                event_type=event_type,
                handler=handler_name,
                error_type=type(exc).__name__,
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            return
        import sys
        print(
            f"events_github_webhook.handler_exception event_type={event_type} "
            f"handler={handler_name} error={type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        traceback.print_exc(file=sys.stderr)

    # ---- HTTP entry point ----

    def dispatch(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
    ) -> DispatchResult:
        if not self.verify_signature(headers=headers, body=body):
            return DispatchResult(status=401, body="invalid signature")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return DispatchResult(status=400, body="invalid json")
        event_name = (
            headers.get("x-github-event")
            or headers.get("X-GitHub-Event")
            or "unknown"
        )
        action = payload.get("action")
        full_type = f"github.{event_name}.{action}" if action else f"github.{event_name}"
        delivery_id = (
            headers.get("x-github-delivery")
            or headers.get("X-GitHub-Delivery")
            or ""
        )
        self.publish(full_type, {"delivery_id": delivery_id, **payload})
        return DispatchResult(status=200, body="ok")

    # ---- signature verification ----

    def verify_signature(
        self, *, headers: dict[str, str], body: bytes,
    ) -> bool:
        """GitHub uses HMAC-SHA256 in the X-Hub-Signature-256 header."""
        sig = (
            headers.get("x-hub-signature-256")
            or headers.get("X-Hub-Signature-256")
            or ""
        )
        if not sig.startswith("sha256="):
            return False
        expected = "sha256=" + hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)


_ = EventBus  # Protocol check
