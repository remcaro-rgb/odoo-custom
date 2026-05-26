"""FastAPI service for the slack_intake agent.

Four endpoints — three Slack-side and one GitHub-side — that route through
the corresponding EventBus adapters (signature verification lives in the
adapter, not here).

This module owns:
- HTTP framework wiring (FastAPI)
- Routing inbound bytes into the right EventBus adapter
- The healthz probe Fly uses for machine health
- The kill-switch check (AGENTS_ENABLED config flag)

It does NOT own:
- Slack / GitHub signature verification (that's in the adapters)
- Any business logic (that's in agents.slack_intake.core)
"""

from __future__ import annotations

from typing import Any

# FastAPI symbols must be importable at module scope: combined with
# `from __future__ import annotations`, FastAPI resolves route handler
# parameter types via `eval_forward_ref` in the MODULE's globals. If
# `Request` is only available inside `build_app()`, FastAPI sees the
# string "Request", can't resolve it, and treats `request` as a query
# parameter — every POST returns 422 with "loc":["query","request"].
from fastapi import FastAPI, Request, Response  # noqa: E402

from ..adapters.events_github_webhook import GitHubWebhookEventBus
from ..adapters.events_slack_webhook import SlackWebhookEventBus
from ..bootstrap import Runtime
from ..slack_intake import core as intake_core


def build_app(*, runtime: Runtime) -> Any:
    """Construct a FastAPI app bound to the given runtime.

    Kept separate from `serve()` so tests can drive the app via TestClient
    without binding a real port.
    """
    app = FastAPI(title="odoo-saas-slack-intake")

    slack_bus = _ensure_slack_bus(runtime)
    github_bus = _ensure_github_bus(runtime)

    # Attach the runtime logger to each bus so handler exceptions land as
    # structured log lines (issue #117). Without this, exceptions either
    # propagate to FastAPI as a 500 or go to stderr — both make debugging
    # harder than it needs to be.
    slack_bus.set_logger(runtime.logger)
    github_bus.set_logger(runtime.logger)

    # Subscribe handlers to the actual buses serving each platform — we own
    # two independent EventBus instances (Slack v0 HMAC + GitHub
    # HMAC-SHA256), so passing only `runtime` would subscribe to the wrong
    # one. See _register_handlers in agents.slack_intake.core.
    intake_core._register_handlers(
        runtime, slack_bus=slack_bus, github_bus=github_bus,
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:  # type: ignore[no-untyped-def]
        return {"status": "ok"}

    @app.post("/slack/events")
    async def slack_events(request: Request) -> Response:  # type: ignore[no-untyped-def]
        if not _enabled(runtime):
            return Response(status_code=503, content="agents disabled")
        body = await request.body()
        result = slack_bus.dispatch(
            headers={k.lower(): v for k, v in request.headers.items()},
            body=body,
        )
        return Response(status_code=result.status, content=result.body,
                        media_type=result.content_type)

    @app.post("/slack/commands")
    async def slack_commands(request: Request) -> Response:  # type: ignore[no-untyped-def]
        if not _enabled(runtime):
            return Response(status_code=503, content="agents disabled")
        body = await request.body()
        result = slack_bus.dispatch(
            headers={k.lower(): v for k, v in request.headers.items()},
            body=body,
        )
        return Response(status_code=result.status, content=result.body,
                        media_type=result.content_type)

    @app.post("/slack/interactivity")
    async def slack_interactivity(request: Request) -> Response:  # type: ignore[no-untyped-def]
        if not _enabled(runtime):
            return Response(status_code=503, content="agents disabled")
        body = await request.body()
        result = slack_bus.dispatch(
            headers={k.lower(): v for k, v in request.headers.items()},
            body=body,
        )
        # `slack.modal_submitted` handlers may return a response_action;
        # core returns it from on_modal_submitted via the publish() call
        # mechanism. We keep this endpoint simple: empty 200 closes the modal.
        return Response(status_code=result.status, content=result.body,
                        media_type=result.content_type)

    @app.post("/github/webhook")
    async def github_webhook(request: Request) -> Response:  # type: ignore[no-untyped-def]
        if not _enabled(runtime):
            return Response(status_code=503, content="agents disabled")
        body = await request.body()
        result = github_bus.dispatch(
            headers={k.lower(): v for k, v in request.headers.items()},
            body=body,
        )
        return Response(status_code=result.status, content=result.body,
                        media_type=result.content_type)

    return app


def serve(*, runtime: Runtime, host: str = "0.0.0.0", port: int = 8080) -> None:  # noqa: S104  # nosec B104
    """Bind the FastAPI app to a port and serve forever.

    Binding to 0.0.0.0 is intentional and safe: the Fly Firecracker microVM
    is fronted by Fly's edge proxy, and Fly assigns the VM's IP at runtime
    so we cannot bind to a specific address.
    """
    import uvicorn  # type: ignore[import-untyped]
    app = build_app(runtime=runtime)
    uvicorn.run(app, host=host, port=port, log_level=runtime.config.runtime.log_level)


# ---- helpers ----

def _enabled(runtime: Runtime) -> bool:
    return bool(getattr(runtime.config.runtime, "agents_enabled", True))


def _ensure_slack_bus(runtime: Runtime) -> SlackWebhookEventBus:
    bus = runtime.events
    if isinstance(bus, SlackWebhookEventBus):
        return bus
    # The runtime's events port is bound to a different adapter; spin up a
    # Slack bus alongside. This covers the case where ops binds events to
    # github_webhook (Spec-Gen agent's default) and slack_intake still needs
    # to receive Slack traffic.
    return SlackWebhookEventBus.from_config(runtime.config)


def _ensure_github_bus(runtime: Runtime) -> GitHubWebhookEventBus:
    bus = runtime.events
    if isinstance(bus, GitHubWebhookEventBus):
        return bus
    return GitHubWebhookEventBus.from_config(runtime.config)
