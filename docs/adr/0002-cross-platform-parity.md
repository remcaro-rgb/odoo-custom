# 0002. Cross-platform Railway + Fly parity

**Date:** 2026-05-15
**Status:** Accepted

## Context

We deploy to Railway and Fly simultaneously. Both are PaaS providers; both have outages; both have pricing surprises. A single-platform deploy is a single point of failure — if Railway has a regional outage during business hours in Colombia, our tenants lose service.

We could mitigate with hot/cold failover, but in practice nobody flips the switch fast enough during an incident.

## Decision

We will **deploy every push to `main` to BOTH Railway and Fly staging** and gate the build red if either platform deploys but the other doesn't. The same parity is enforced for production via the `promote-to-prod` workflow.

In normal operation tenants are served by one platform per pool; the other is hot-standby with up-to-date code. DNS failover is operator-initiated (not automated) because automated failover for a database-backed app is rarely the right call without human eyes.

## Consequences

**Easier:**
- Either platform can have an outage without taking customers down (manual flip).
- We discover platform-specific Dockerfile bugs early (e.g. one platform's env var injection differs).
- Pricing leverage — we can shift load if one platform's pricing changes.

**Harder:**
- 2× deploy cost.
- Two sets of platform-specific config (`infra/fly/`, `infra/railway/`) to keep in sync.
- DNS and traffic-routing complexity (Traefik handles this today).

## Alternatives considered

**Single platform.** Cheaper and simpler, but a platform outage means we're down for hours. Unacceptable for a business-hours-critical product in Colombia.

**Cloud-provider VMs (DigitalOcean, Hetzner).** More control but more ops burden for a small team. The platforms abstract enough of the operational pain that the cost is worth it.

**Kubernetes from day one.** Premature optimisation for current scale. K8s adapter exists in the v7 runtime for the day we need it.
