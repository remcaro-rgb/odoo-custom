FROM alpine:3.20

LABEL org.opencontainers.image.title="odoo-saas-pgbouncer"
LABEL org.opencontainers.image.description="PgBouncer transaction-pooling front for the self-managed Postgres on the SaaS data plane. Same image on Railway + Fly; per-platform manifests differ only in the env wiring."

# pgbouncer + bash for the entrypoint, ca-certificates for upstream TLS,
# postgresql16-client (psql) for the readiness probe.
RUN apk add --no-cache pgbouncer bash ca-certificates postgresql16-client \
    && mkdir -p /etc/pgbouncer /var/log/pgbouncer /var/run/pgbouncer \
    && chown -R pgbouncer:pgbouncer /etc/pgbouncer /var/log/pgbouncer /var/run/pgbouncer

COPY infra/postgres/pgbouncer/pgbouncer.ini /etc/pgbouncer/pgbouncer.ini
COPY infra/postgres/pgbouncer/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 6432

# Run as the pgbouncer user (uid 70 in alpine); the entrypoint chowns
# /etc/pgbouncer before dropping into pgbouncer itself.
ENTRYPOINT ["/entrypoint.sh"]
