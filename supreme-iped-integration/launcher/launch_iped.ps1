# ==============================================================
#  SUPREME V4 -- Launcher silencioso (sem terminal)
# ==============================================================
Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -AssemblyName System.Windows.Forms

$IpedHome      = "C:\iped-test-case"
$IpedExe       = "$IpedHome\IPED-SearchApp.exe"
$WatcherScript = (Split-Path $PSScriptRoot -Parent) + "\supreme-watcher\watcher.py"

$env:SUPREME_API_URL   = "http://localhost:8000"
$env:SUPREME_AUDIT_LOG = $env:USERPROFILE + "\supreme_audit.ndjson"
$env:SUPREME_SALT      = "dev-salt-local-troque-em-producao"
$env:WATCHER_POLL_SECS = "15"

$BackendUrl = $env:SUPREME_API_URL

# Abre URL no navegador padrao.
# ProcessStartInfo com UseShellExecute=$true funciona em PS5, PS7 e .NET Core.
function Open-Url { param([string]$Url)
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName       = $Url
        $psi.UseShellExecute = $true
        [System.Diagnostics.Process]::Start($psi) | Out-Null
        Write-Host "  [OK] Abriu: $Url"
    } catch {
        Write-Host "  [ERRO] Open-Url falhou: $_"
        # Fallback: cmd start, mais tolerante com & na URL
        $safe = $Url -replace '"', '%22'
        cmd /c start "" """$safe"""
    }
}

# 1. Pedir ID funcional
$userId = [Microsoft.VisualBasic.Interaction]::InputBox(
    "Digite seu ID funcional para iniciar a sessao SUPREME V4:",
    "SUPREME V4 - Telemetria de Exposicao Ocupacional",
    "perito_021"
)
if ($userId -eq "") { exit }

$env:SUPREME_USER_ID = $userId

# Calcular id_hash via SHA-256
$saltedId = $userId + $env:SUPREME_SALT
$sha256   = [System.Security.Cryptography.SHA256]::Create()
$bytes    = [System.Text.Encoding]::UTF8.GetBytes($saltedId)
$hash     = $sha256.ComputeHash($bytes)
$idHash   = ($hash | ForEach-Object { $_.ToString("x2") }) -join ""
$sha256.Dispose()

# Formularios pre-IPED e pos-IPED
$preInstruments = @(
    @{ key = "SRQ20";  form = "srq20"  }
    @{ key = "DASS21"; form = "dass21" }
    @{ key = "OLBI";   form = "olbi"   }
)

# 2. Verificar schedule e abrir formularios pre-IPED
try {
    $resp   = Invoke-RestMethod -Uri "$BackendUrl/v1/schedule/$idHash" -Method GET -TimeoutSec 8 -ErrorAction Stop
    $dueNow = @($resp.due_now | ForEach-Object { [string]$_ })
    $toOpen = $preInstruments | Where-Object { $dueNow -contains $_.key }
} catch {
    # Backend indisponivel -- abre todos por seguranca
    $toOpen = $preInstruments
}

if ($toOpen.Count -gt 0) {
    $nomes = ($toOpen | ForEach-Object { $_.key }) -join ", "
    [System.Windows.Forms.MessageBox]::Show(
        "Instrumentos a preencher antes de usar o IPED:`n`n$nomes`n`nOs formularios serao abertos no navegador.",
        "SUPREME V4", "OK", "Information") | Out-Null

    foreach ($inst in $toOpen) {
        $url = "$BackendUrl/forms/$($inst.form)?user=$idHash&backend=$BackendUrl"
        Open-Url $url
        Start-Sleep -Seconds 2
    }

    [System.Windows.Forms.MessageBox]::Show(
        "Preencha os formularios no navegador e clique OK para abrir o IPED.",
        "SUPREME V4", "OK", "Information") | Out-Null
}

# 3. Watcher em background
$watcherProc = $null
if (Test-Path $WatcherScript) {
    $watcherProc = Start-Process python -ArgumentList $WatcherScript -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

# Linhas no audit log antes de abrir o IPED
$auditLog    = $env:SUPREME_AUDIT_LOG
$linesBefore = 0
if (Test-Path $auditLog) { $linesBefore = (Get-Content $auditLog | Measure-Object -Line).Lines }

# 4. Abrir IPED
if (Test-Path $IpedExe) {
    Start-Process $IpedExe -Wait -WorkingDirectory $IpedHome
} else {
    [System.Windows.Forms.MessageBox]::Show(
        "IPED nao encontrado em: $IpedExe`n`nAjuste o caminho no launcher.",
        "SUPREME V4 - Erro", "OK", "Error") | Out-Null
}

# 5. Pos-sessao: abrir PANAS se houve exposicao
Start-Sleep -Seconds 15
$linesAfter = 0
if (Test-Path $auditLog) { $linesAfter = (Get-Content $auditLog | Measure-Object -Line).Lines }

if ($linesAfter -gt $linesBefore) {
    $panasDue = $true  # default: sempre abrir se houve exposicao
    try {
        $resp2    = Invoke-RestMethod -Uri "$BackendUrl/v1/schedule/$idHash" -Method GET -TimeoutSec 8 -ErrorAction Stop
        $due2     = @($resp2.due_now | ForEach-Object { [string]$_ })
        $panasDue = ($due2 -contains "PANAS_SHORT")
    } catch {}

    if ($panasDue) {
        [System.Windows.Forms.MessageBox]::Show(
            "Sessao encerrada. O PANAS sera aberto no navegador. Por favor preencha.",
            "SUPREME V4 - PANAS", "OK", "Information") | Out-Null
        Open-Url "$BackendUrl/forms/panas?user=$idHash&backend=$BackendUrl"
        Start-Sleep -Seconds 5
    }
}

# 6. Encerrar watcher
if ($null -ne $watcherProc -and -not $watcherProc.HasExited) {
    Stop-Process -Id $watcherProc.Id -Force -ErrorAction SilentlyContinue
}
