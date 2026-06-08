param(
  [switch]$TemplateMode,
  [switch]$SkipDockerCompose,
  [switch]$AllowBootstrapToken
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
  $PSNativeCommandUseErrorActionPreference = $false
}

$Failures = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]

function Add-Failure {
  param([string]$Message)
  $Failures.Add($Message) | Out-Null
  Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Add-WarningMessage {
  param([string]$Message)
  $Warnings.Add($Message) | Out-Null
  Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Add-Pass {
  param([string]$Message)
  Write-Host "[ OK ] $Message" -ForegroundColor Green
}

function Read-DotEnv {
  param([string]$Path)
  $values = @{}
  if (-not (Test-Path -LiteralPath $Path)) {
    Add-Failure "Arquivo obrigatorio ausente: $Path"
    return $values
  }
  foreach ($line in Get-Content -LiteralPath $Path) {
    $trimmed = $line.Trim()
    if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) {
      continue
    }
    $parts = $trimmed -split "=", 2
    if ($parts.Count -ne 2) {
      Add-Failure "Linha invalida em ${Path}: $line"
      continue
    }
    $values[$parts[0].Trim()] = $parts[1].Trim().Trim('"').Trim("'")
  }
  return $values
}

function Test-RequiredKey {
  param([hashtable]$Values, [string]$Key, [string]$Path)
  if (-not $Values.ContainsKey($Key) -or [string]::IsNullOrWhiteSpace($Values[$Key])) {
    Add-Failure "${Path} deve definir $Key"
  }
}

function Test-SecretValue {
  param([hashtable]$Values, [string]$Key, [string]$Path, [int]$MinLength = 32)
  Test-RequiredKey -Values $Values -Key $Key -Path $Path
  if (-not $Values.ContainsKey($Key)) {
    return
  }
  $value = $Values[$Key]
  $lower = $value.ToLowerInvariant()
  $isPlaceholder = (
    $value -like "CHANGE_ME*" -or
    $value -like "GERE_*" -or
    $lower -like "dev_*" -or
    $lower -like "*troque*" -or
    $lower -like "*placeholder*" -or
    $lower -eq "change-me"
  )
  if (-not $TemplateMode -and $isPlaceholder) {
    Add-Failure "${Path} contem placeholder em $Key"
  }
  if (-not $TemplateMode -and $value.Length -lt $MinLength) {
    Add-Failure "${Path} define $Key com menos de $MinLength caracteres"
  }
}

function Test-ExpectedValue {
  param([hashtable]$Values, [string]$Key, [string]$Expected, [string]$Path)
  Test-RequiredKey -Values $Values -Key $Key -Path $Path
  if ($Values.ContainsKey($Key) -and $Values[$Key].ToLowerInvariant() -ne $Expected.ToLowerInvariant()) {
    Add-Failure "${Path} deve definir $Key=$Expected"
  }
}

function Test-ClosedOrigins {
  param([hashtable]$Values, [string]$Path)
  Test-RequiredKey -Values $Values -Key "ALLOWED_ORIGINS" -Path $Path
  if (-not $Values.ContainsKey("ALLOWED_ORIGINS")) {
    return
  }
  $origins = $Values["ALLOWED_ORIGINS"]
  if ($origins -match "(^|,)\s*\*\s*(,|$)") {
    Add-Failure "${Path} nao pode usar ALLOWED_ORIGINS=* em producao"
  }
  if (-not $TemplateMode -and $origins -match "localhost|127\.0\.0\.1|example\.org|seu-dominio") {
    Add-Failure "${Path} deve usar dominio/IP real em ALLOWED_ORIGINS"
  }
}

function Test-NotTracked {
  param([string]$Path)
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Add-WarningMessage "git nao encontrado; nao foi possivel validar tracking de $Path"
    return
  }
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & git ls-files --error-unmatch -- $Path 1>$null 2>$null
  $gitExitCode = $LASTEXITCODE
  $ErrorActionPreference = $previousErrorActionPreference

  if ($gitExitCode -eq 0) {
    Add-Failure "Arquivo sensivel versionado no Git: $Path"
  } else {
    Add-Pass "Arquivo sensivel nao versionado: $Path"
  }
}

function Test-FileExists {
  param([string]$Path)
  if (Test-Path -LiteralPath $Path) {
    Add-Pass "Arquivo presente: $Path"
  } else {
    Add-Failure "Arquivo obrigatorio ausente: $Path"
  }
}

