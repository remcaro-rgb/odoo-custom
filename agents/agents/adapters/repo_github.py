"""GitHub Repo adapter — the default.

Implements the Repo port against the GitHub API + a local git working tree.
The working tree is expected to be checked out by the workflow's
`actions/checkout` step before the agent runs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import Config
from ..ports import GitIdentity, PullRequest, Repo

if TYPE_CHECKING:
    pass


class GitHubRepoAdapter:
    """Repo adapter for GitHub. Combines local git ops + GitHub REST API."""

    def __init__(self, *, org: str, repo: str, token: str,
                 service_account: str, working_tree: Path | None = None) -> None:
        self._org = org
        self._repo = repo
        self._service_account = service_account
        self._working_tree = working_tree or Path.cwd()
        from github import Github  # type: ignore[import-untyped]
        self._gh = Github(token)
        self._token = token
        self._gh_repo = self._gh.get_repo(f"{org}/{repo}")

    @classmethod
    def from_config(cls, config: Config) -> GitHubRepoAdapter:
        from .secrets_envvar import EnvVarSecretStore
        secrets = EnvVarSecretStore()
        gh_cfg = config.extras.get("github", {})
        return cls(
            org=gh_cfg.get("org", ""),
            repo=gh_cfg.get("repo", ""),
            token=secrets.get_or_raise(gh_cfg.get("token_secret", "GITHUB_TOKEN")),
            service_account=gh_cfg.get("service_account", "agents-bot"),
        )

    # ---------------- workspace ops ----------------

    def _git(self, *args: str) -> str:
        # Calling git with a fixed argv[0] and untrusted args in argv[1+] is
        # safe — no shell interpolation, no PATH lookup ambiguity beyond
        # whichever `git` is first on PATH (we accept that risk in CI;
        # the runner image controls PATH).
        result = subprocess.run(  # noqa: S603,S607
            ["git", *args],
            cwd=self._working_tree,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def checkout(self, branch: str, *, base: str = "main") -> None:
        self._git("fetch", "origin", base)
        # Try to switch; if not present, create
        try:
            self._git("checkout", branch)
        except subprocess.CalledProcessError:
            self._git("checkout", "-b", branch, f"origin/{base}")

    def commit(self, paths: list[str], message: str, *,
               author: GitIdentity) -> str:
        for p in paths:
            self._git("add", p)
        env = {
            "GIT_AUTHOR_NAME": author.name,
            "GIT_AUTHOR_EMAIL": author.email,
            "GIT_COMMITTER_NAME": author.name,
            "GIT_COMMITTER_EMAIL": author.email,
        }
        commit_cmd = ["git", "commit", "-m", message]
        if author.gpg_key_id:
            commit_cmd.append(f"--gpg-sign={author.gpg_key_id}")
        subprocess.run(  # noqa: S603,S607
            commit_cmd,
            cwd=self._working_tree,
            check=True,
            env={**__import__("os").environ, **env},
        )
        return self._git("rev-parse", "HEAD").strip()

    def push(self, branch: str) -> None:
        self._git("push", "-u", "origin", branch)

    # ---------------- PR ops ----------------

    def open_pr(self, *, head: str, base: str = "main",
                title: str, body: str,
                labels: tuple[str, ...] = ()) -> PullRequest:
        pr = self._gh_repo.create_pull(title=title, body=body, head=head, base=base)
        if labels:
            pr.add_to_labels(*labels)
        return PullRequest(
            number=pr.number, head_sha=pr.head.sha, head_branch=pr.head.ref,
            base_branch=pr.base.ref, title=pr.title, body=pr.body or "",
            labels=tuple(label.name for label in pr.labels), url=pr.html_url,
        )

    def add_labels(self, pr: PullRequest, labels: tuple[str, ...]) -> None:
        gh_pr = self._gh_repo.get_pull(pr.number)
        gh_pr.add_to_labels(*labels)

    def remove_labels(self, pr: PullRequest, labels: tuple[str, ...]) -> None:
        gh_pr = self._gh_repo.get_pull(pr.number)
        for label in labels:
            try:
                gh_pr.remove_from_labels(label)
            except Exception:  # noqa: BLE001
                # Already removed or label doesn't exist; idempotent op.
                logger = __import__("logging").getLogger(__name__)
                logger.debug("remove_from_labels: %s not present on PR #%d", label, pr.number)

    # ---------------- file ops ----------------

    def read(self, path: str, *, ref: str = "HEAD") -> bytes:
        # Read from working tree at the given ref via git show
        return subprocess.run(  # noqa: S603,S607
            ["git", "show", f"{ref}:{path}"],
            cwd=self._working_tree, check=True, capture_output=True,
        ).stdout

    def write(self, path: str, content: bytes) -> None:
        full = self._working_tree / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)

    def list_changed_files(self, base: str, head: str) -> list[str]:
        out = self._git("diff", "--name-only", f"{base}..{head}")
        return [line for line in out.splitlines() if line]

    def file_owners(self, path: str) -> list[str]:
        """Parse .github/CODEOWNERS and return the owners for `path`.

        Simple glob matching; last matching rule wins (CODEOWNERS semantics).
        """
        codeowners_path = self._working_tree / ".github" / "CODEOWNERS"
        if not codeowners_path.exists():
            return []
        owners: list[str] = []
        for line in codeowners_path.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            pattern, *line_owners = parts
            if self._matches(pattern, path):
                owners = line_owners
        return owners

    @staticmethod
    def _matches(pattern: str, path: str) -> bool:
        import fnmatch
        # CODEOWNERS uses gitignore-style patterns; fnmatch covers the common cases
        if pattern.startswith("/"):
            pattern = pattern[1:]
        if pattern.endswith("/"):
            return path.startswith(pattern)
        return fnmatch.fnmatch(path, pattern) or path.startswith(pattern.rstrip("/") + "/")


_ = Repo  # Protocol check
