"""Logger port — structured logging.

Default adapter: StdJSON (JSON to stdout — platform log forwarder picks it up).
Other adapters: Loki, Better Stack, Datadog.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Protocol


class Logger(Protocol):
    def info(self, msg: str, /, **fields: Any) -> None: ...
    def warn(self, msg: str, /, **fields: Any) -> None: ...
    def error(self, msg: str, /, **fields: Any) -> None: ...
    def debug(self, msg: str, /, **fields: Any) -> None: ...

    @contextmanager
    def span(self, name: str, /, **fields: Any) -> Iterator[None]:
        """Start a span — duration is logged on exit. Use as a context manager."""
        ...

    def bind(self, **fields: Any) -> "Logger":
        """Return a new logger with the given fields attached to every event."""
        ...
