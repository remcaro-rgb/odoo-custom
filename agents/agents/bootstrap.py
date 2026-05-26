"""Bootstrap — wires adapters into ports at startup.

Reads `config.bindings`, looks up the corresponding adapter, instantiates it,
and returns a typed container the agent code uses.

If `config.allowed_adapters` is set for a port and the configured binding is
NOT in the allow-list for that port, bootstrap REFUSES to start. This is the
production-safety lock from the portable-runtime spec §12.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Config
from .ports import (
    ArtifactStore,
    ChatOps,
    ComputeEnv,
    EventBus,
    IssueTracker,
    KnowledgeBase,
    LLMProvider,
    Logger,
    Notifier,
    Repo,
    SecretStore,
    StateStore,
)


@dataclass
class Runtime:
    """All adapter instances, wired and ready.

    Any port can be None if its adapter module isn't installed or its
    `from_config` raises (missing secrets, missing optional deps). Agents
    that touch a None port crash at use-time with a clear error; agents
    that never touch it start cleanly. This keeps the runtime usable
    while the broader adapter library is still being filled in.
    """

    llm: LLMProvider | None
    repo: Repo | None
    issues: IssueTracker | None
    notifier: Notifier | None
    chat: ChatOps | None
    secrets: SecretStore | None
    artifacts: ArtifactStore | None
    compute: ComputeEnv | None
    kb: KnowledgeBase | None
    events: EventBus | None
    state: StateStore | None
    logger: Logger
    config: Config


def bootstrap(config: Config) -> Runtime:
    """Instantiate adapters per config.bindings and return a Runtime.

    Ports whose adapter is missing or fails to initialise are set to None
    and logged to stderr. The Logger port is the one exception: it MUST
    initialise, otherwise the runtime has no way to report anything.
    """

    # Production-safety: refuse non-allow-listed adapters
    _enforce_allowlist(config)

    # Logger first — every other failure should be reported through it.
    logger = _make_logger(config)

    notifier = _safe_make("notifier", _make_notifier, config, logger)
    return Runtime(
        llm=_safe_make("llm", _make_llm, config, logger),
        repo=_safe_make("repo", _make_repo, config, logger),
        issues=_safe_make("issues", _make_issues, config, logger),
        notifier=notifier,
        chat=_safe_make_chat(config, fallback=notifier, logger=logger),
        secrets=_safe_make("secrets", _make_secrets, config, logger),
        artifacts=_safe_make("artifacts", _make_artifacts, config, logger),
        compute=_safe_make("compute", _make_compute, config, logger),
        kb=_safe_make("kb", _make_kb, config, logger),
        events=_safe_make("events", _make_events, config, logger),
        state=_safe_make("state", _make_state, config, logger),
        logger=logger,
        config=config,
    )


def _safe_make(
    name: str,
    fn,           # type: ignore[no-untyped-def]
    config: Config,
    logger,       # type: ignore[no-untyped-def]
):
    """Call fn(config); if it raises, log it and return None."""
    try:
        return fn(config)
    except Exception as exc:  # noqa: BLE001 — bootstrap must not crash on optional ports
        logger.warn(
            "bootstrap.port_unavailable",
            port=name,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return None


def _safe_make_chat(
    config: Config,
    *,
    fallback: Any,
    logger,       # type: ignore[no-untyped-def]
):
    try:
        return _make_chat(config, fallback=fallback)
    except Exception as exc:  # noqa: BLE001
        logger.warn(
            "bootstrap.port_unavailable",
            port="chat",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return None


def _enforce_allowlist(config: Config) -> None:
    if not config.allowed_adapters:
        return  # no allow-list configured (typical for dev)
    bindings = config.bindings.model_dump()
    for port_name, allowed in config.allowed_adapters.items():
        if port_name not in bindings:
            continue
        chosen = bindings[port_name]
        if chosen not in allowed:
            raise RuntimeError(
                f"Adapter '{chosen}' for port '{port_name}' is not in "
                f"allowed_adapters: {allowed}. Refusing to start."
            )


def _make_llm(config: Config) -> LLMProvider:
    name = config.bindings.llm
    if name == "litellm":
        from .adapters.llm_litellm import LiteLLMAdapter
        return LiteLLMAdapter.from_config(config)
    if name == "claude":
        from .adapters.llm_claude import ClaudeAdapter
        return ClaudeAdapter.from_config(config)
    if name == "openai":
        from .adapters.llm_openai import OpenAIAdapter
        return OpenAIAdapter.from_config(config)
    if name == "ollama":
        from .adapters.llm_ollama import OllamaAdapter
        return OllamaAdapter.from_config(config)
    raise ValueError(f"Unknown LLM adapter: {name}")


def _make_repo(config: Config) -> Repo:
    name = config.bindings.repo
    if name == "github":
        from .adapters.repo_github import GitHubRepoAdapter
        return GitHubRepoAdapter.from_config(config)
    if name == "gitlab":
        from .adapters.repo_gitlab import GitLabRepoAdapter
        return GitLabRepoAdapter.from_config(config)
    raise ValueError(f"Unknown repo adapter: {name}")


def _make_issues(config: Config) -> IssueTracker:
    name = config.bindings.issues
    if name == "github":
        from .adapters.issues_github import GitHubIssuesAdapter
        return GitHubIssuesAdapter.from_config(config)
    if name == "gitlab":
        from .adapters.issues_gitlab import GitLabIssuesAdapter
        return GitLabIssuesAdapter.from_config(config)
    raise ValueError(f"Unknown issues adapter: {name}")


def _make_notifier(config: Config) -> Notifier:
    name = config.bindings.notifier
    if name == "slack":
        from .adapters.notifier_slack import SlackAdapter
        return SlackAdapter.from_config(config)
    if name == "email":
        from .adapters.notifier_email import EmailAdapter
        return EmailAdapter.from_config(config)
    if name == "webhook":
        from .adapters.notifier_webhook import WebhookAdapter
        return WebhookAdapter.from_config(config)
    raise ValueError(f"Unknown notifier adapter: {name}")


def _make_secrets(config: Config) -> SecretStore:
    name = config.bindings.secrets
    if name == "envvar":
        from .adapters.secrets_envvar import EnvVarSecretStore
        return EnvVarSecretStore()
    if name == "vault":
        from .adapters.secrets_vault import VaultSecretStore
        return VaultSecretStore.from_config(config)
    raise ValueError(f"Unknown secrets adapter: {name}")


def _make_artifacts(config: Config) -> ArtifactStore:
    name = config.bindings.artifacts
    if name == "s3":
        from .adapters.artifacts_s3 import S3ArtifactStore
        return S3ArtifactStore.from_config(config)
    if name == "localfs":
        from .adapters.artifacts_localfs import LocalFsArtifactStore
        return LocalFsArtifactStore.from_config(config)
    raise ValueError(f"Unknown artifacts adapter: {name}")


def _make_compute(config: Config) -> ComputeEnv:
    name = config.bindings.compute
    if name == "fly":
        from .adapters.compute_fly import FlyComputeEnv
        return FlyComputeEnv.from_config(config)
    if name == "railway":
        from .adapters.compute_railway import RailwayComputeEnv
        return RailwayComputeEnv.from_config(config)
    if name == "kubernetes":
        from .adapters.compute_k8s import K8sComputeEnv
        return K8sComputeEnv.from_config(config)
    raise ValueError(f"Unknown compute adapter: {name}")


def _make_kb(config: Config) -> KnowledgeBase:
    name = config.bindings.kb
    if name == "pgvector":
        from .adapters.kb_pgvector import PgVectorKnowledgeBase
        return PgVectorKnowledgeBase.from_config(config)
    if name == "chroma":
        from .adapters.kb_chroma import ChromaKnowledgeBase
        return ChromaKnowledgeBase.from_config(config)
    raise ValueError(f"Unknown KB adapter: {name}")


def _make_events(config: Config) -> EventBus:
    name = config.bindings.events
    if name == "github_webhook":
        from .adapters.events_github_webhook import GitHubWebhookEventBus
        return GitHubWebhookEventBus.from_config(config)
    if name == "slack_webhook":
        from .adapters.events_slack_webhook import SlackWebhookEventBus
        return SlackWebhookEventBus.from_config(config)
    if name == "local_cron":
        from .adapters.events_local_cron import LocalCronEventBus
        return LocalCronEventBus.from_config(config)
    raise ValueError(f"Unknown events adapter: {name}")


def _make_state(config: Config) -> StateStore:
    name = config.bindings.state
    if name == "sqlite":
        from .adapters.state_sqlite import SqliteStateStore
        return SqliteStateStore.from_config(config)
    if name == "memory":
        from .adapters.state_memory import InMemoryStateStore
        return InMemoryStateStore()
    raise ValueError(f"Unknown state adapter: {name}")


def _make_chat(config: Config, *, fallback: Any) -> ChatOps:
    """Resolve the ChatOps adapter.

    If a `chat` binding is set, instantiate that. Otherwise: if the notifier
    is the SlackAdapter (which implements both ports), reuse it; if not,
    instantiate a fresh SlackAdapter for chat ops alone.
    """
    name = getattr(config.bindings, "chat", None)
    if name == "slack":
        from .adapters.notifier_slack import SlackAdapter
        return SlackAdapter.from_config(config)
    if name in (None, ""):
        # Implicit binding: prefer the existing notifier if it is Slack.
        from .adapters.notifier_slack import SlackAdapter
        if isinstance(fallback, SlackAdapter):
            return fallback
        return SlackAdapter.from_config(config)
    raise ValueError(f"Unknown chat adapter: {name}")


def _make_logger(config: Config) -> Logger:
    name = config.bindings.logger
    if name == "stdjson":
        from .adapters.logger_stdjson import StdJsonLogger
        return StdJsonLogger.from_config(config)
    if name == "betterstack":
        from .adapters.logger_betterstack import BetterStackLogger
        return BetterStackLogger.from_config(config)
    raise ValueError(f"Unknown logger adapter: {name}")
