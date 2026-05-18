"""Hello agent core — end-to-end smoke.

Run with:
    agents run hello --input '{"name": "world"}'

What it does:
    1. Reads README.md from the repo (exercises Repo port).
    2. Asks the LLM to write a one-line haiku about the README's first line.
    3. Posts the haiku to the notifier channel.
    4. Logs end-to-end timing.

If all of this works, every default adapter is wired correctly.
"""

from __future__ import annotations

from ..ports import Message


def run(runtime, payload: dict) -> None:
    """Entry point invoked by `agents run hello`."""
    name = payload.get("name", "world")
    log = runtime.logger.bind(agent="hello", run_id=payload.get("run_id", "smoke"))

    with log.span("hello.run", name=name):
        # 1. Read README.md
        with log.span("hello.read_readme"):
            content = runtime.repo.read("README.md").decode("utf-8", errors="ignore")
        first_line = content.split("\n", 1)[0]
        log.info("hello.first_line", line=first_line[:80])

        # 2. Ask the LLM for a haiku
        with log.span("hello.llm"):
            resp = runtime.llm.chat(
                messages=[
                    Message(
                        role="system",
                        content=(
                            "You are a tiny smoke-test bot. Reply in EXACTLY one line. "
                            "No preamble, no postamble."
                        ),
                    ),
                    Message(
                        role="user",
                        content=(
                            f"Write a one-line greeting for {name!r} that quotes a "
                            f"single word from this line: {first_line!r}"
                        ),
                    ),
                ],
                max_tokens=80, temperature=0.4,
            )
        haiku = resp.content.strip().splitlines()[0] if resp.content else "(empty)"
        log.info("hello.haiku", text=haiku, model=resp.model, cost_usd=resp.cost_usd)

        # 3. Notify
        with log.span("hello.notify"):
            runtime.notifier.send(
                channel=runtime.config.extras.get("slack", {})
                    .get("default_channel", "#devops-agents"),
                summary=f"hello agent · {haiku}",
                details={"name": name, "model": resp.model,
                         "cost_usd": f"${resp.cost_usd:.4f}"},
                severity="info",
            )

    log.info("hello.done")


def iterate(runtime, payload: dict) -> None:
    """No-op — hello agent doesn't iterate."""
    runtime.logger.info("hello.iterate.noop", payload=payload)
