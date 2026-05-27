"""Intake — parse the incoming GitHub webhook payload into a typed record.

Two payload shapes are accepted:

1. The raw `issues.opened|labeled` webhook event:
       {"action": "...", "issue": {...}, "label": {...}, "repository": {...}}

2. A CLI/test shape with the issue normalised at the top level:
       {"issue": {"number": ..., "title": ..., "body": ..., "labels": [...]}}

Returns an :class:`Intake` record carrying everything downstream modules need.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

# Labels we route on, in priority order. The first one we find wins.
_ROUTING_LABELS = (
    ("feature-request", "feature", "design"),
    ("bug", "bug", "fix"),
)

# Labels we IGNORE — already-handled or non-routing.
_NON_ROUTING = frozenset({"intent-confirmed", "spec-drafted", "awaiting-reporter-confirm"})

_SENSITIVE_PATTERNS = (
    r"(?i)\b(password|api[\s_-]?key|secret|private[\s_-]?key)\b",
    r"(?i)\b(credit[\s_-]?card|cvv|ssn|social[\s_-]?security)\b",
    r"(?i)\b(billing|invoice|refund|chargeback)\b",
    r"(?i)\b(security|breach|cve|0day)\b",
    r"(?i)\b(legal|gdpr|dmca|lawsuit)\b",
)

STALE_DAYS = 30


@dataclass(frozen=True)
class Intake:
    """Structured intake for the drafter and PR opener."""

    action: str                 # "opened" | "labeled" | "synthetic"
    issue_number: int
    issue_title: str
    issue_body: str
    issue_author: str
    issue_url: str
    repo_full_name: str
    labels: tuple[str, ...]
    classification: str         # "feature" | "bug" | "sensitive" | "stale" | "unrouted"
    spec_kind: str              # "design" | "fix" | ""
    created_at: datetime | None


def parse(payload: dict[str, Any], *, now: datetime | None = None) -> Intake:
    """Normalise a webhook payload into a typed Intake."""
    now = now or datetime.now(UTC)
    action = payload.get("action") or "synthetic"
    issue = payload.get("issue") or {}
    repo = payload.get("repository") or {}

    labels_field = issue.get("labels", [])
    labels = _normalise_labels(labels_field)
    title = (issue.get("title") or "").strip()
    body = issue.get("body") or ""
    created_at = _parse_iso(issue.get("created_at"))

    classification, spec_kind = _classify(
        labels=labels, title=title, body=body, created_at=created_at, now=now,
    )

    return Intake(
        action=str(action),
        issue_number=int(issue.get("number") or 0),
        issue_title=title,
        issue_body=body,
        issue_author=(issue.get("user") or {}).get("login", ""),
        issue_url=issue.get("html_url", ""),
        repo_full_name=repo.get("full_name", ""),
        labels=labels,
        classification=classification,
        spec_kind=spec_kind,
        created_at=created_at,
    )


def _normalise_labels(field: Any) -> tuple[str, ...]:
    """Accept either ['foo', 'bar'] or [{'name': 'foo'}, ...]."""
    out: list[str] = []
    for item in field or []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and item.get("name"):
            out.append(str(item["name"]))
    return tuple(out)


def _classify(
    *,
    labels: tuple[str, ...],
    title: str,
    body: str,
    created_at: datetime | None,
    now: datetime,
) -> tuple[str, str]:
    """Return (classification, spec_kind)."""
    if _is_sensitive(title) or _is_sensitive(body):
        return "sensitive", ""
    if created_at is not None and now - created_at > timedelta(days=STALE_DAYS):
        return "stale", ""
    label_set = {label for label in labels if label not in _NON_ROUTING}
    for needle, classification, spec_kind in _ROUTING_LABELS:
        if needle in label_set:
            return classification, spec_kind
    return "unrouted", ""


def _is_sensitive(text: str) -> bool:
    return any(re.search(p, text or "") for p in _SENSITIVE_PATTERNS)


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        # GitHub uses ISO-8601 with 'Z'. Python 3.11+ parses Z natively.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
