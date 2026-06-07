#!/usr/bin/env bash
set -euo pipefail
docker compose -f docker-compose.production.yml exec -T supreme-db psql -U supreme -d supreme <<'SQL'
DELETE FROM events_raw WHERE timestamp < NOW() - INTERVAL '18 months';
DELETE FROM system_health_logs WHERE timestamp < NOW() - INTERVAL '90 days';
SQL
