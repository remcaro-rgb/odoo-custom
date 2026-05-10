#!/bin/bash
# zfs-init.sh — STUB. ZFS subvolume bootstrap for atomic pgdata + filestore.
#
# Status: not used on Railway/Fly cloud Volumes (their block devices don't
# expose ZFS kernel modules from inside an unprivileged container). pgBackRest
# achieves backup atomicity at the protocol level via
# pg_start_backup() → ship → pg_stop_backup(), which is what the WDK
# tenantBackupDaily workflow relies on.
#
# This script becomes load-bearing for bare-metal exclusive-tier deployments
# (Phase 3+) where we control the host kernel and want filesystem-level
# atomicity between Postgres pgdata and the Odoo filestore. On those hosts
# the intended layout is:
#
#   zpool: tank
#     ├── tank/pgdata     mount → /var/lib/postgresql/data
#     └── tank/filestore  mount → /var/lib/odoo/filestore
#
# Snapshot sequence:
#   1. SELECT pg_start_backup('atomic-snap', true, false);
#   2. zfs snapshot tank/pgdata@<ts>
#      zfs snapshot tank/filestore@<ts>
#   3. SELECT pg_stop_backup(false, true);
#   4. Send/upload both snapshot streams.
#
# Implementation deferred until Phase 3 hardware is selected. Until then,
# pgBackRest's protocol-level atomicity is the source of truth for the
# WARM dumps tier.

set -euo pipefail
echo "zfs-init: stub — see comments. No-op for cloud Volume deployments."
exit 0
