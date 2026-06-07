#!/usr/bin/env bash
set -euo pipefail
DUMP=${1:?uso: scripts/restore_postgres.sh backups/postgres/supreme_YYYY.dump}
docker compose -f docker-compose.production.yml exec -T supreme-db pg_restore -U supreme -d supreme --clean --if-exists < "$DUMP"