$rootEnvPath = if ($TemplateMode) { ".env.production.example" } else { ".env" }
$supremeEnvPath = if ($TemplateMode) { "supreme-backend/.env.production.example" } else { "supreme-backend/.env.production" }
$sentinelaEnvPath = if ($TemplateMode) { "sentinela/.env.production.example" } else { "sentinela/.env.production" }

Write-Host "SUPREME/SENTINELA production readiness check" -ForegroundColor Cyan
if ($TemplateMode) {
  Write-Host "Mode: template validation"
} else {
  Write-Host "Mode: production go/no-go"
}

$rootEnv = Read-DotEnv -Path $rootEnvPath
$supremeEnv = Read-DotEnv -Path $supremeEnvPath
$sentinelaEnv = Read-DotEnv -Path $sentinelaEnvPath

foreach ($key in @("POSTGRES_PASSWORD", "SENTINELA_POSTGRES_PASSWORD", "REDIS_PASSWORD", "GRAFANA_ADMIN_PASSWORD")) {
  Test-SecretValue -Values $rootEnv -Key $key -Path $rootEnvPath
}
foreach ($key in @("SUPREME_API_WORKERS", "SUPREME_WORKER_REPLICAS", "GRAFANA_ROOT_URL")) {
  Test-RequiredKey -Values $rootEnv -Key $key -Path $rootEnvPath
}
if (-not $TemplateMode -and $rootEnv.ContainsKey("GRAFANA_ROOT_URL") -and $rootEnv["GRAFANA_ROOT_URL"] -match "localhost|example\.org|seu-dominio") {
  Add-Failure "$rootEnvPath deve usar URL real em GRAFANA_ROOT_URL"
}

Test-ExpectedValue -Values $supremeEnv -Key "ENVIRONMENT" -Expected "production" -Path $supremeEnvPath
Test-ExpectedValue -Values $supremeEnv -Key "ENABLE_DOCS" -Expected "false" -Path $supremeEnvPath
Test-ExpectedValue -Values $supremeEnv -Key "ENABLE_METRICS" -Expected "true" -Path $supremeEnvPath
Test-ExpectedValue -Values $supremeEnv -Key "API_DEBUG" -Expected "false" -Path $supremeEnvPath
foreach ($key in @("POSTGRES_PASSWORD", "REDIS_PASSWORD", "API_SECRET_KEY", "API_INGEST_TOKEN", "SUPREME_SALT", "SENTINELA_API_KEY")) {
  Test-SecretValue -Values $supremeEnv -Key $key -Path $supremeEnvPath
}
foreach ($key in @("DATABASE_URL", "REDIS_URL", "DATABASE_POOL_SIZE", "DATABASE_MAX_OVERFLOW", "RQ_QUEUE_ANALYTICS", "RQ_QUEUE_EVENTS", "RQ_QUEUE_DEAD_LETTER", "RQ_MAX_RETRIES", "RQ_RETRY_DELAY_S", "API_HOST", "API_PORT", "LOG_LEVEL", "STUDY_START_DATE", "WINDOW_DAYS", "MIN_BASELINE_WINDOWS", "MAX_BASELINE_WINDOWS", "DQ_MIN_THRESHOLD", "ALGORITHM_VERSION", "SENTINELA_URL")) {
  Test-RequiredKey -Values $supremeEnv -Key $key -Path $supremeEnvPath
}
Test-ClosedOrigins -Values $supremeEnv -Path $supremeEnvPath
if (-not $TemplateMode -and $supremeEnv.ContainsKey("SENTINELA_URL") -and $supremeEnv["SENTINELA_URL"] -match "localhost|127\.0\.0\.1|example\.org|seu-dominio") {
  Add-Failure "$supremeEnvPath deve usar URL real em SENTINELA_URL"
}

