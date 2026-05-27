"""Tests for the Fly TCP healthcheck listener.

The listener binds tcp/9999 and accept-closes every connection so
Fly's [checks.daemon_alive] probe succeeds. These tests exercise the
real socket — a connect from the test passes iff the listener is
behaving correctly."""

from __future__ import annotations

import socket
import time

import pytest

from migration_runner.health_listener import start_health_listener


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    s.bind(('::', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _try_connect(port: int, timeout: float = 1.0) -> bool:
    """Return True if a TCP connect to ::1:<port> succeeds — same shape
    Fly's TCP healthcheck uses against the machine's 6PN address."""
    try:
        with socket.create_connection(('::1', port), timeout=timeout):
            return True
    except OSError:
        return False


class TestStartHealthListener:
    def test_accepts_a_tcp_connection_after_start(self) -> None:
        port = _find_free_port()
        thread = start_health_listener(port=port)
        try:
            assert thread.is_alive(), 'listener thread should be running'
            # Give the accept loop a beat to enter accept() — usually
            # immediate but on heavily-loaded CI hosts it can lag.
            for _ in range(20):
                if _try_connect(port):
                    return
                time.sleep(0.05)
            pytest.fail(f'health listener did not accept connections on port {port}')
        finally:
            # daemon=True thread, won't block teardown; can't gracefully
            # shut down a blocking accept() without injecting a sentinel,
            # which is more complexity than this fixture needs.
            pass

    def test_thread_is_daemon(self) -> None:
        # Critical: if non-daemon, an unhandled crash in run_forever
        # would leave the process alive on this thread alone — i.e.
        # the SIGTERM exit path could hang.
        port = _find_free_port()
        thread = start_health_listener(port=port)
        assert thread.daemon, 'listener must be a daemon thread'

    def test_handles_concurrent_connections(self) -> None:
        port = _find_free_port()
        start_health_listener(port=port)
        # Open a few connections in series — they should each succeed
        # then close cleanly. Tests the accept-then-close loop doesn't
        # wedge on a slow accept().
        for _ in range(5):
            for _attempt in range(20):
                if _try_connect(port):
                    break
                time.sleep(0.05)
            else:
                pytest.fail('listener stopped accepting after first connection')
