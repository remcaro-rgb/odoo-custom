"""Contract test for Logger port.

Any Logger adapter must:
- Accept info/warn/error/debug calls with arbitrary kwargs.
- Support a span context manager that logs start + end with duration.
- Support bind() returning a new logger with attached fields.
"""

from __future__ import annotations

import json

import pytest

from agents.adapters.logger_stdjson import StdJsonLogger


def _parse_lines(captured: str) -> list[dict]:
    return [json.loads(line) for line in captured.strip().splitlines() if line]


def test_info_emits_json(capsys: pytest.CaptureFixture[str]) -> None:
    log = StdJsonLogger()
    log.info("event.name", agent="test", run_id="r_1")
    out = capsys.readouterr().out
    rows = _parse_lines(out)
    assert len(rows) == 1
    assert rows[0]["msg"] == "event.name"
    assert rows[0]["agent"] == "test"
    assert rows[0]["run_id"] == "r_1"
    assert rows[0]["level"] == "info"


def test_levels(capsys: pytest.CaptureFixture[str]) -> None:
    log = StdJsonLogger()
    log.info("a")
    log.warn("b")
    log.error("c")
    log.debug("d")
    rows = _parse_lines(capsys.readouterr().out)
    assert [r["level"] for r in rows] == ["info", "warn", "error", "debug"]


def test_span_logs_start_and_end(capsys: pytest.CaptureFixture[str]) -> None:
    log = StdJsonLogger()
    with log.span("phase.x", agent="test"):
        pass
    rows = _parse_lines(capsys.readouterr().out)
    assert len(rows) == 2
    assert rows[0]["msg"] == "phase.x.start"
    assert rows[1]["msg"] == "phase.x.end"
    assert rows[1]["duration_ms"] >= 0


def test_span_logs_error_on_exception(capsys: pytest.CaptureFixture[str]) -> None:
    log = StdJsonLogger()
    with pytest.raises(ValueError, match="boom"):
        with log.span("phase.y"):
            raise ValueError("boom")
    rows = _parse_lines(capsys.readouterr().out)
    assert any(r["msg"] == "phase.y.error" and r["level"] == "error"
               for r in rows)


def test_bind_attaches_fields(capsys: pytest.CaptureFixture[str]) -> None:
    log = StdJsonLogger()
    bound = log.bind(agent="test", run_id="r_42")
    bound.info("event.x", extra="yes")
    rows = _parse_lines(capsys.readouterr().out)
    assert rows[0]["agent"] == "test"
    assert rows[0]["run_id"] == "r_42"
    assert rows[0]["extra"] == "yes"


def test_serialize_failure_is_safe(capsys: pytest.CaptureFixture[str]) -> None:
    log = StdJsonLogger()
    # A non-serialisable field — must not crash
    class Weird:
        pass

    log.info("event.weird", thing=Weird())
    rows = _parse_lines(capsys.readouterr().out)
    # Either str() serialised via default=str, or fell back to safe minimal
    assert len(rows) == 1
