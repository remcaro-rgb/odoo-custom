FROM python:3.12-slim

LABEL maintainer="Manuel Caro"
LABEL org.opencontainers.image.title="odoo-saas"
LABEL org.opencontainers.image.description="Odoo 19 + Colombia localization (Jorels) + custom addons, platform-agnostic image. Multi-tenant via dbfilter=^%d$."

# System dependencies — all in one RUN layer
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
    gnupg \
    ca-certificates \
    fonts-noto-cjk \
    fontconfig \
    libfreetype6 \
    libjpeg62-turbo \
    libpng16-16 \
    libx11-6 \
    libxcb1 \
    libxext6 \
    libxrender1 \
    xfonts-75dpi \
    xfonts-base \
    nodejs \
    npm \
    postgresql-client \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# wkhtmltopdf — patched-Qt build from wkhtmltopdf/packaging
ARG WKHTMLTOPDF_VERSION=0.12.6.1-3
RUN ARCH=$(dpkg --print-architecture) \
    && apt-get update \
    && curl -sSL -o /tmp/wkhtmltox.deb \
    "https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOPDF_VERSION}/wkhtmltox_${WKHTMLTOPDF_VERSION}.bookworm_${ARCH}.deb" \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm /tmp/wkhtmltox.deb \
    && rm -rf /var/lib/apt/lists/*

# less CSS compiler
RUN npm install -g less

# Clone Odoo 19.0 from GitHub (pinned to exact commit)
ARG ODOO_COMMIT=36251c03d81188c04faca77f9d14abe782486b49
RUN git clone --depth 1 --branch 19.0 https://github.com/odoo/odoo.git /odoo \
    && cd /odoo && git fetch --depth 1 origin $ODOO_COMMIT && git checkout $ODOO_COMMIT \
    && rm -rf /odoo/.git

# Python dependencies from Odoo source
RUN pip install --no-cache-dir -r /odoo/requirements.txt
RUN pip install --no-cache-dir -e /odoo

# Jorels Colombian localization addons (copied from build context)
COPY jorels-addons /mnt/jorels-addons

# Copy custom addons (small, from build context)
COPY custom-addons /mnt/custom-addons

# Phase 4.1: license signing pubkey. saas_license_gate verifies the
# Ed25519 signature on the /v1/check response against this key at
# install time and on every hourly cron tick. The dev key is shipped
# in the main image; production enterprise builds use `--build-arg
# LICENSE_PUBKEY_FILE=infra/keys/license-signing-pubkey.pem` (the
# rotated, non-leaked key — see infra/keys/README.md). When the gate
# addon is not installed (i.e., shared SaaS pool images), this file
# is unused but harmless.
ARG LICENSE_PUBKEY_FILE=infra/keys/license-signing-pubkey.dev.pem
COPY ${LICENSE_PUBKEY_FILE} /etc/saas-license-pubkey.pem

# Config (currently named odoo-railway.conf for historical reasons; the contents
# are platform-agnostic. Workers / log level can be overridden via env at runtime.)
COPY config/odoo-railway.conf /etc/odoo/odoo.conf

# Platform-agnostic entrypoint
COPY infra/odoo-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Odoo filestore directory
RUN mkdir -p /var/lib/odoo

EXPOSE 8069

# Create the unprivileged odoo user (uid 1000). We do NOT `USER odoo` here:
# the entrypoint starts as root so it can chown a freshly-mounted (root-owned)
# data volume, then drops to `odoo` via gosu before exec'ing Odoo. Running odoo
# as a non-root user is still enforced — just done at runtime, not build time.
RUN useradd --no-create-home -u 1000 odoo \
    && chown -R odoo:odoo /var/lib/odoo /mnt/custom-addons /mnt/jorels-addons

ENTRYPOINT ["/entrypoint.sh"]
