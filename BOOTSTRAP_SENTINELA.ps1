# Bootstrap do usuario master do SENTINELA
# Execute depois que o stack estiver rodando: .\BOOTSTRAP_SENTINELA.ps1

$envFile = ".\sentinela\.env.production"
if (-not (Test-Path $envFile)) {
    Write-Host "ERRO: $envFile nao encontrado. Rode SUBIR_LOCAL.ps1 primeiro." -ForegroundColor Red
    exit 1
}

$BOOTSTRAP_TOKEN = (Get-Content $envFile | Where-Object { $_ -match "^BOOTSTRAP_TOKEN=" }) -replace "^BOOTSTRAP_TOKEN=", ""
if (-not $BOOTSTRAP_TOKEN) {
    Write-Host "ERRO: BOOTSTRAP_TOKEN nao encontrado em $envFile" -ForegroundColor Red
    exit 1
}

$EMAIL    = "admin@local.test"
$PASSWORD = "SenhaForte123!"

Write-Host ""
Write-Host "Criando usuario master do SENTINELA..." -ForegroundColor Cyan

# Bootstrap
$bBody = '{"email":"' + $EMAIL + '","password":"' + $PASSWORD + '","role":"master"}'
$bBody | Set-Content -Encoding UTF8 _b.json
$bResp = curl.exe -sk -X POST https://localhost/sentinela/api/auth/bootstrap `
    -H "Content-Type: application/json" `
    -H "X-Bootstrap-Token: $BOOTSTRAP_TOKEN" `
    --data-binary "@_b.json" 2>&1
Remove-Item _b.json -ErrorAction SilentlyContinue
Write-Host "Bootstrap: $bResp" -ForegroundColor Yellow

# Login
$lBody = '{"email":"' + $EMAIL + '","password":"' + $PASSWORD + '"}'
$lBody | Set-Content -Encoding UTF8 _l.json
$lResp = curl.exe -sk -X POST https://localhost/sentinela/api/auth/login `
    -H "Content-Type: application/json" `
    --data-binary "@_l.json" 2>&1
Remove-Item _l.json -ErrorAction SilentlyContinue

if ($lResp -match "access_token") {
    Write-Host "Login OK." -ForegroundColor Green
    Write-Host ""
    Write-Host "Acesse: https://localhost/sentinela/" -ForegroundColor White
    Write-Host "Email : $EMAIL" -ForegroundColor White
    Write-Host "Senha : $PASSWORD" -ForegroundColor White
} else {
    Write-Host "Login falhou: $lResp" -ForegroundColor Red
}
