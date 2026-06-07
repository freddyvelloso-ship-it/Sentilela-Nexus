# setup_env_local.ps1
# Gera arquivos locais de ambiente para teste Docker Compose.
# Não use estes valores em produção.

$ErrorActionPreference = "Stop"

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    $fullPath = Join-Path (Get-Location) $Path
    $directory = Split-Path $fullPath -Parent

    if (!(Test-Path $directory)) {
        New-Item -ItemType Directory -Force $directory | Out-Null
    }

    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($fullPath, $Content, $utf8NoBom)
}

$PostgresPassword = "sentinela_local_postgres_1234567890"
$SentinelaPostgresPassword = "sentinela_local_db_1234567890"
$RedisPassword = "sentinela_local_redis_1234567890"
$GrafanaPassword = "sentinela_local_grafana_1234567890"
$ApiSecretKey = "sentinela_local_api_secret_key_1234567890_abcdef"
$SecretKey = "sentinela_local_secret_key_1234567890_abcdef"
$ApiIngestToken = "sentinela_local_ingest_token_1234567890_abcdef"
$SupremeSalt = "sentinela_local_salt_1234567890_abcdef"
$SentinelaApiKey = "sentinela_local_shared_sentinela_key_1234567890"
$BootstrapToken = "sentinela_local_bootstrap_token_1234567890"

$RootEnv = @"
# Ambiente local de teste. Não usar em produção.

POSTGRES_PASSWORD=$PostgresPassword
SENTINELA_POSTGRES_PASSWORD=$SentinelaPostgresPassword
REDIS_PASSWORD=$RedisPassword

GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$GrafanaPassword

SUPREME_API_WORKERS=2
SUPREME_WORKER_REPLICAS=2

BACKUP_PASSPHRASE=sentinela_local_backup_1234567890

API_SECRET_KEY=$ApiSecretKey
SECRET_KEY=$SecretKey
API_INGEST_TOKEN=$ApiIngestToken
SUPREME_SALT=$SupremeSalt

IPED_AUDIT_DIR=C:/Users/nunas
"@

$SupremeEnv = @"
# SUPREME Backend - ambiente local de teste. Não usar em produção.

ENVIRONMENT=production
ENABLE_DOCS=false
ENABLE_METRICS=true
LOG_LEVEL=INFO
API_DEBUG=false

POSTGRES_PASSWORD=$PostgresPassword
REDIS_PASSWORD=$RedisPassword

DATABASE_URL=postgresql+asyncpg://supreme:$PostgresPassword@supreme-db:5432/supreme
REDIS_URL=redis://:$RedisPassword@supreme-redis:6379/0

API_SECRET_KEY=$ApiSecretKey
API_INGEST_TOKEN=$ApiIngestToken
SUPREME_SALT=$SupremeSalt

ALLOWED_ORIGINS=https://localhost,http://localhost
SENTINELA_URL=http://sentinela:8001
SENTINELA_API_KEY=$SentinelaApiKey
"@

$SentinelaEnv = @"
# SENTINELA - ambiente local de teste. Não usar em produção.

AUTO_INIT_DB=false
ACCESS_TOKEN_EXPIRE_MINUTES=480

POSTGRES_PASSWORD=$SentinelaPostgresPassword
DATABASE_URL=postgresql+asyncpg://sentinela:$SentinelaPostgresPassword@sentinela-db:5432/sentinela

SECRET_KEY=$SecretKey
SUPREME_API_KEY=$SentinelaApiKey
BOOTSTRAP_TOKEN=$BootstrapToken

ALLOWED_ORIGINS=https://localhost,http://localhost
"@

Write-Utf8NoBom ".env" $RootEnv
Write-Utf8NoBom "supreme-backend\.env.production" $SupremeEnv
Write-Utf8NoBom "sentinela\.env.production" $SentinelaEnv

Write-Host "Arquivos locais gerados:"
Write-Host " - .env"
Write-Host " - supreme-backend\.env.production"
Write-Host " - sentinela\.env.production"
Write-Host ""
Write-Host "Atenção: estes arquivos não devem ser commitados."