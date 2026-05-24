# Phase 4 (Tier 2) — migration-runner image.
#
# Extends the project's odoo-saas base image so the runner can invoke
# `odoo -u all` directly as a subprocess (no Docker-in-Docker). The
# runner adds:
#   - The migration_runner Python package
#   - croniter + psycopg as runtime deps
#   - A new entrypoint that runs `python -m migration_runner` as a
#     long-lived daemon (no HTTP exposure)
#
# Plan §5 dependencies: "bundle Odoo in the runner image — same
# Dockerfile base with migration_runner/ added as an extra stage".
#
# The BASE_IMAGE argument lets ops point the runner at a specific
# enterprise-v1 digest so the migration runs against the SAME Odoo
# code the tenants are about to receive. Default points to ghcr —
# overridable at build time with --build-arg BASE_IMAGE=...
ARG BASE_IMAGE=ghcr.io/goliattco/odoo-saas-odoo:latest
FROM ${BASE_IMAGE} AS runner

LABEL org.opencontainers.image.title="odoo-saas-migration-runner"
LABEL org.opencontainers.image.description="Per-tenant Odoo migration queue consumer. Claims tenant_migration_jobs rows + runs odoo -u all -d <db>."

# The base image's user is `odoo` (uid 1000). We need root briefly to
# install croniter + psycopg + the runner package, then re-drop to a
# non-privileged user.
USER root

# psycopg binary wheel + croniter + the runner package itself.
# Pinned versions match the runner's pyproject.toml constraints; the
# binary wheel for psycopg avoids libpq-dev rebuilds in CI.
RUN pip install --no-cache-dir --break-system-packages \
        "croniter>=2.0,<3.0" \
        "psycopg[binary]>=3.1,<4.0"

# Lay out a clean install root with the SDK convention:
#   /opt/migration_runner_build/
#     ├── pyproject.toml
#     └── migration_runner/        <- the actual package source
# COPY'ing the source dir directly to /opt/migration_runner would put
# the .py files at the install root WITHOUT a `migration_runner/` parent;
# setuptools `packages.find(include=["migration_runner*"])` then matches
# nothing and pip installs an empty package — `python -m migration_runner`
# fails with `No module named migration_runner`.
COPY infra/runners/migration_runner /opt/migration_runner_build/migration_runner
RUN cp /opt/migration_runner_build/migration_runner/pyproject.toml /opt/migration_runner_build/pyproject.toml \
 && pip install --no-cache-dir --break-system-packages /opt/migration_runner_build

# Switch back to the non-privileged user inherited from the base image.
USER odoo

# No port exposure — the runner has no inbound surface.
ENTRYPOINT ["python", "-m", "migration_runner"]
