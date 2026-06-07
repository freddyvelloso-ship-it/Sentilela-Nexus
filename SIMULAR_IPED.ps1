# Simulador de eventos IPED para testar o pipeline SUPREME
# Gera supreme_audit.ndjson com eventos reais-like e os envia direto ao SUPREME
# Execute: .\SIMULAR_IPED.ps1

$envFile = ".\supreme-backend\.env.production"
if (-not (Test-Path $envFile)) {
    Write-Host "ERRO: rode SUBIR_LOCAL.ps1 primeiro." -ForegroundColor Red
    exit 1
}

$API_INGEST_TOKEN = (Get-Content $envFile | Where-Object { $_ -match "^API_INGEST_TOKEN=" }) -replace "^API_INGEST_TOKEN=", ""
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

# Enviar eventos diretamente ao SUPREME via /v1/events/ingest
Write-Host "Enviando eventos ao SUPREME..." -ForegroundColor Yellow
Write-Host ""

$timestamp = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")

$supremeEvents = @(
    @{ id_hash=$idHash; timestamp=$timestamp;                  event_type="image_view";          artifact_id="item_1001"; severity=1; duration_seconds=12;  source="iped_sim" }
    @{ id_hash=$idHash; timestamp=$timestamp;                  event_type="video_play";           artifact_id="item_1002"; severity=3; duration_seconds=72;  source="iped_sim" }
    @{ id_hash=$idHash; timestamp=$timestamp;                  event_type="image_view";          artifact_id="item_1003"; severity=5; duration_seconds=40;  source="iped_sim" }
    @{ id_hash=$idHash; timestamp=$timestamp;                  event_type="file_open";           artifact_id="item_1004"; severity=1; duration_seconds=13;  source="iped_sim" }
    @{ id_hash=$idHash; timestamp=$timestamp;                  event_type="classification_event"; artifact_id="item_1005"; severity=4; duration_seconds=5;   source="iped_sim" }
)

$payload = @{ events = $supremeEvents } | ConvertTo-Json -Depth 5
$payload | Set-Content -Encoding UTF8 _sim_payload.json

$resp = curl.exe -sk -X POST https://localhost/v1/events/ingest `
    -H "Content-Type: application/json" `
    -H "Authorization: Bearer $API_INGEST_TOKEN" `
    --data-binary "@_sim_payload.json" 2>&1
Remove-Item _sim_payload.json -ErrorAction SilentlyContinue

if ($resp -match "events_stored") {
    Write-Host "Ingestao OK: $resp" -ForegroundColor Green
} else {
    Write-Host "Resposta: $resp" -ForegroundColor Yellow
}

Write-Host ""

# Verificar no banco
Write-Host "Verificando no banco..." -ForegroundColor Yellow
$sql = "SELECT id_hash, event_type, severity, duration_seconds, source FROM events_raw ORDER BY timestamp DESC LIMIT 10;"
docker exec supreme_final-supreme-db-1 psql -U supreme -d supreme -c $sql 2>&1

Write-Host ""
Write-Host "Pipeline testado. Verifique o dashboard em: https://localhost/sentinela/" -ForegroundColor Cyan
Write-Host ""
Write-Host "O watcher Docker le $auditPath a cada 15s." -ForegroundColor DarkGray
Write-Host "Para ver o watcher processando: docker logs -f supreme_final-supreme-iped-watcher-1" -ForegroundColor DarkGray
Write-Host ""
