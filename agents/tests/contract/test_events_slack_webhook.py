"""Contract test for SlackWebhookEventBus signature verification + dispatch."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from agents.adapters.events_slack_webhook import SlackWebhookEventBus

SIGNING_SECRET = "test_signing_secret"  # noqa: S105 — test fixture, not a real secret


def _sign(body: bytes, ts: int) -> dict[str, str]:
    base = b"v0:" + str(ts).encode("ascii") + b":" + body
    sig = "v0=" + hmac.new(
        SIGNING_SECRET.encode("utf-8"), base, hashlib.sha256,
    ).hexdigest()
    return {
        "x-slack-signature": sig,
        "x-slack-request-timestamp": str(ts),
    }


def _bus() -> SlackWebhookEventBus:
    return SlackWebhookEventBus(signing_secret=SIGNING_SECRET)


def test_signature_verified_for_fresh_request() -> None:
    body = b"command=%2Fintake&user_id=U1"
    ts = int(time.time())
    bus = _bus()
    assert bus.verify_signature(headers=_sign(body, ts), body=body, now=ts) is True


def test_signature_rejected_for_stale_request() -> None:
    body = b"command=%2Fintake"
    ts = int(time.time()) - 1000   # 16 minutes old; past the 5-min cutoff
    bus = _bus()
    assert bus.verify_signature(headers=_sign(body, ts), body=body) is False


def test_signature_rejected_for_tampered_body() -> None:
    body = b"command=%2Fintake"
    ts = int(time.time())
    headers = _sign(body, ts)
    tampered = b"command=%2Fevil"
    bus = _bus()
    assert bus.verify_signature(headers=headers, body=tampered, now=ts) is False


def test_signature_rejected_when_header_missing() -> None:
    body = b"command=%2Fintake"
    assert _bus().verify_signature(headers={}, body=body) is False


def test_url_verification_handshake() -> None:
    body = json.dumps({"type": "url_verification", "challenge": "abc123"}).encode()
    ts = int(time.time())
    bus = _bus()
    result = bus.dispatch(
        headers={**_sign(body, ts), "content-type": "application/json"},
        body=body, now=ts,
    )
    assert result.status == 200
    assert result.body == "abc123"


def test_slash_command_publishes_event() -> None:
    bus = _bus()
    seen: list[dict] = []
    bus.subscribe("slack.slash_command", lambda e: seen.append(e.payload))

    body = b"command=%2Fintake&user_id=U1&trigger_id=trig.42&channel_id=C1"
    ts = int(time.time())
    headers = {
        **_sign(body, ts),
        "content-type": "application/x-www-form-urlencoded",
    }
    result = bus.dispatch(headers=headers, body=body, now=ts)
    assert result.status == 200
    assert len(seen) == 1
    assert seen[0]["command"] == "/intake"
    assert seen[0]["user_id"] == "U1"


def test_interactivity_modal_submitted() -> None:
    bus = _bus()
    received: list[dict] = []
    bus.subscribe("slack.modal_submitted", lambda e: received.append(e.payload))

    inner = {"type": "view_submission", "view": {"callback_id": "intake_submit"}}
    body = ("payload=" + json.dumps(inner)).encode("utf-8")
    # urllib quoting note: the test's form parser handles bare JSON fine.
    ts = int(time.time())
    headers = {
        **_sign(body, ts),
        "content-type": "application/x-www-form-urlencoded",
    }
    result = bus.dispatch(headers=headers, body=body, now=ts)
    assert result.status == 200
    assert len(received) == 1
    assert received[0]["view"]["callback_id"] == "intake_submit"


def test_event_subscription_publishes_inner_event() -> None:
    bus = _bus()
    captured: list[dict] = []
    bus.subscribe("slack.message", lambda e: captured.append(e.payload))

    inner = {
        "type": "event_callback",
        "event_id": "Ev123",
        "event": {"type": "message", "text": "hello", "user": "U1", "channel": "C1"},
    }
    body = json.dumps(inner).encode("utf-8")
    ts = int(time.time())
    headers = {**_sign(body, ts), "content-type": "application/json"}
    result = bus.dispatch(headers=headers, body=body, now=ts)
    assert result.status == 200
    assert len(captured) == 1
    assert captured[0]["text"] == "hello"
    assert captured[0]["event_id"] == "Ev123"


def test_invalid_signature_returns_401() -> None:
    body = b"command=%2Fintake"
    ts = int(time.time())
    headers = {
        "x-slack-signature": "v0=deadbeef",
        "x-slack-request-timestamp": str(ts),
    }
    bus = _bus()
    result = bus.dispatch(headers=headers, body=body, now=ts)
    assert result.status == 401


# ---- Issue #117: handler exceptions must not propagate to dispatch ----

def test_publish_absorbs_handler_exception_with_logger() -> None:
    """A handler that raises must NOT propagate; the bus logs and continues."""
    class FakeLogger:
        def __init__(self) -> None: self.errors: list[dict] = []
        def error(self, msg: str, /, **fields) -> None:
            self.errors.append({"msg": msg, **fields})
        def info(self, *a, **k) -> None: ...
        def warn(self, *a, **k) -> None: ...
        def debug(self, *a, **k) -> None: ...

    fake = FakeLogger()
    bus = SlackWebhookEventBus(signing_secret=SIGNING_SECRET, logger=fake)
    bus.subscribe("slack.boom", lambda e: (_ for _ in ()).throw(ValueError("kaboom")))

    # Should NOT raise.
    bus.publish("slack.boom", {"x": 1})

    assert len(fake.errors) == 1
    err = fake.errors[0]
    assert err["msg"] == "events_slack_webhook.handler_exception"
    assert err["event_type"] == "slack.boom"
    assert err["error_type"] == "ValueError"
    assert err["error"] == "kaboom"
    assert "kaboom" in err["traceback"]


def test_publish_continues_to_next_handler_after_exception() -> None:
    """One failing handler must not block siblings on the same event."""
    bus = SlackWebhookEventBus(signing_secret=SIGNING_SECRET)
    received: list[str] = []
    bus.subscribe("slack.boom", lambda e: (_ for _ in ()).throw(RuntimeError("first")))
    bus.subscribe("slack.boom", lambda e: received.append("second"))
    bus.subscribe("slack.boom", lambda e: (_ for _ in ()).throw(RuntimeError("third")))
    bus.subscribe("slack.boom", lambda e: received.append("fourth"))

    bus.publish("slack.boom", {})

    assert received == ["second", "fourth"]


def test_dispatch_returns_200_when_handler_raises() -> None:
    """The Slack-facing HTTP contract: always 200, never 5xx from a bug."""
    bus = SlackWebhookEventBus(signing_secret=SIGNING_SECRET)
    bus.subscribe("slack.slash_command",
                  lambda e: (_ for _ in ()).throw(ValueError("downstream API failed")))

    body = b"command=%2Fintake&user_id=U1&trigger_id=trig.x&channel_id=C1"
    ts = int(time.time())
    headers = {**_sign(body, ts),
               "content-type": "application/x-www-form-urlencoded"}
    result = bus.dispatch(headers=headers, body=body, now=ts)
    assert result.status == 200, f"expected 200 even on handler crash, got {result.status}"


def test_publish_without_logger_falls_back_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When no logger is attached, errors land on stderr — still no propagation."""
    bus = SlackWebhookEventBus(signing_secret=SIGNING_SECRET)
    bus.subscribe("slack.boom", lambda e: (_ for _ in ()).throw(KeyError("nope")))

    bus.publish("slack.boom", {})  # must not raise

    captured = capsys.readouterr()
    assert "events_slack_webhook.handler_exception" in captured.err
    assert "KeyError" in captured.err
