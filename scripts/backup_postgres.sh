#!/usr/bin/env bash
set -euo pipefail
mkdir -p backups/postgres
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
SUPREME_OUT="backups/postgres/supreme_${STAMP}.dump"
SENTINELA_OUT="backups/postgres/sentinela_${STAMP}.dump"

docker compose -f docker-compose.production.yml exec -T supreme-db pg_dump -U supreme -d supreme -Fc > "$SUPREME_OUT"
docker compose -f docker-compose.production.yml exec -T sentinela-db pg_dump -U sentinela -d sentinela -Fc > "$SENTINELA_OUT"

if [[ -n "${BACKUP_PASSPHRASE:-}" ]]; then
  gpg --batch --yes --symmetric --cipher-algo AES256 --passphrase "$BACKUP_PASSPHRASE" "$SUPREME_OUT"
  gpg --batch --yes --symmetric --cipher-algo AES256 --passphrase "$BACKUP_PASSPHRASE" "$SENTINELA_OUT"
  shred -u "$SUPREME_OUT" "$SENTINELA_OUT"
fi

find backups/postgres -type f -mtime +30 -delete
