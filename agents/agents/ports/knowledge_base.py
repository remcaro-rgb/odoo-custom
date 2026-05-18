"""KnowledgeBase port — RAG over docs, specs, FAQs.

Default adapter: pgvector.
Other adapters: Chroma, Pinecone, Weaviate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class KbChunk:
    id: str
    title: str
    body: str
    source_url: str | None = None
    metadata: dict = field(default_factory=dict)
    # The vector itself is internal to the adapter; agent code never sees it.


class KnowledgeBase(Protocol):
    def upsert(self, chunks: list[KbChunk]) -> None:
        """Insert or update chunks. The adapter embeds the body and stores it."""
        ...

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        filter: dict | None = None,
    ) -> list[KbChunk]:
        """Semantic search. Returns the top-k chunks ranked by similarity."""
        ...

    def delete(self, ids: list[str]) -> None: ...
