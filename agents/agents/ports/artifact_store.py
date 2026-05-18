"""ArtifactStore port — blob storage for logs, screenshots, transcripts.

Default adapter: S3-compatible (works with AWS S3, Cloudflare R2, MinIO, B2).
Other adapters: GCS, LocalFS.
"""

from __future__ import annotations

from typing import Protocol


class ArtifactStore(Protocol):
    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Store blob at `key`. Returns the canonical URL."""
        ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def signed_url(self, key: str, *, ttl_seconds: int = 3600) -> str:
        """Return a presigned URL for time-limited read access."""
        ...

    def exists(self, key: str) -> bool: ...
