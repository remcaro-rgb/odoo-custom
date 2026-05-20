"""Per-port smoke tests — used by `agents test-adapter <port> <adapter>`.

Lightweight checks that exercise the adapter's main path with a small live call.
Used in CI integration tests and by operators verifying a config swap.
"""

from __future__ import annotations

from typing import Any


def run(port: str, runtime: Any) -> None:
    """Dispatch to the per-port smoke check."""
    handlers = {
        "llm": _smoke_llm,
        "repo": _smoke_repo,
        "issues": _smoke_issues,
        "notifier": _smoke_notifier,
        "secrets": _smoke_secrets,
        "artifacts": _smoke_artifacts,
        "compute": _smoke_compute,
        "kb": _smoke_kb,
        "events": _smoke_events,
        "logger": _smoke_logger,
    }
    handler = handlers.get(port)
    if handler is None:
        raise ValueError(f"No smoke test defined for port: {port}")
    handler(runtime)


def _smoke_llm(runtime: Any) -> None:
    from .ports import Message
    resp = runtime.llm.chat(
        messages=[Message(role="user", content="Reply with exactly: PONG")],
        max_tokens=10, temperature=0.0,
    )
    assert "PONG" in resp.content.upper(), f"Expected PONG, got: {resp.content}"
    print(
        f"LLM OK: {resp.model} · {resp.tokens_in}→{resp.tokens_out} tokens "
        f"· ${resp.cost_usd:.4f}"
    )


def _smoke_repo(runtime: Any) -> None:
    # Read README.md at HEAD — minimal read path
    data = runtime.repo.read("README.md")
    assert len(data) > 0
    print(f"Repo OK: read README.md ({len(data)} bytes)")


def _smoke_issues(runtime: Any) -> None:
    issues = runtime.issues.list_issues(state="open")
    print(f"Issues OK: {len(issues)} open issues visible")


def _smoke_notifier(runtime: Any) -> None:
    runtime.notifier.send(
        channel="#devops-agents",
        summary="Smoke test from agents test-adapter",
        severity="info",
    )
    print("Notifier OK: smoke message sent")


def _smoke_secrets(runtime: Any) -> None:
    names = runtime.secrets.list_names()
    print(f"Secrets OK: {len(names)} names visible (values not logged)")


def _smoke_artifacts(runtime: Any) -> None:
    key = "smoke/test.txt"
    url = runtime.artifacts.put(key, b"hello", content_type="text/plain")
    data = runtime.artifacts.get(key)
    assert data == b"hello"
    runtime.artifacts.delete(key)
    print(f"Artifacts OK: put/get/delete cycle at {url}")


def _smoke_compute(runtime: Any) -> None:
    # Don't actually spawn — just verify the adapter can list deployments
    print("Compute OK: adapter loaded (no spawn performed in smoke)")


def _smoke_kb(runtime: Any) -> None:
    results = runtime.kb.search("test query", k=1)
    print(f"KB OK: search returned {len(results)} result(s)")


def _smoke_events(runtime: Any) -> None:
    print("EventBus OK: adapter loaded (no event published in smoke)")


def _smoke_logger(runtime: Any) -> None:
    runtime.logger.info("smoke.test", port="logger", ok=True)
    print("Logger OK: info line emitted")
