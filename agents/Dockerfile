FROM python:3.12-slim AS build

LABEL maintainer="Manuel Caro"
LABEL org.opencontainers.image.title="odoo-saas-agents"
LABEL org.opencontainers.image.description="Portable AI-agent runtime — runs every agent on any CI platform."

WORKDIR /build

# System deps for building wheels (some adapters need them)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY agents/ ./agents/
COPY README.md ./

# Install with the "all" extra so every default adapter is available.
RUN pip wheel --no-deps -w /wheels . \
 && pip wheel -w /wheels ".[all]"


FROM python:3.12-slim

LABEL maintainer="Manuel Caro"
LABEL org.opencontainers.image.title="odoo-saas-agents"

# Runtime deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libpq5 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl \
 && rm -rf /wheels

# Default config (operator overrides via mounted volume / env)
COPY config.example.yml /app/config.yml

# Per-environment overrides: load_config picks the right file when
# AGENTS_ENV is set (e.g., AGENTS_ENV=prod -> config.prod.yml). The
# Fly app for slack-intake sets AGENTS_ENV=prod; other deployments
# without the env var still use the base config.yml unchanged.
COPY config.prod.yml /app/config.prod.yml

# Non-root runtime
RUN useradd --no-create-home --uid 1000 agents \
 && chown -R agents:agents /app
USER agents

ENTRYPOINT ["agents"]
CMD ["--help"]
