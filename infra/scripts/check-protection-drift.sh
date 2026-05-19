#!/usr/bin/env bash
#
# Compare the live branch-protection required-check list on `main` against
# the committed source-of-truth in .github/required-checks.yml.
#
# Run with a token that has repo admin (a personal classic PAT with `repo`
# scope, or a GitHub App installation token with `Administration: read`):
#
#   GH_TOKEN=ghp_xxx ./infra/scripts/check-protection-drift.sh
#
# Exits 0 if live == committed; non-zero with a diff if they drifted.

set -euo pipefail

REPO="${REPO:-GoliattCo/odoo-custom}"
BRANCH="${BRANCH:-main}"
COMMITTED_FILE=".github/required-checks.yml"

if ! command -v gh >/dev/null; then
    echo "error: gh CLI not on PATH" >&2
    exit 2
fi

# Live list from API
gh api "repos/${REPO}/branches/${BRANCH}/protection" \
    --jq '.required_status_checks.contexts[]' 2>/dev/null \
    | sort -u > /tmp/protection-live.txt

# Committed list from yaml
python3 - <<PY > /tmp/protection-committed.txt
import yaml, pathlib, sys
d = yaml.safe_load(pathlib.Path("${COMMITTED_FILE}").read_text())
for c in sorted(set(d.get("main", []))):
    print(c)
PY

if diff -u /tmp/protection-committed.txt /tmp/protection-live.txt; then
    echo "OK: live branch protection on ${BRANCH} matches ${COMMITTED_FILE}"
    exit 0
else
    echo "DRIFT detected between ${COMMITTED_FILE} and live ${BRANCH} protection." >&2
    echo "Resolve by either (a) committing the live list, or (b) applying the committed list" >&2
    echo "with: ./infra/scripts/apply-required-checks.sh" >&2
    exit 1
fi
