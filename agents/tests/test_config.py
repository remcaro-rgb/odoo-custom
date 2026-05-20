"""Tests for the config loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agents.config import load_config


@pytest.fixture
def fixture_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.yml"
    cfg.write_text(yaml.safe_dump({
        "runtime": {"log_level": "info"},
        "bindings": {"llm": "litellm", "repo": "github"},
        "litellm": {"model": "claude-sonnet-4-6"},
        "allowed_adapters": {"llm": ["litellm", "claude"]},
    }))
    return cfg


def test_load_basic(fixture_config: Path) -> None:
    config = load_config(fixture_config)
    assert config.bindings.llm == "litellm"
    assert config.bindings.repo == "github"
    assert config.extras["litellm"]["model"] == "claude-sonnet-4-6"


def test_env_override(fixture_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTS_BINDINGS_LLM", "ollama")
    config = load_config(fixture_config)
    assert config.bindings.llm == "ollama"


def test_env_layered_override(
    fixture_config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "config.staging.yml").write_text(
        yaml.safe_dump({"bindings": {"notifier": "teams"}})
    )
    monkeypatch.setenv("AGENTS_ENV", "staging")
    config = load_config(fixture_config)
    assert config.bindings.notifier == "teams"
    # Base still wins where staging didn't override
    assert config.bindings.repo == "github"


def test_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yml")
