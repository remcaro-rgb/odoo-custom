"""Config loader.

Reads YAML with env-var overrides. Env vars use the prefix `AGENTS_` and
underscore-separated keys: `AGENTS_BINDINGS_LLM=ollama` overrides
`bindings.llm` in the YAML.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class RuntimeConfig(BaseModel):
    log_level: str = "info"
    spend_cap_monthly_usd: float = 250.0
    agents_enabled: bool = True


class Bindings(BaseModel):
    llm: str = "litellm"
    repo: str = "github"
    issues: str = "github"
    notifier: str = "slack"
    secrets: str = "envvar"
    artifacts: str = "s3"
    compute: str = "fly"
    kb: str = "pgvector"
    events: str = "github_webhook"
    logger: str = "stdjson"


class Config(BaseModel):
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    bindings: Bindings = Field(default_factory=Bindings)
    # Adapter-specific configuration is loose — adapters parse what they need.
    extras: dict[str, Any] = Field(default_factory=dict)
    allowed_adapters: dict[str, list[str]] = Field(default_factory=dict)
    agents: dict[str, dict[str, Any]] = Field(default_factory=dict)


def load_config(path: str | Path = "config.yml") -> Config:
    """Load YAML config, then apply AGENTS_* env overrides.

    Layered: agents/config.yml → agents/config.<env>.yml → AGENTS_* env vars.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found at {path}")

    with path.open() as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}

    # Apply per-environment override file if AGENTS_ENV is set
    env_name = os.environ.get("AGENTS_ENV")
    if env_name:
        env_path = path.parent / f"config.{env_name}.yml"
        if env_path.exists():
            with env_path.open() as f:
                _deep_merge(data, yaml.safe_load(f) or {})

    # Apply AGENTS_* env vars
    _apply_env_overrides(data)

    # Pydantic validates and applies defaults
    return _build_config(data)


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> None:
    for key, value in over.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _apply_env_overrides(data: dict[str, Any]) -> None:
    """Map AGENTS_<SECTION>_<KEY> → data[section][key]."""
    prefix = "AGENTS_"
    for env_key, env_value in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        path_parts = [p.lower() for p in env_key[len(prefix):].split("_")]
        if len(path_parts) < 2:
            continue
        node = data
        for part in path_parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                # Conflict with non-dict scalar; ignore the override
                break
        else:
            node[path_parts[-1]] = _coerce(env_value)


def _coerce(s: str) -> Any:
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _build_config(data: dict[str, Any]) -> Config:
    """Pull known sections; bundle the rest into `extras`."""
    known = {"runtime", "bindings", "allowed_adapters", "agents"}
    extras = {k: v for k, v in data.items() if k not in known}
    return Config(
        runtime=RuntimeConfig(**data.get("runtime", {})),
        bindings=Bindings(**data.get("bindings", {})),
        allowed_adapters=data.get("allowed_adapters", {}),
        agents=data.get("agents", {}),
        extras=extras,
    )
