# launch_sentinela.ps1
# Inicia o SENTINELA (Docker Compose) e abre o dashboard no navegador.

$ProjectDir = "C:\Users\nunas\OneDrive\Documentos\Claude\Projects\SUPREME V4 - IPED (1)\sentinela"
$URL        = "http://localhost:8001"

# Garante que o Docker Desktop está rodando
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    [System.Windows.Forms.MessageBox]::Show(
        "Docker não encontrado. Instale o Docker Desktop e tente novamente.",
        "SENTINELA", "OK", "Error"
    )
    exit 1
}

Write-Host "Iniciando SENTINELA..." -ForegroundColor Cyan

# Sobe os containers em background
Set-Location $ProjectDir
docker compose up -d 2>&1 | Out-Null

# Aguarda a API ficar disponível (até 30s)
$tentativas = 0
$pronto = $false
while ($tentativas -lt 15 -and -not $pronto) {
    Start-Sleep -Seconds 2
    try {
        $resp = Invoke-WebRequest -Uri "$URL/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($resp.StatusCode -eq 200) { $pronto = $true }
    } catch { }
    $tentativas++
}

# Abre o navegador
Start-Process $URL
Write-Host "SENTINELA disponível em $URL" -ForegroundColor Green
