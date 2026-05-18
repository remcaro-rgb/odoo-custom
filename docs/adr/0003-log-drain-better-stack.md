# 0003. Better Stack as the log drain, with Loki migration path

**Date:** 2026-05-16
**Status:** Accepted

## Context

We need a central log drain with: per-tenant tagging, fast search, 30-day hot retention, 1-year cold retention in S3, and reasonable cost at our current scale (~10 GB ingestion/day expected at year-1).

Candidates: Better Stack, Grafana Cloud Loki, self-hosted Loki, Datadog, AWS CloudWatch, Papertrail.

## Decision

We will use **Better Stack** for the centralised log drain, with explicit plan to migrate to **self-hosted Loki on Fly** if monthly ingestion exceeds ~100 GB.

The runtime's `Logger` port abstracts the sink, so the migration is a config change + Loki provisioning, not a code change (per ADR-0007 portable agent runtime).

## Consequences

**Easier:**
- ~$25/month for 30 GB ingestion at year-1 scale. No ops burden — managed.
- Modern search UI, sane defaults, structured-log-friendly.
- Slack/PagerDuty integrations out of the box.

**Harder:**
- Vendor dependency. Mitigated by the `Logger` port abstraction.
- Pricing scales linearly; past ~100 GB/month, self-hosted Loki becomes cheaper even with operator time.

## Alternatives considered

**Self-hosted Loki on Fly.** ~5× cheaper at scale but ~20 hours of setup + ongoing maintenance. Right answer at 100+ GB/month; wrong answer at 10 GB/month with a small team.

**Datadog.** Excellent tool, vastly overkill for our log volume. At $15/host/month + ingestion costs, would be 3–5× the Better Stack cost.

**Grafana Cloud Loki.** Solid; pricing is comparable to Better Stack. Better Stack chosen for nicer UX and easier alerting setup. Will re-evaluate at renewal.

**AWS CloudWatch.** Locks us into AWS; we don't currently use AWS for anything else. Cross-region querying is awkward.
