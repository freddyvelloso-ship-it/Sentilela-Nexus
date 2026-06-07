# SUPREME V5 - Launcher IPED
# Fluxo: formularios pre-sessao -> IPED abre -> eventos capturados -> SUPREME -> SENTINELA
# Execute a partir de supreme_final\: .\LAUNCHER_IPED.ps1

Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -AssemblyName System.Windows.Forms

$IPED_HOME = $env:IPED_HOME
if (-not $IPED_HOME) {
    $candidates = @(
        "C:\iped-test-case", "C:\iped", "C:\IPED", "C:\iped-4.2", "C:\iped-4.1",
        "$env:ProgramFiles\IPED", "$env:LOCALAPPDATA\IPED"
    )
    foreach ($c in $candidates) {
        $hasExe  = Test-Path "$c\IPED-SearchApp.exe"
        $hasJar  = Test-Path "$c\iped.jar"
        $hasJar2 = Test-Path "$c\iped-searchapp.jar"
        if ($hasExe -or $hasJar -or $hasJar2) { $IPED_HOME = $c; break }
    }
}

if (-not $IPED_HOME -or -not (Test-Path $IPED_HOME)) {
    $IPED_HOME = [Microsoft.VisualBasic.Interaction]::InputBox(
        "Informe o caminho completo da pasta do IPED:",
        "SUPREME V5 - Caminho do IPED", "C:\iped-test-case")
    if (-not $IPED_HOME -or -not (Test-Path $IPED_HOME)) {
        [System.Windows.Forms.MessageBox]::Show("Caminho invalido.", "Erro", "OK", "Error") | Out-Null
        exit 1
    }
}

$SUPREME_URL = "https://localhost"

$scriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile      = Join-Path $scriptDir "supreme-backend\.env.production"
if (-not (Test-Path $envFile)) {
    [System.Windows.Forms.MessageBox]::Show("Rode SUBIR_LOCAL.ps1 primeiro.", "Erro", "OK", "Error") | Out-Null
    exit 1
}

function Get-EnvVal($file, $key) {
    $line = Get-Content $file | Where-Object { $_ -match "^${key}=" } | Select-Object -First 1
    if ($line) { return ($line -split "=", 2)[1] }
    return $null
}

$API_INGEST_TOKEN = Get-EnvVal $envFile "API_INGEST_TOKEN"
$API_SECRET_KEY   = Get-EnvVal $envFile "API_SECRET_KEY"
$SUPREME_SALT     = Get-EnvVal $envFile "SUPREME_SALT"

if (-not $API_INGEST_TOKEN) {
    [System.Windows.Forms.MessageBox]::Show("API_INGEST_TOKEN nao encontrado.", "Erro", "OK", "Error") | Out-Null
    exit 1
}

# Pedir ID funcional
$userId = [Microsoft.VisualBasic.Interaction]::InputBox(
    "Digite seu ID funcional para iniciar a sessao SUPREME V5:",
    "SUPREME V5 - Identificacao do Perito", "")
if ($userId -eq "") { exit }

# Calcular id_hash
$sha256 = [System.Security.Cryptography.SHA256]::Create()
$bytes  = [System.Text.Encoding]::UTF8.GetBytes($userId + $SUPREME_SALT)
$hash   = $sha256.ComputeHash($bytes)
$idHash = ($hash | ForEach-Object { $_.ToString("x2") }) -join ""
$sha256.Dispose()

$env:SUPREME_USER_ID = $userId
$auditLog = "$env:USERPROFILE\supreme_audit.ndjson"

function Open-Url {
    param([string]$Url)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Url
    $psi.UseShellExecute = $true
    [System.Diagnostics.Process]::Start($psi) | Out-Null
}

# Verificar quais formularios estao vencidos via API
$preInstruments = @(
    @{ key = "SRQ20";  label = "SRQ-20";  path = "srq20"  }
    @{ key = "DASS21"; label = "DASS-21"; path = "dass21" }
    @{ key = "OLBI";   label = "OLBI";    path = "olbi"   }
)

$toOpen = @()
$schedUrl = $SUPREME_URL + "/v1/schedule/" + $idHash
$schedResp = curl.exe -sk --max-time 8 -H "Authorization: Bearer $API_SECRET_KEY" $schedUrl 2>&1

if ($LASTEXITCODE -eq 0 -and ($schedResp -join "") -match "due_now") {
    try {
        $schedObj = ($schedResp -join "") | ConvertFrom-Json
        $dueNow   = @($schedObj.due_now | ForEach-Object { [string]$_ })
        $toOpen   = $preInstruments | Where-Object { $dueNow -contains $_.key }
        Write-Host "Schedule: vencidos = $($dueNow -join ', ')" -ForegroundColor Cyan
    } catch {
        Write-Host "Schedule parse falhou - abrindo todos." -ForegroundColor Yellow
        $toOpen = $preInstruments
    }
} else {
    Write-Host "Schedule API offline - abrindo todos (primeira sessao)." -ForegroundColor Yellow
    $toOpen = $preInstruments
}

