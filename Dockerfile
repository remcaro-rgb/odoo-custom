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

# Config (currently named odoo-railway.conf for historical reasons; the contents
# are platform-agnostic. Workers / log level can be overridden via env at runtime.)
COPY config/odoo-railway.conf /etc/odoo/odoo.conf

# Platform-agnostic entrypoint
COPY infra/odoo-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Odoo filestore directory
RUN mkdir -p /var/lib/odoo

EXPOSE 8069

# Run as non-root user
RUN useradd --no-create-home -u 1000 odoo \
    && chown -R odoo:odoo /var/lib/odoo /mnt/custom-addons /mnt/jorels-addons

USER odoo

ENTRYPOINT ["/entrypoint.sh"]
