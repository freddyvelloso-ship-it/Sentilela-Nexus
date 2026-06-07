#!/usr/bin/env bash
set -euo pipefail
BASE=${BASE_URL:-http://localhost}
TOKEN=${API_SECRET_KEY:?defina API_SECRET_KEY}
curl -fsS "$BASE/" >/dev/null
curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/v1/health" >/dev/null
curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/metrics" >/dev/null