# Formularios pre-IPED
if ($toOpen.Count -gt 0) {
    $nomes = ($toOpen | ForEach-Object { $_.label }) -join ", "
    [System.Windows.Forms.MessageBox]::Show(
        "Antes de iniciar, preencha os instrumentos psicometricos:`n`n$nomes`n`nEles serao abertos no navegador. Clique OK para continuar.",
        "SUPREME V5 - Pre-Sessao", "OK", "Information") | Out-Null

    foreach ($inst in $toOpen) {
        $formUrl = $SUPREME_URL + "/forms/" + $inst.path + "?user=" + $idHash + "&token=" + $API_INGEST_TOKEN
        Open-Url $formUrl
        Start-Sleep -Seconds 2
    }

    [System.Windows.Forms.MessageBox]::Show(
        "Preencha todos os formularios no navegador e clique OK para abrir o IPED.",
        "SUPREME V5 - Pre-Sessao", "OK", "Information") | Out-Null
}

# Registrar inicio de sessao
$sessionStart = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
$sessTs       = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$sessBody = '{"events":[{"id_hash":"' + $idHash + '","timestamp":"' + $sessionStart + '","event_type":"session_start","artifact_id":"session_' + $sessTs + '","severity":1,"duration_seconds":0,"source":"launcher"}]}'
$sessBody | Set-Content -Encoding UTF8 _sess.json
$ingestUrl = $SUPREME_URL + "/v1/events/ingest"
curl.exe -sk -X POST $ingestUrl -H "Content-Type: application/json" -H "Authorization: Bearer $API_INGEST_TOKEN" --data-binary "@_sess.json" 2>&1 | Out-Null
Remove-Item _sess.json -ErrorAction SilentlyContinue

# Registrar linhas antes de abrir IPED
$linesBefore = 0
if (Test-Path $auditLog) {
    $linesBefore = (Get-Content $auditLog | Measure-Object -Line).Lines
}

Write-Host "Abrindo IPED em: $IPED_HOME" -ForegroundColor Cyan

# Detectar executavel do IPED
$ipedExe = $null
$ipedJar = $null

if (Test-Path "$IPED_HOME\IPED-SearchApp.exe") {
    $ipedExe = "$IPED_HOME\IPED-SearchApp.exe"
} elseif (Test-Path "$IPED_HOME\iped-searchapp.jar") {
    $ipedJar = "$IPED_HOME\iped-searchapp.jar"
} elseif (Test-Path "$IPED_HOME\iped.jar") {
    $ipedJar = "$IPED_HOME\iped.jar"
} else {
    $jars = Get-ChildItem $IPED_HOME -Filter "*.jar" | Where-Object { $_.Name -match "iped" }
    if ($jars) { $ipedJar = $jars[0].FullName }
}

$patchJar = "$IPED_HOME\plugins\supreme-audit-patch.jar"
$extraCp  = ""
if (Test-Path $patchJar) {
    $extraCp = ";" + $patchJar
    Write-Host "Patch Java: $patchJar" -ForegroundColor Green
} else {
    Write-Host "Patch Java nao encontrado - duracao sera estimada." -ForegroundColor Yellow
}

$env:SUPREME_AUDIT_LOG = $auditLog
$env:SUPREME_USER_ID   = $userId

if ($ipedExe) {
    Start-Process $ipedExe -WorkingDirectory $IPED_HOME -Wait
} elseif ($ipedJar) {
    $javaArgs = "-cp `"" + $ipedJar + $extraCp + "`" iped.app.ui.App"
    Start-Process java -ArgumentList $javaArgs -WorkingDirectory $IPED_HOME -Wait
} else {
    [System.Windows.Forms.MessageBox]::Show(
        "IPED nao encontrado em: $IPED_HOME",
        "SUPREME V5 - Erro", "OK", "Error") | Out-Null
    exit 1
}

# Pos-sessao
Start-Sleep -Seconds 5

$linesAfter = 0
if (Test-Path $auditLog) {
    $linesAfter = (Get-Content $auditLog | Measure-Object -Line).Lines
}

$houveSessao = $true

# Registrar encerramento
$endTs   = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$endTime = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
$endBody = '{"events":[{"id_hash":"' + $idHash + '","timestamp":"' + $endTime + '","event_type":"session_end","artifact_id":"session_' + $endTs + '","severity":1,"duration_seconds":0,"source":"launcher"}]}'
$endBody | Set-Content -Encoding UTF8 _end.json
curl.exe -sk -X POST $ingestUrl -H "Content-Type: application/json" -H "Authorization: Bearer $API_INGEST_TOKEN" --data-binary "@_end.json" 2>&1 | Out-Null
Remove-Item _end.json -ErrorAction SilentlyContinue

# Verificar se PANAS esta vencido
$panasDue = $true
$sched2Resp = curl.exe -sk --max-time 8 -H "Authorization: Bearer $API_SECRET_KEY" $schedUrl 2>&1
if ($LASTEXITCODE -eq 0 -and ($sched2Resp -join "") -match "due_now") {
    try {
        $sched2Obj = ($sched2Resp -join "") | ConvertFrom-Json
        $due2      = @($sched2Obj.due_now | ForEach-Object { [string]$_ })
        $panasDue  = ($due2 -contains "PANAS_SHORT")
    } catch { }
}

if ($panasDue) {
    [System.Windows.Forms.MessageBox]::Show(
        "Sessao encerrada. O instrumento PANAS sera aberto para avaliacao pos-exposicao.",
        "SUPREME V5 - Pos-Sessao", "OK", "Information") | Out-Null
    $panasUrl = $SUPREME_URL + "/forms/panas?user=" + $idHash + "&token=" + $API_INGEST_TOKEN
    Open-Url $panasUrl
}

Write-Host "Sessao encerrada. Dashboard: https://localhost/sentinela/" -ForegroundColor Cyan