Test-ExpectedValue -Values $sentinelaEnv -Key "ENVIRONMENT" -Expected "production" -Path $sentinelaEnvPath
Test-ExpectedValue -Values $sentinelaEnv -Key "ENABLE_DOCS" -Expected "false" -Path $sentinelaEnvPath
Test-ExpectedValue -Values $sentinelaEnv -Key "AUTO_INIT_DB" -Expected "false" -Path $sentinelaEnvPath
Test-ExpectedValue -Values $sentinelaEnv -Key "ALGORITHM" -Expected "HS256" -Path $sentinelaEnvPath
foreach ($key in @("POSTGRES_PASSWORD", "SECRET_KEY", "SUPREME_API_KEY")) {
  Test-SecretValue -Values $sentinelaEnv -Key $key -Path $sentinelaEnvPath
}
foreach ($key in @("DATABASE_URL", "ACCESS_TOKEN_EXPIRE_MINUTES")) {
  Test-RequiredKey -Values $sentinelaEnv -Key $key -Path $sentinelaEnvPath
}
Test-ClosedOrigins -Values $sentinelaEnv -Path $sentinelaEnvPath
if (-not $TemplateMode -and $sentinelaEnv.ContainsKey("BOOTSTRAP_TOKEN") -and -not [string]::IsNullOrWhiteSpace($sentinelaEnv["BOOTSTRAP_TOKEN"]) -and -not $AllowBootstrapToken) {
  Add-Failure "$sentinelaEnvPath deve remover ou esvaziar BOOTSTRAP_TOKEN apos criar o usuario master. Use -AllowBootstrapToken somente antes do bootstrap inicial."
}

if ($supremeEnv.ContainsKey("SENTINELA_API_KEY") -and $sentinelaEnv.ContainsKey("SUPREME_API_KEY")) {
  if (-not $TemplateMode -and $supremeEnv["SENTINELA_API_KEY"] -ne $sentinelaEnv["SUPREME_API_KEY"]) {
    Add-Failure "SENTINELA_API_KEY deve ser igual a sentinela SUPREME_API_KEY"
  } else {
    Add-Pass "Chave compartilhada SUPREME/SENTINELA validada"
  }
}

if (-not $TemplateMode -and $supremeEnv.ContainsKey("API_SECRET_KEY") -and $supremeEnv.ContainsKey("API_INGEST_TOKEN") -and $supremeEnv["API_SECRET_KEY"] -eq $supremeEnv["API_INGEST_TOKEN"]) {
  Add-Failure "API_SECRET_KEY e API_INGEST_TOKEN devem ser diferentes"
}
if (-not $TemplateMode -and $supremeEnv.ContainsKey("API_SECRET_KEY") -and $supremeEnv.ContainsKey("SUPREME_SALT") -and $supremeEnv["API_SECRET_KEY"] -eq $supremeEnv["SUPREME_SALT"]) {
  Add-Failure "API_SECRET_KEY e SUPREME_SALT devem ser diferentes"
}

foreach ($path in @(".env", "supreme-backend/.env.production", "sentinela/.env.production", "certs/fullchain.pem", "certs/privkey.pem", "infra/prometheus/supreme-api-token.local")) {
  Test-NotTracked -Path $path
}

if (-not $TemplateMode) {
  Test-FileExists -Path "certs/fullchain.pem"
  Test-FileExists -Path "certs/privkey.pem"
  Test-FileExists -Path "infra/prometheus/supreme-api-token.local"

  if ((Test-Path -LiteralPath "infra/prometheus/supreme-api-token.local") -and $supremeEnv.ContainsKey("API_SECRET_KEY")) {
    $promToken = (Get-Content -LiteralPath "infra/prometheus/supreme-api-token.local" -Raw).Trim()
    if ($promToken -ne $supremeEnv["API_SECRET_KEY"]) {
      Add-Failure "infra/prometheus/supreme-api-token.local deve ser igual a API_SECRET_KEY"
    } else {
      Add-Pass "Token local do Prometheus confere com API_SECRET_KEY"
    }
  }
}

if (-not $SkipDockerCompose -and -not $TemplateMode) {
  if (Get-Command docker -ErrorAction SilentlyContinue) {
    & docker compose -f docker-compose.production.yml config --quiet
    if ($LASTEXITCODE -eq 0) {
      Add-Pass "docker compose production config valido"
    } else {
      Add-Failure "docker compose production config falhou"
    }
  } else {
    Add-WarningMessage "docker nao encontrado; compose config nao executado"
  }
}

Write-Host ""
Write-Host "Resumo: $($Failures.Count) falha(s), $($Warnings.Count) aviso(s)."
if ($Failures.Count -gt 0) {
  exit 1
}
exit 0
