"""Tiny TCP liveness listener for Fly's `[checks.daemon_alive]` probe.

The migration-runner has no inbound HTTP — it polls the queue. Fly's
machine health system needs *something* to probe to decide whether
the daemon process is alive enough to keep the machine running.

The original ``fly.toml`` declared a TCP check on port 9999 but
shipped without binding anything to that port, so every deploy in
this app's history has logged "1 critical" health checks. That
state is cosmetically alarming on every `flyctl status` and makes
`flyctl deploy --wait-timeout` time out waiting for "healthy" even
when the rollout succeeded.

This module binds a background-thread TCP listener on port 9999 and
accept-closes every connection. Fly's TCP check just verifies the
socket accepts — no payload exchange — so an empty accept loop is
sufficient. If the daemon process is killed, the kernel reaps the
socket and the next health probe fails, which is exactly the signal
Fly's restart policy needs.

This does NOT prove the poll loop is making progress; a hung poll
loop with the health thread still scheduling would still pass. That
deeper liveness signal would need either an HTTP /health endpoint
that returns "last tick within N seconds", or per-tick stale-mtime
file probes via a healthcheck script. Both are heavier than what
this app's failure modes warrant — the poll loop is wrapped in
a broad except that re-enters on failure (runner.py:139), so the
hang case is bounded.
"""

from __future__ import annotations

import logging
import socket
import threading

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 9999


def start_health_listener(port: int = _DEFAULT_PORT) -> threading.Thread:
    """Spawn a daemon thread that accept-closes TCP connections on
    ``port`` so Fly's healthcheck can verify the process is alive.

    Returns the thread (mainly so tests can assert it started; the
    daemon doesn't need the handle).

    Binds IPv6 with ``IPV6_V6ONLY=0`` so Fly's check — which uses 6PN
    addressing internally — can reach it without a separate IPv4
    listener.
    """
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('::', port))
    sock.listen(8)

    def _serve() -> None:
        logger.info('health listener accepting on tcp/%d', port)
        try:
            while True:
                conn, _addr = sock.accept()
                conn.close()
        except Exception:  # noqa: BLE001 — broad: never let the thread escape
            # If the socket dies the daemon's overall machine should be
            # restarted by Fly (because the next health check will fail),
            # which is the right behaviour. Log the cause for forensics.
            logger.exception('health listener crashed — Fly will mark unhealthy')

    thread = threading.Thread(
        target=_serve, name='migration-runner-health', daemon=True
    )
    thread.start()
    return thread
