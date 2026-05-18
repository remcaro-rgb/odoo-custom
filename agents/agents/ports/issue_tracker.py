"""IssueTracker port — issues, comments, labels.

Default adapter: GitHub Issues.
Other adapters: GitLab Issues, Linear, Jira.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str
    labels: tuple[str, ...]
    state: str          # "open" | "closed"
    author: str
    url: str


@dataclass(frozen=True)
class Comment:
    id: int
    body: str
    author: str
    issue_number: int


class IssueTracker(Protocol):
    def open_issue(
        self,
        *,
        title: str,
        body: str,
        labels: tuple[str, ...] = (),
    ) -> Issue: ...

    def comment(self, issue: Issue, body: str) -> Comment: ...

    def edit_comment(self, comment: Comment, body: str) -> None: ...

    def add_label(self, issue: Issue, label: str) -> None: ...

    def remove_label(self, issue: Issue, label: str) -> None: ...

    def list_issues(
        self,
        *,
        labels: tuple[str, ...] | None = None,
        state: str = "open",
    ) -> list[Issue]: ...

    def search_similar(self, text: str, *, limit: int = 5) -> list[Issue]:
        """Embedding-based similar-issue search. Used for duplicate detection."""
        ...
