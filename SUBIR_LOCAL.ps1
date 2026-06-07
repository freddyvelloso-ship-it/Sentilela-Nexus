# SUPREME V5 - Setup local para Windows + Docker Desktop
# Execute: cd supreme_final; .\SUBIR_LOCAL.ps1
# Requer: Docker Desktop rodando

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SUPREME V5 - Setup Local" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verificar Docker
Write-Host "[1/6] Verificando Docker..." -ForegroundColor Yellow
$dockerOk = $false
$null = docker info 2>&1
if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
if (-not $dockerOk) {
    Write-Host "ERRO: Docker Desktop nao esta rodando." -ForegroundColor Red
    exit 1
}
Write-Host "      Docker OK" -ForegroundColor Green

# 2. Segredos
Write-Host "[2/6] Verificando segredos..." -ForegroundColor Yellow

function New-Secret {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
}

function Get-EnvVal($file, $key) {
    if (-not (Test-Path $file)) { return $null }
    $line = Get-Content $file | Where-Object { $_ -match "^${key}=" } | Select-Object -First 1
    if ($line) { return ($line -split "=", 2)[1] }
    return $null
}

$envFile      = ".env"
$supremeEnv   = ".\supreme-backend\.env.production"
$sentinelaEnv = ".\sentinela\.env.production"

$volList      = docker volume ls --format "{{.Name}}" 2>&1
$hasVolumes   = ($volList -join "") -match "supreme_final_sentinela_pgdata"
$hasEnvFiles  = (Test-Path $envFile) -and (Test-Path $supremeEnv) -and (Test-Path $sentinelaEnv)

if ($hasEnvFiles -and $hasVolumes) {
    Write-Host "      Reutilizando segredos existentes (volumes ativos)." -ForegroundColor Green
    $POSTGRES_PASSWORD           = Get-EnvVal $envFile      "POSTGRES_PASSWORD"
    $REDIS_PASSWORD              = Get-EnvVal $envFile      "REDIS_PASSWORD"
    $SENTINELA_POSTGRES_PASSWORD = Get-EnvVal $envFile      "SENTINELA_POSTGRES_PASSWORD"
    $GRAFANA_ADMIN_PASSWORD      = Get-EnvVal $envFile      "GRAFANA_ADMIN_PASSWORD"
    $API_SECRET_KEY              = Get-EnvVal $supremeEnv   "API_SECRET_KEY"
    $API_INGEST_TOKEN            = Get-EnvVal $supremeEnv   "API_INGEST_TOKEN"
    $SUPREME_SALT                = Get-EnvVal $supremeEnv   "SUPREME_SALT"
    $SENTINELA_SHARED_KEY        = Get-EnvVal $supremeEnv   "SENTINELA_API_KEY"
    $SENTINELA_SECRET_KEY        = Get-EnvVal $sentinelaEnv "SECRET_KEY"
    $BOOTSTRAP_TOKEN             = Get-EnvVal $sentinelaEnv "BOOTSTRAP_TOKEN"
} else {
    Write-Host "      Gerando novos segredos..." -ForegroundColor Yellow
    $POSTGRES_PASSWORD           = New-Secret
    $REDIS_PASSWORD              = New-Secret
    $SENTINELA_POSTGRES_PASSWORD = New-Secret
    $GRAFANA_ADMIN_PASSWORD      = New-Secret
    $API_SECRET_KEY              = New-Secret
    $API_INGEST_TOKEN            = New-Secret
    $SUPREME_SALT                = New-Secret
    $SENTINELA_SHARED_KEY        = New-Secret
    $SENTINELA_SECRET_KEY        = New-Secret
    $BOOTSTRAP_TOKEN             = New-Secret
    Write-Host "      Segredos gerados." -ForegroundColor Green
}

