FROM traefik:v3.2

LABEL org.opencontainers.image.title="odoo-saas-traefik"
LABEL org.opencontainers.image.description="Traefik v3 — tenant-aware router for the Odoo SaaS data plane. Static config baked in; dynamic routes live in Redis KV at runtime."

# Static config (entrypoints, providers, certificate resolvers).
COPY infra/traefik/traefik.yml /etc/traefik/traefik.yml

# Fallback dynamic config (used only if the Redis KV provider is unreachable;
# the production source of truth is Redis written by the WDK registerRoute
# step).
COPY infra/traefik/dynamic.yml /etc/traefik/dynamic.yml

EXPOSE 80 443 8080

# Traefik image already sets ENTRYPOINT and reads /etc/traefik/traefik.yml.
