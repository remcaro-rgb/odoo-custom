"""`agents` CLI entry point.

Same image on every platform. Invocation:
    agents run spec-generator [--input '{"issue_id": 1500}']
    agents iterate implementation --pr 1501
    agents handle-commit implementation --branch agent/spec-1500 --sha abc123
    agents preview destroy --spec 1500
    agents config validate
    agents test-adapter llm litellm
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import __version__
from .config import load_config
from .bootstrap import bootstrap

DEFAULT_CONFIG = Path(__file__).parent.parent / "config.yml"


@click.group()
@click.option("--config", type=click.Path(path_type=Path), default=DEFAULT_CONFIG,
              help="Path to config.yml (default: agents/config.yml)")
@click.version_option(version=__version__)
@click.pass_context
def main(ctx: click.Context, config: Path) -> None:
    """odoo-saas-agents — portable AI-agent runtime."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@main.command()
@click.argument("agent_name", type=click.Choice([
    "spec-generator", "implementation", "code", "security", "optimization",
    "support-triage",
]))
@click.option("--input", "input_json", default="{}",
              help="JSON input passed to the agent's entry point")
@click.pass_context
def run(ctx: click.Context, agent_name: str, input_json: str) -> None:
    """Run an agent."""
    config = load_config(ctx.obj["config_path"])
    runtime = bootstrap(config)
    runtime.logger.info("agents.cli.run", agent=agent_name)
    payload = json.loads(input_json)
    _dispatch(agent_name, "run", runtime, payload)


@main.command()
@click.argument("agent_name", type=click.Choice(["spec-generator", "implementation"]))
@click.option("--pr", required=True, type=int)
@click.option("--input", "input_json", default="{}")
@click.pass_context
def iterate(ctx: click.Context, agent_name: str, pr: int, input_json: str) -> None:
    """Iterate an in-flight agent run (reporter feedback, refinement)."""
    config = load_config(ctx.obj["config_path"])
    runtime = bootstrap(config)
    runtime.logger.info("agents.cli.iterate", agent=agent_name, pr=pr)
    payload = {"pr": pr, **json.loads(input_json)}
    _dispatch(agent_name, "iterate", runtime, payload)


@main.command("handle-commit")
@click.argument("agent_name", type=click.Choice(["implementation"]))
@click.option("--branch", required=True)
@click.option("--sha", required=True)
@click.option("--author", required=True)
@click.pass_context
def handle_commit(
    ctx: click.Context, agent_name: str, branch: str, sha: str, author: str,
) -> None:
    """Implementation Agent: react to a human commit on agent/spec-*."""
    config = load_config(ctx.obj["config_path"])
    runtime = bootstrap(config)
    runtime.logger.info("agents.cli.handle_commit", agent=agent_name,
                        branch=branch, sha=sha, author=author)
    _dispatch(agent_name, "handle_commit", runtime,
              {"branch": branch, "sha": sha, "author": author})


@main.group()
def config() -> None:
    """Config subcommands."""


@config.command("validate")
@click.pass_context
def config_validate(ctx: click.Context) -> None:
    """Validate the config file + check that required secrets are reachable."""
    config_obj = load_config(ctx.obj["config_path"])
    # Build runtime — this exercises every adapter's lazy import + from_config
    try:
        bootstrap(config_obj)
    except Exception as exc:
        click.echo(f"FAIL: {exc}", err=True)
        sys.exit(1)
    click.echo("OK — config validates and all configured adapters can initialise.")


@config.command("show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Print resolved config (with env overrides applied; secrets masked)."""
    config_obj = load_config(ctx.obj["config_path"])
    click.echo(json.dumps(config_obj.model_dump(), indent=2, default=str))


@main.command("test-adapter")
@click.argument("port", type=click.Choice([
    "llm", "repo", "issues", "notifier", "secrets", "artifacts",
    "compute", "kb", "events", "logger",
]))
@click.argument("adapter_name")
@click.pass_context
def test_adapter(ctx: click.Context, port: str, adapter_name: str) -> None:
    """Run a smoke test against a specific adapter (uses live credentials)."""
    config_obj = load_config(ctx.obj["config_path"])
    # Override binding for this run
    setattr(config_obj.bindings, port, adapter_name)
    runtime = bootstrap(config_obj)
    runtime.logger.info("agents.cli.test_adapter", port=port, adapter=adapter_name)
    # Adapter-specific smoke test
    from . import smoke
    smoke.run(port, runtime)


@main.group()
def preview() -> None:
    """Preview-env management (Implementation Agent)."""


@preview.command("destroy")
@click.option("--spec", required=True, type=int)
@click.pass_context
def preview_destroy(ctx: click.Context, spec: int) -> None:
    """Destroy preview env for the given spec/issue ID."""
    config_obj = load_config(ctx.obj["config_path"])
    runtime = bootstrap(config_obj)
    _dispatch("implementation", "preview_destroy", runtime, {"spec_id": spec})


@preview.command("list")
@click.pass_context
def preview_list(ctx: click.Context) -> None:
    """List active preview envs."""
    config_obj = load_config(ctx.obj["config_path"])
    runtime = bootstrap(config_obj)
    _dispatch("implementation", "preview_list", runtime, {})


def _dispatch(agent_name: str, action: str, runtime, payload: dict) -> None:
    """Route to the agent's entry point."""
    module_name = agent_name.replace("-", "_")
    try:
        agent_module = __import__(
            f"agents.{module_name}.core", fromlist=[action],
        )
    except ModuleNotFoundError:
        runtime.logger.warn(
            "agents.cli.agent_module_missing",
            agent=agent_name,
            note="The agent module isn't implemented yet (Phase 6+ of the roadmap).",
        )
        click.echo(
            f"Agent {agent_name} not implemented yet. "
            f"See docs/superpowers/specs/2026-05-16-{agent_name}-agent-design.md "
            f"for the design.", err=True,
        )
        sys.exit(2)
    handler = getattr(agent_module, action, None)
    if handler is None:
        click.echo(f"Agent {agent_name} has no '{action}' entry point.", err=True)
        sys.exit(2)
    handler(runtime, payload)
