# Simulador de eventos IPED para testar o pipeline SUPREME
# Gera supreme_audit.ndjson com eventos reais-like e os envia direto ao SUPREME
# Execute: .\SIMULAR_IPED.ps1

$envFile = ".\supreme-backend\.env.production"
if (-not (Test-Path $envFile)) {
    Write-Host "ERRO: rode SUBIR_LOCAL.ps1 primeiro." -ForegroundColor Red
    exit 1
}

$API_INGEST_TOKEN = (Get-Content $envFile | Where-Object { $_ -match "^API_INGEST_TOKEN=" }) -replace "^API_INGEST_TOKEN=", ""
$API_SECRET_KEY   = (Get-Content $envFile | Where-Object { $_ -match "^API_SECRET_KEY=" })   -replace "^API_SECRET_KEY=", ""
$SUPREME_SALT     = (Get-Content $envFile | Where-Object { $_ -match "^SUPREME_SALT=" })     -replace "^SUPREME_SALT=", ""

if (-not $API_INGEST_TOKEN -or -not $SUPREME_SALT) {
    Write-Host "ERRO: API_INGEST_TOKEN ou SUPREME_SALT nao encontrados em $envFile" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SIMULADOR DE EVENTOS IPED" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Pseudonimizar usuario de teste
$userId   = "perito_simulado_001"
$salted   = $userId + $SUPREME_SALT
$sha256   = [System.Security.Cryptography.SHA256]::Create()
$bytes    = [System.Text.Encoding]::UTF8.GetBytes($salted)
$hash     = $sha256.ComputeHash($bytes)
$idHash   = ($hash | ForEach-Object { $_.ToString("x2") }) -join ""
$sha256.Dispose()

Write-Host "Usuario simulado : $userId" -ForegroundColor DarkGray
Write-Host "ID hash          : $idHash" -ForegroundColor DarkGray
Write-Host ""

# Gerar arquivo supreme_audit.ndjson simulado
$auditPath = "$env:USERPROFILE\supreme_audit.ndjson"
$now       = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()

$events = @(
    @{ itemId=1001; userId=$userId; event="open";  mediaType="image/jpeg";   nudityClass=1; openTs=$now;              closeTs=0;                aiCsam=0; aiPorn=0  }
    @{ itemId=1001; userId=$userId; event="close"; mediaType="image/jpeg";   nudityClass=1; openTs=$now;              closeTs=$now+12000;        aiCsam=0; aiPorn=0  }
    @{ itemId=1002; userId=$userId; event="open";  mediaType="video/mp4";    nudityClass=3; openTs=$now+15000;        closeTs=0;                aiCsam=0; aiPorn=72 }
    @{ itemId=1002; userId=$userId; event="close"; mediaType="video/mp4";    nudityClass=3; openTs=$now+15000;        closeTs=$now+87000;        aiCsam=0; aiPorn=72 }
    @{ itemId=1003; userId=$userId; event="open";  mediaType="image/png";    nudityClass=5; openTs=$now+90000;        closeTs=0;                aiCsam=81; aiPorn=0 }
    @{ itemId=1003; userId=$userId; event="close"; mediaType="image/png";    nudityClass=5; openTs=$now+90000;        closeTs=$now+130000;       aiCsam=81; aiPorn=0 }
    @{ itemId=1004; userId=$userId; event="open";  mediaType="text/plain";   nudityClass=1; openTs=$now+135000;       closeTs=0;                aiCsam=0; aiPorn=0  }
    @{ itemId=1004; userId=$userId; event="close"; mediaType="text/plain";   nudityClass=1; openTs=$now+135000;       closeTs=$now+148000;       aiCsam=0; aiPorn=0  }
    @{ itemId=1005; userId=$userId; event="classification_event"; mediaType="image/jpeg"; nudityClass=4; openTs=$now+150000; closeTs=$now+155000; aiCsam=0; aiPorn=65 }
)

"" | Set-Content -Encoding UTF8 $auditPath
foreach ($ev in $events) {
    ($ev | ConvertTo-Json -Compress) | Add-Content -Encoding UTF8 $auditPath
}

Write-Host "Arquivo de auditoria gerado: $auditPath" -ForegroundColor Green
Write-Host "Eventos escritos: $($events.Count)" -ForegroundColor Green
Write-Host ""

# Registrar consent do participante simulado
Write-Host "Registrando consent..." -ForegroundColor Yellow
$consentBody = '{"status":"granted"}'
$consentBody | Set-Content -Encoding UTF8 _consent.json
$cResp = curl.exe -sk -X POST "https://localhost/v1/governance/consent/$idHash" `
    -H "Content-Type: application/json" `
    -H "Authorization: Bearer $API_SECRET_KEY" `
    --data-binary "@_consent.json" 2>&1
Remove-Item _consent.json -ErrorAction SilentlyContinue
if ($cResp -match "granted") {
    Write-Host "  Consent OK" -ForegroundColor Green
} else {
    Write-Host "  Consent resp: $cResp" -ForegroundColor Yellow
}
Write-Host ""

# Enviar eventos diretamente ao SUPREME via /v1/events/ingest
# Envia 5 janelas passadas completas (study_start=2026-01-01, window=14d)
# para garantir baseline (>= 4 janelas) e IEO calculado.
Write-Host "Enviando eventos ao SUPREME (5 janelas historicas)..." -ForegroundColor Yellow
Write-Host ""

# Timestamps no meio de cada janela fechada:
# W1: 2026-01-01->15  W2: 2026-01-15->29  W3: 2026-01-29->02-12
# W4: 2026-02-12->26  W5: 2026-02-26->03-12
# Timestamps com segundos aleatórios para evitar colisão de event_hash em reexecuções
$rnd = Get-Random -Minimum 10 -Maximum 59
$windowTimestamps = @(
    "2026-01-08T10:00:${rnd}Z"
    "2026-01-22T10:00:${rnd}Z"
    "2026-02-05T10:00:${rnd}Z"
    "2026-02-19T10:00:${rnd}Z"
    "2026-03-05T10:00:${rnd}Z"
)

$totalStored = 0
foreach ($ts in $windowTimestamps) {
    $windowEvents = @(
        @{ user_identifier=$idHash; timestamp=$ts; event_type="image_view";           media_type="image";   severity=2; duration_seconds=20;  source_tool="iped" }
        @{ user_identifier=$idHash; timestamp=$ts; event_type="video_play";           media_type="video";   severity=3; duration_seconds=90;  source_tool="iped" }
        @{ user_identifier=$idHash; timestamp=$ts; event_type="image_view";           media_type="image";   severity=4; duration_seconds=35;  source_tool="iped" }
        @{ user_identifier=$idHash; timestamp=$ts; event_type="file_open";            media_type="preview"; severity=1; duration_seconds=10;  source_tool="iped" }
        @{ user_identifier=$idHash; timestamp=$ts; event_type="cla