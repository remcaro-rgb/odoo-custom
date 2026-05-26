#!/usr/bin/env bash
# Build + deploy odoo-saas-slack-intake from a local checkout.
#
# Mirrors what .github/workflows/deploy-slack-intake.yml does in CI, for
# manual deploys (post-secret rotation, image hot-fix, etc.).
#
# Prereqs:
#   flyctl auth login   (with deploy access to the app)
#   The app + volume exist (run ./volume.sh first if not).
#   Secrets are set: see secrets.sample.env for the list.

set -euo pipefail

APP="odoo-saas-slack-intake"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"

echo "Deploying $APP from $REPO_ROOT (rolling strategy) …"
# Build context = agents/ (where the Dockerfile + its COPY-relative files
# all live). Pass it as the positional arg; --config + --dockerfile are
# addressed from the cwd (= repo root).
cd "$REPO_ROOT"
flyctl deploy agents \
  --app "$APP" \
  --config "infra/fly/slack-intake/fly.toml" \
  --dockerfile "agents/Dockerfile" \
  --remote-only \
  --strategy rolling

echo "Smoke-checking /healthz …"
for attempt in 1 2 3 4 5; do
  sleep 6
  code=$(curl -sS -o /dev/null -w '%{http_code}' \
    "https://${APP}.fly.dev/healthz" || echo 000)
  if [ "$code" = "200" ]; then
    echo "OK — healthz returned 200 after $((attempt * 6))s"
    exit 0
  fi
  echo "Attempt $attempt: healthz returned $code; retrying …"
done

echo "FAIL — healthz never returned 200. Investigate with:" >&2
echo "  flyctl logs --app $APP" >&2
exit 1
