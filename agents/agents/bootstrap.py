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
    ComputeEnv,
    EventBus,
    IssueTracker,
    KnowledgeBase,
    LLMProvider,
    Logger,
    Notifier,
    Repo,
    SecretStore,
)


@dataclass
class Runtime:
    """All adapter instances, wired and ready."""

    llm: LLMProvider
    repo: Repo
    issues: IssueTracker
    notifier: Notifier
    secrets: SecretStore
    artifacts: ArtifactStore
    compute: ComputeEnv
    kb: KnowledgeBase
    events: EventBus
    logger: Logger
    config: Config


def bootstrap(config: Config) -> Runtime:
    """Instantiate adapters per config.bindings and return a Runtime."""

    # Production-safety: refuse non-allow-listed adapters
    _enforce_allowlist(config)

    # Each adapter import is lazy so optional deps don't break dev installs
    return Runtime(
        llm=_make_llm(config),
        repo=_make_repo(config),
        issues=_make_issues(config),
        notifier=_make_notifier(config),
        secrets=_make_secrets(config),
        artifacts=_make_artifacts(config),
        compute=_make_compute(config),
        kb=_make_kb(config),
        events=_make_events(config),
        logger=_make_logger(config),
        config=config,
    )


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
    if name == "local_cron":
        from .adapters.events_local_cron import LocalCronEventBus
        return LocalCronEventBus.from_config(config)
    raise ValueError(f"Unknown events adapter: {name}")


def _make_logger(config: Config) -> Logger:
    name = config.bindings.logger
    if name == "stdjson":
        from .adapters.logger_stdjson import StdJsonLogger
        return StdJsonLogger.from_config(config)
    if name == "betterstack":
        from .adapters.logger_betterstack import BetterStackLogger
        return BetterStackLogger.from_config(config)
    raise ValueError(f"Unknown logger adapter: {name}")
