"""EnvVar secret store — the default, dev-friendly secret backend.

Reads secrets from the process environment. Production typically uses Vault
or a platform-native secret store (Fly, Railway, K8s).
"""

from __future__ import annotations

import os

from ..ports import SecretStore


class EnvVarSecretStore:
    """SecretStore backed by os.environ. No SDK dependency."""

    def get(self, name: str) -> str | None:
        return os.environ.get(name)

    def get_or_raise(self, name: str) -> str:
        value = os.environ.get(name)
        if value is None:
            raise KeyError(f"Secret not set in environment: {name}")
        return value

    def list_names(self) -> list[str]:
        # Filter for likely-secret names; never return values.
        candidates = []
        for name in os.environ:
            # Heuristic: caps + (TOKEN | KEY | SECRET | PASSWORD | DSN)
            if name.isupper() and any(
                s in name for s in ("TOKEN", "KEY", "SECRET", "PASSWORD", "DSN")
            ):
                candidates.append(name)
        return sorted(candidates)


_ = SecretStore  # Protocol check
