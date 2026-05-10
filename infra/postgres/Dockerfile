FROM postgres:16-alpine

LABEL org.opencontainers.image.title="odoo-saas-postgres"
LABEL org.opencontainers.image.description="Postgres 16 + pgBackRest, self-managed for the Odoo SaaS data plane. Same image deploys to Railway, Fly, or local Docker."

# pgBackRest for continuous WAL archiving + base backups.
# Alpine package tracks upstream Postgres minor releases reasonably well.
RUN apk add --no-cache \
        pgbackrest \
        bash \
        ca-certificates \
        tzdata \
    && mkdir -p \
        /etc/pgbackrest \
        /var/log/pgbackrest \
        /var/lib/pgbackrest \
        /var/spool/pgbackrest \
    && chown -R postgres:postgres \
        /etc/pgbackrest \
        /var/log/pgbackrest \
        /var/lib/pgbackrest \
        /var/spool/pgbackrest

# Tuned Postgres config. The official postgres:16 image runs initdb on an empty
# PGDATA, then loads /etc/postgresql/postgresql.conf if you point at it via the
# postgres CLI flag. We override via the entrypoint additions below.
COPY infra/postgres/postgresql.conf /etc/postgresql/postgresql.conf

# pgBackRest stanza config. Secrets (S3 keys, KMS key id) come from env at
# runtime; see entrypoint for the PGBACKREST_* env mapping.
COPY infra/postgres/pgbackrest.conf /etc/pgbackrest/pgbackrest.conf

# Init-time hook: creates the pgBackRest stanza on first boot, after Postgres
# has initialized PGDATA. Scripts in /docker-entrypoint-initdb.d/ run once
# under the official postgres image's entrypoint, against a freshly-initdb'd
# cluster. After this, archive_command in postgresql.conf takes over.
COPY infra/postgres/init-pgbackrest.sh /docker-entrypoint-initdb.d/10-pgbackrest.sh
RUN chmod +x /docker-entrypoint-initdb.d/10-pgbackrest.sh

EXPOSE 5432

# Use the official postgres image's entrypoint but tell it to load our tuned
# postgresql.conf instead of the initdb default.
CMD ["postgres", "-c", "config_file=/etc/postgresql/postgresql.conf"]