# 3. Certificado TLS
Write-Host "[3/6] Gerando certificado TLS..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path certs | Out-Null
if (-not (Test-Path "certs\fullchain.pem")) {
    $ErrorActionPreference = "Continue"
    docker run --rm `
        -v "${PWD}\certs:/certs" `
        alpine/openssl req -x509 -nodes -newkey rsa:2048 -days 365 `
        -keyout /certs/privkey.pem `
        -out /certs/fullchain.pem `
        -subj "/CN=localhost" 2>&1 | Out-Null
    Write-Host "      Certificado criado." -ForegroundColor Green
} else {
    Write-Host "      Certificado ja existe, reutilizando." -ForegroundColor Green
}

# 4. Criar arquivos .env
Write-Host "[4/6] Criando arquivos .env..." -ForegroundColor Yellow

"POSTGRES_PASSWORD=$POSTGRES_PASSWORD
REDIS_PASSWORD=$REDIS_PASSWORD
SENTINELA_POSTGRES_PASSWORD=$SENTINELA_POSTGRES_PASSWORD
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$GRAFANA_ADMIN_PASSWORD
SUPREME_API_WORKERS=1
SUPREME_WORKER_REPLICAS=1
API_INGEST_TOKEN=$API_INGEST_TOKEN
SUPREME_SALT=$SUPREME_SALT
IPED_AUDIT_DIR=C:/Users/$env:USERNAME" | Set-Content -Encoding ASCII $envFile

"ENVIRONMENT=production
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
ALGORITHM_VERSION=IEO-1.0.0" | Set-Content -Encoding ASCII $supremeEnv

"ENVIRONMENT=production
SECRET_KEY=$SENTINELA_SECRET_KEY
SUPREME_API_KEY=$SENTINELA_SHARED_KEY
BOOTSTRAP_TOKEN=$BOOTSTRAP_TOKEN
ALLOWED_ORIGINS=https://localhost
AUTO_INIT_DB=false
ACCESS_TOKEN_EXPIRE_MINUTES=43200" | Set-Content -Encoding ASCII $sentinelaEnv

Write-Host "      Arquivos .env criados." -ForegroundColor Green

# 5. Subir stack
Write-Host "[5/6] Subindo containers..." -ForegroundColor Yellow
Write-Host ""
docker compose -f docker-compose.production.yml -f docker-compose.local.yml up -d --build
$buildExit = $LASTEXITCODE
if ($buildExit -ne 0) {
    Write-Host "ERRO: docker compose falhou." -ForegroundColor Red
    exit 1
}

# 6. Aguardar
Write-Host ""
Write-Host "[6/6] Aguardando servicos..." -ForegroundColor Yellow
$waited = 0
while ($waited -lt 90) {
    Start-Sleep -Seconds 10
    $waited += 10
    $ps = docker compose -f docker-compose.production.yml -f docker-compose.local.yml ps 2>&1
    $still = ($ps | Select-String "starting|unhealthy").Count
    if ($still -eq 0) { break }
    Write-Host "      Aguardando... ($waited s)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  STATUS DOS CONTAINERS" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
docker compose -f docker-compose.production.yml -f docker-compose.local.yml ps

# Smoke tests
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SMOKE TESTS" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Start-Sleep -Seconds 5

function Test-Url($Label, $Url, $Pattern) {
    $resp = curl.exe -sk --max-time 8 $Url 2>&1
    if ($resp -match $Pattern) {
        Write-Host "  OK   $Label" -ForegroundColor Green
    } else {
        Write-Host "  FAIL $Label => $resp" -ForegroundColor Red
    }
}

Test-Url "SUPREME  /health"            "https://localhost/health"           "status.*ok"
Test-Url "SENTINELA /sentinela/health" "https://localhost/sentinela/health" "status.*ok"
Test-Url "SENTINELA front API base"    "https://localhost/sentinela/"       "const API = '/sentinela'"

# Bootstrap SENTINELA
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  BOOTSTRAP SENTINELA" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

$EMAIL    = "admin@local.test"
$PASSWORD = "SenhaForte123!"

$bBody = '{"email":"' + $EMAIL + '","password":"' + $PASSWORD + '","role":"master"}'
$bBody | Set-Content -Encoding UTF8 _b.json
$bResp = curl.exe -sk -X POST https://localhost/sentinela/api/auth/bootstrap `
    -H "Content-Type: application/json" `
    -H "X-Bootstrap-Token: $BOOTSTRAP_TOKEN" `
    --data-binary "@_b.json" 2>&1
Remove-Item _b.json -ErrorAction SilentlyContinue
Write-Host "  Bootstrap: $bResp" -ForegroundColor Yellow

$lBody = '{"email":"' + $EMAIL + '","password":"' + $PASSWORD + '"}'
$lBody | Set-Content -Encoding UTF8 _l.json
$lResp = curl.exe -sk -X POST https://localhost/sentinela/api/auth/login `
    -H "Content-Type: application/json" `
    --data-binary "@_l.json" 2>&1
Remove-Item _l.json -ErrorAction SilentlyContinue

if ($lResp -match "access_token") {
    Write-Host "  OK   Login SENTINELA funcionando." -ForegroundColor Green
} else {
    Write-Host "  FAIL Login: $lResp" -ForegroundColor Red
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ACESSO LOCAL" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  SENTINELA : https://localhost/sentinela/" -ForegroundColor White
Write-Host "  Login     : $EMAIL" -ForegroundColor White
Write-Host "  Senha     : $PASSWORD" -ForegroundColor White
Write-Host "  Grafana   : https://localhost/grafana/ (admin / $GRAFANA_ADMIN_PASSWORD)" -ForegroundColor White
Write-Host ""
Write-Host "  API_INGEST_TOKEN : $API_INGEST_TOKEN" -ForegroundColor DarkGray
Write-Host "  API_SECRET_KEY   : $API_SECRET_KEY" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Certificado autoassinado - aceite o aviso no Chrome." -ForegroundColor Yellow
Write-Host "  Logs : docker compose -f docker-compose.production.yml -f docker-compose.local.yml logs -f" -ForegroundColor DarkGray
Write-Host "  Stop : docker compose -f docker-compose.production.yml -f docker-compose.local.yml down" -ForegroundColor DarkGray
Write-Host ""
