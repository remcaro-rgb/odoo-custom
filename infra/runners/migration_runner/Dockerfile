# Phase 4 (Tier 2) — migration-runner image (self-contained).
#
# Earlier versions extended `ghcr.io/goliattco/odoo-saas-odoo:latest` so the
# runner could invoke `odoo -u all` as a subprocess. That worked locally but
# Fly's Depot remote builder cannot authenticate to private GHCR refs from
# `FROM` lines (no flyctl flag exists to pass docker registry creds to the
# builder's image-resolver). Rather than chain custom builder VMs, this
# Dockerfile installs Odoo from upstream directly + COPIES the same addons
# the standard image bundles. Result:
#
#   * Pure-public-base image (python:3.12-slim) — Fly remote-builds cleanly
#   * Same Odoo 19.0 commit pin as the standard image (single source of truth
#     for the ODOO_COMMIT ARG between this and the root Dockerfile)
#   * Same custom-addons + jorels addons baked in, so `odoo -u all` against
#     a tenant DB resolves every addon the tenant has installed
#   * Plus the migration_runner Python package + croniter/psycopg
#
# Tradeoff: ~250MB build context (custom-addons + jorels-addons + Odoo
# clone). Build time ~4-6 min on Fly's remote builder; cached by buildx
# after the first run.

FROM python:3.12-slim

LABEL org.opencontainers.image.title="odoo-saas-migration-runner"
LABEL org.opencontainers.image.description="Per-tenant Odoo migration queue consumer. Claims tenant_migration_jobs rows + runs odoo -u all -d <db>."

# System dependencies — mirror the root Dockerfile's layer so the runner
# can satisfy every wheel build during Odoo's pip install. The list is
# intentionally identical (minus wkhtmltopdf, which the runner doesn't
# need for `odoo -u all` — only used for report rendering at runtime).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        libpq-dev \
        libxml2-dev \
        libxslt1-dev \
        libldap2-dev \
        libsasl2-dev \
        libjpeg-dev \
        libssl-dev \
        libffi-dev \
        curl \
        ca-certificates \
        fonts-noto-cjk \
        fontconfig \
        libfreetype6 \
        libjpeg62-turbo \
        libpng16-16 \
        nodejs \
        npm \
        postgresql-client \
        gosu \
    && rm -rf /var/lib/apt/lists/*

# less CSS compiler — needed because Odoo's `-u all` recompiles assets
# for installed modules, and several core modules pull in less sources.
RUN npm install -g less

# Odoo 19.0 — same commit pin as the root Dockerfile. Bumping this on the
# runner without bumping the root Dockerfile risks the runner running a
# different Odoo than the tenant pool, so keep them in sync.
ARG ODOO_COMMIT=36251c03d81188c04faca77f9d14abe782486b49
RUN git clone --depth 1 --branch 19.0 https://github.com/odoo/odoo.git /odoo \
    && cd /odoo && git fetch --depth 1 origin $ODOO_COMMIT && git checkout $ODOO_COMMIT \
    && rm -rf /odoo/.git
RUN pip install --no-cache-dir -r /odoo/requirements.txt
RUN pip install --no-cache-dir -e /odoo

# Jorels Colombian localization + custom addons (same source-of-truth as
# the root Dockerfile, copied from the same build context).
COPY jorels-addons /mnt/jorels-addons
COPY custom-addons /mnt/custom-addons

# Odoo config (the platform-agnostic one shared with the tenant image).
COPY config/odoo-railway.conf /etc/odoo/odoo.conf

# Reuse the same entrypoint Odoo apps use — when the runner spawns a
# subprocess it invokes this script with TARGET_DB + UPDATE_MODULES=all
# + STOP_AFTER_INIT=1 set.
COPY infra/odoo-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Odoo filestore (mostly unused by the runner — `-u all` doesn't need
# the filestore to be writable beyond Odoo's own startup scaffolding).
RUN mkdir -p /var/lib/odoo

# Create the unprivileged odoo user (uid 1000), mirroring the root image
# for parity with the entrypoint's gosu drop.
RUN useradd --no-create-home -u 1000 odoo \
    && chown -R odoo:odoo /var/lib/odoo /mnt/custom-addons /mnt/jorels-addons

# --- flyctl (for pgbackrest SSH-delegation in snapshot.py + rollback.py) ---
# rollback.py and SNAPSHOT_MODE=ssh both shell out via
# `flyctl ssh console --app odoo-saas-postgres -C "..."` so the
# pgbackrest binary + stanza config + S3 creds stay on the Postgres
# machine. Install the official Fly install script; pinned to a
# known-good version for reproducibility.
ENV FLYCTL_INSTALL=/opt/flyctl
ENV PATH=$FLYCTL_INSTALL/bin:$PATH
# fly.io/install.sh's version arg only accepts release-tag forms it
# can find in github.com/superfly/flyctl/releases — `0.3.197` is
# rejected (not a real release at the time of build) and any other
# specific pin risks similar failure when the release is later
# pruned/renamed. Track latest stable; flyctl is mature and we don't
# depend on a specific feature beyond `ssh console --command`, which
# has been stable for years.
RUN curl -L https://fly.io/install.sh | sh

# --- migration_runner package ---
# psycopg binary wheel + croniter as runtime deps for the runner itself.
RUN pip install --no-cache-dir \
        "croniter>=2.0,<3.0" \
        "psycopg[binary]>=3.1,<4.0"

# Lay out a clean install root with the parent-named-subdir convention
# so setuptools' `packages.find(include=["migration_runner*"])` matches
# (caught by the smoke step in build-migration-runner.yml).
COPY infra/runners/migration_runner /opt/migration_runner_build/migration_runner
RUN cp /opt/migration_runner_build/migration_runner/pyproject.toml /opt/migration_runner_build/pyproject.toml \
 && pip install --no-cache-dir /opt/migration_runner_build

# No inbound port — the runner has no HTTP surface.
ENTRYPOINT ["python", "-m", "migration_runner"]
