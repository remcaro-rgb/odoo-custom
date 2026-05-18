"""SecretStore port — agent core never reads secrets directly.

Default adapter: EnvVar (read from process env).
Other adapters: Vault, K8s Secrets, Fly secrets, Railway secrets.
"""

from __future__ import annotations

from typing import Protocol


class SecretStore(Protocol):
    def get(self, name: str) -> str | None:
        """Fetch a secret by name. Returns None if not set.

        Implementations MUST NOT log the value, even at trace level.
        """
        ...

    def get_or_raise(self, name: str) -> str:
        """Like get() but raises KeyError if the secret is missing."""
        ...

    def list_names(self) -> list[str]:
        """Return secret NAMES only — never values."""
        ...
