# gerar_cert_local.ps1
# Gera certificado TLS self-signed local para NGINX.
# Apenas para teste local.

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force ".\certs" | Out-Null

docker run --rm `
  -v "${PWD}\certs:/certs" `
  alpine/openssl req -x509 -nodes -days 365 `
  -newkey rsa:2048 `
  -keyout /certs/privkey.pem `
  -out /certs/fullchain.pem `
  -subj "/CN=localhost"

Write-Host "Certificados locais gerados:"
Write-Host " - certs\fullchain.pem"
Write-Host " - certs\privkey.pem"
Write-Host ""
Write-Host "Atenção: certs\privkey.pem é chave privada e não deve ser commitada."