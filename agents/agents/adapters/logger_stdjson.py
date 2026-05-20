"""StdJSON logger — JSON to stdout. Platform log forwarders pick this up.

The default Logger adapter. Cheap, portable, works on every CI runner and
every container platform.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ..config import Config
from ..ports import Logger


class StdJsonLogger:
    """Structured JSON to stdout, with span timing.

    Compatible with the Logger port. Output format:

        {"ts": "...", "level": "info", "msg": "...", **fields}
    """

    def __init__(self, bound: dict[str, Any] | None = None) -> None:
        self._bound = bound or {}

    @classmethod
    def from_config(cls, config: Config) -> StdJsonLogger:
        return cls()

    def _emit(self, level: str, msg: str, fields: dict[str, Any]) -> None:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": level,
            "msg": msg,
            **self._bound,
            **fields,
        }
        try:
            line = json.dumps(record, default=str, separators=(",", ":"))
        except (TypeError, ValueError):
            # Be defensive: fall back to a safe minimal record
            line = json.dumps({
                "ts": record["ts"], "level": "error", "msg": "logger_serialize_failed",
                "original_msg": msg,
            })
        print(line, file=sys.stdout, flush=True)

    def info(self, msg: str, /, **fields: Any) -> None:
        self._emit("info", msg, fields)

    def warn(self, msg: str, /, **fields: Any) -> None:
        self._emit("warn", msg, fields)

    def error(self, msg: str, /, **fields: Any) -> None:
        self._emit("error", msg, fields)

    def debug(self, msg: str, /, **fields: Any) -> None:
        self._emit("debug", msg, fields)

    @contextmanager
    def span(self, name: str, /, **fields: Any) -> Iterator[None]:
        start = time.perf_counter()
        self._emit("info", f"{name}.start", fields)
        try:
            yield
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self._emit("error", f"{name}.error",
                       {**fields, "duration_ms": duration_ms,
                        "error": type(exc).__name__, "error_msg": str(exc)})
            raise
        else:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self._emit("info", f"{name}.end", {**fields, "duration_ms": duration_ms})

    def bind(self, **fields: Any) -> StdJsonLogger:
        return StdJsonLogger({**self._bound, **fields})


_ = Logger  # Protocol check
