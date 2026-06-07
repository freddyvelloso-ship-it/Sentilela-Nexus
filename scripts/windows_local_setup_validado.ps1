# SUPREME V5 - setup local validado no Windows/PowerShell
# Execute a partir da pasta supreme_final

function New-Secret {
  $bytes = New-Object byte[] 32
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $rng.GetBytes($bytes)
  return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
}

$POSTGRES_PASSWORD = New-Secret
$REDIS_PASSWORD = New-Secret
$SENTINELA_POSTGRES_PASSWORD = New-Secret
$GRAFANA_ADMIN_PASSWORD = New-Secret
$API_SECRET_KEY = New-Secret
$API_INGEST_TOKEN = New-Secret
$SUPREME_SALT = New-Secret
$SENTINELA_SHARED_KEY = New-Secret
$SENTINELA_SECRET_KEY = New-Secret
$BOOTSTRAP_TOKEN = New-Secret

mkdir certs -Force | Out-Null
docker run --rm -v "${PWD}\certs:/certs" alpine/openssl req -x509 -nodes -newkey rsa:2048 -days 365 `
  -keyout /certs/privkey.pem `
  -out /certs/fullchain.pem `
  -subj "/CN=localhost"

@"
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
REDIS_PASSWORD=$REDIS_PASSWORD
SENTINELA_POSTGRES_PASSWORD=$SENTINELA_POSTGRES_PASSWORD
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$GRAFANA_ADMIN_PASSWORD
SUPREME_API_WORKERS=1
SUPREME_WORKER_REPLICAS=1
"@ | Set-Content -Encoding ASCII .env

@"
ENVIRONMENT=production
ENABLE_DOCS=false
ENABLE_METRICS=true
API_SECRET_KEY=$API_SECRET_KEY
API_INGEST_TOKEN=$API_INGEST_TOKEN
SUPREME_SALT=$SUPREME_SALT
ALLOWED_ORIGINS=https://localhost
LOG_LEVEL=INFO
API_DEBUG=false
SENTINELA_URL=http://sentinela:8001
SENTINELA_API_KEY=$SENTINELA_SHARED_KEY
ALGORITHM_VERSION=IEO-1.0.0
"@ | Set-Content -Encoding ASCII .\supreme-backend\.env.production

@"
ENVIRONMENT=production
SECRET_KEY=$SENTINELA_SECRET_KEY
SUPREME_API_KEY=$SENTINELA_SHARED_KEY
BOOTSTRAP_TOKEN=$BOOTSTRAP_TOKEN
ALLOWED_ORIGINS=https://localhost
AUTO_INIT_DB=false
ACCESS_TOKEN_EXPIRE_MINUTES=480
"@ | Set-Content -Encoding ASCII .\sentinela\.env.production

@"
services:
  nginx:
    networks:
      - backend

  supreme-redis:
    environment:
      REDIS_PASSWORD: `${REDIS_PASSWORD}

  grafana:
    environment:
      GF_SERVER_ROOT_URL: https://localhost/grafana/
      GF_SERVER_SERVE_FROM_SUB_PATH: "true"

  prometheus:
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.retention.time=30d

  loki:
    user: "0:0"

networks:
  backend:
    driver: bridge
"@ | Set-Content -Encoding ASCII .\docker-compose.local.yml

Write-Host "API_SECRET_KEY=$API_SECRET_KEY"
Write-Host "API_INGEST_TOKEN=$API_INGEST_TOKEN"
Write-Host "BOOTSTRAP_TOKEN=$BOOTSTRAP_TOKEN"
Write-Host "GRAFANA_ADMIN_PASSWORD=$GRAFANA_ADMIN_PASSWORD"
Write-Host "SENTINELA_LOGIN=admin@local.test"
Write-Host "SENTINELA_PASSWORD=SenhaForte123!"
Write-Host "Agora rode: docker compose -f docker-compose.production.yml -f docker-compose.local.yml up -d --build"
