"""ComputeEnv port — spawn / deploy / destroy ephemeral compute.

Used for preview envs (Implementation Agent) and agentlab.

Default adapter: Fly.
Other adapters: Railway, Kubernetes, DockerLocal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class Deployment:
    name: str
    url: str
    region: str
    image: str
    size: str
    metadata: dict


Status = Literal["spawning", "up", "redeploying", "destroyed", "failed"]


class ComputeEnv(Protocol):
    def spawn(
        self,
        *,
        name: str,
        image: str,
        env: dict[str, str],
        region: str | None = None,
        size: str = "small",
        volume_size_gb: int = 0,
    ) -> Deployment:
        """Create and start a new compute instance."""
        ...

    def deploy(self, deployment: Deployment, image: str) -> None:
        """Update an existing deployment with a new image (rolling)."""
        ...

    def redeploy(self, deployment: Deployment) -> None:
        """Restart with the same image. Used for config-only updates."""
        ...

    def destroy(self, deployment: Deployment) -> None: ...

    def status(self, deployment: Deployment) -> Status: ...

    def secrets_set(
        self,
        deployment: Deployment,
        kv: dict[str, str],
    ) -> None:
        """Set or update deployment-scoped secrets."""
        ...

    def url(self, deployment: Deployment) -> str: ...
