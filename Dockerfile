FROM python:3.12-slim

LABEL maintainer="Manuel Caro"

# System dependencies — all in one RUN layer to avoid stale cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
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
    && rm -rf /var/lib/apt/lists/*

# wkhtmltopdf — patched-Qt build from wkhtmltopdf/packaging (NOT distro package)
# apt-get update required again here because lists were cleared in the prior layer
ARG WKHTMLTOPDF_VERSION=0.12.6.1-3
RUN ARCH=$(dpkg --print-architecture) \
    && apt-get update \
    && curl -sSL -o /tmp/wkhtmltox.deb \
    "https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOPDF_VERSION}/wkhtmltox_${WKHTMLTOPDF_VERSION}.bookworm_${ARCH}.deb" \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm /tmp/wkhtmltox.deb \
    && rm -rf /var/lib/apt/lists/*

# less CSS compiler (node-less apt package not available on Bookworm)
RUN npm install -g less

# Python dependencies from Odoo source
COPY odoo/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Install Odoo itself (makes odoo-bin available as a Python package)
COPY odoo /odoo
RUN pip install --no-cache-dir -e /odoo

# Odoo filestore directory
RUN mkdir -p /var/lib/odoo

EXPOSE 8069

# Run as non-root user for security
# --no-create-home because /odoo already exists (populated by COPY above)
RUN useradd --no-create-home -u 1000 odoo \
    && chown -R odoo:odoo /var/lib/odoo
USER odoo

CMD ["/odoo/odoo-bin", "--config=/etc/odoo/odoo.conf"]
