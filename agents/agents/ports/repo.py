"""Repo port — Git host operations (clone, branch, commit, PR, file ops).

Default adapter: GitHub.
Other adapters: GitLab, Gitea, LocalGit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GitIdentity:
    name: str
    email: str
    gpg_key_id: str | None = None


@dataclass(frozen=True)
class PullRequest:
    number: int
    head_sha: str
    head_branch: str
    base_branch: str
    title: str
    body: str
    labels: tuple[str, ...]
    url: str


class Repo(Protocol):
    """Git host operations.

    Convention: methods that mutate (commit, push, open_pr) accept an explicit
    branch parameter; reads are at HEAD unless `ref=...` is passed.
    """

    # -- workspace ops --
    def checkout(self, branch: str, *, base: str = "main") -> None: ...

    def commit(
        self,
        paths: list[str],
        message: str,
        *,
        author: GitIdentity,
    ) -> str:
        """Stage the given paths and commit. Returns the commit SHA."""
        ...

    def push(self, branch: str) -> None: ...

    # -- PR ops --
    def open_pr(
        self,
        *,
        head: str,
        base: str = "main",
        title: str,
        body: str,
        labels: tuple[str, ...] = (),
    ) -> PullRequest:
        ...

    def add_labels(self, pr: PullRequest, labels: tuple[str, ...]) -> None: ...
    def remove_labels(self, pr: PullRequest, labels: tuple[str, ...]) -> None: ...

    # -- file ops --
    def read(self, path: str, *, ref: str = "HEAD") -> bytes: ...
    def write(self, path: str, content: bytes) -> None: ...

    def list_changed_files(self, base: str, head: str) -> list[str]: ...

    def file_owners(self, path: str) -> list[str]:
        """Resolve CODEOWNERS entries for a path. Returns owner handles."""
        ...
