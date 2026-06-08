# Deploy SUPREME/SENTINELA/IPED

Este runbook prepara homologacao ou producao sem versionar secrets. Execute os comandos a partir da raiz do repositorio.

## 1. Requisitos

- Windows PowerShell para automacoes locais ou shell equivalente no servidor.
- Docker e Docker Compose.
- Git com o codigo atualizado.
- Certificado TLS valido para producao publica ou certificado self-signed apenas para homologacao/local.
- Secrets fortes gerados fora do Git.

## 2. Arquivos locais obrigatorios

Crie estes arquivos no servidor alvo. Eles devem permanecer ignorados pelo Git:

- `.env`
- `supreme-backend/.env.production`
- `sentinela/.env.production`
- `infra/prometheus/supreme-api-token.local`
- `certs/fullchain.pem`
- `certs/privkey.pem`

Use os exemplos versionados como base:

```powershell
Copy-Item .env.production.example .env
Copy-Item supreme-backend\.env.production.example supreme-backend\.env.production
Copy-Item sentinela\.env.production.example sentinela\.env.production
```

Substitua todos os placeholders por secrets fortes. Nao use valores `CHANGE_ME_*`, `dev_*`, `localhost`, `example.org` ou `seu-dominio` em producao real.

## 3. Relacionamento entre secrets

- `.env` `POSTGRES_PASSWORD` deve bater com `supreme-backend/.env.production` `POSTGRES_PASSWORD`.
- `.env` `SENTINELA_POSTGRES_PASSWORD` deve bater com `sentinela/.env.production` `POSTGRES_PASSWORD`.
- `.env` `REDIS_PASSWORD` deve bater com `supreme-backend/.env.production` `REDIS_PASSWORD`.
- `supreme-backend/.env.production` `SENTINELA_API_KEY` deve ser igual a `sentinela/.env.production` `SUPREME_API_KEY`.
- `infra/prometheus/supreme-api-token.local` deve conter apenas o valor de `supreme-backend/.env.production` `API_SECRET_KEY`.
- `API_SECRET_KEY`, `API_INGEST_TOKEN` e `SUPREME_SALT` devem ser diferentes.
- `sentinela/.env.production` `BOOTSTRAP_TOKEN` deve ficar vazio depois da criacao do usuario master.

## 4. TLS

Para producao publica, instale certificado valido:

- `certs/fullchain.pem`: certificado publico e cadeia.
- `certs/privkey.pem`: chave privada correspondente.

Nao commite os arquivos em `certs/`. Se uma chave privada for exposta em chat, issue, PR, log ou e-mail, considere vazada e gere outra.

Certificados self-signed servem apenas para homologacao/local.

## 5. Gate antes de subir

Execute:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\production_readiness_check.ps1
```

O deploy so deve continuar se o resumo for:

```text
Resumo: 0 falha(s), 0 aviso(s).
```

Durante revisao de PR, valide apenas os templates:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\production_readiness_check.ps1 -TemplateMode -SkipDockerCompose
```

## 6. Subir o stack

```powershell
docker compose -f docker-compose.production.yml up -d --build
```

Verifique servicos:

```powershell
docker compose -f docker-compose.production.yml ps
```

## 7. Smoke test

Defina a URL do ambiente e rode:

```powershell
$env:BASE_URL = "https://SEU-DOMINIO-OU-IP"
$env:API_SECRET_KEY = "MESMO_VALOR_DE_SUPREME_API_SECRET_KEY"
bash scripts/smoke_test.sh
```

O smoke test deve validar:

- rota raiz via NGINX;
- health da SUPREME API;
- metricas protegidas por bearer token.

## 8. Bootstrap SENTINELA

Se ainda nao existir usuario master, use temporariamente `BOOTSTRAP_TOKEN` no `sentinela/.env.production`, crie o master e depois esvazie:

```env
BOOTSTRAP_TOKEN=
```

Reinicie o SENTINELA apos remover o token:

```powershell
docker compose -f docker-compose.production.yml up -d sentinela
```

Rode novamente o gate:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\production_readiness_check.ps1
```

## 9. Backup e restore

Execute backup:

```powershell
bash scripts/backup_postgres.sh
```

Valide restore em ambiente separado antes do go-live. Nao considere producao pronta sem restore testado.

## 10. Go/no-go

So considerar pronto para producao quando todos estiverem verdadeiros:

- PR aprovado e mergeado na `main`.
- CI verde.
- `scripts/production_readiness_check.ps1` passando no servidor alvo.
- Stack de homologacao sobe com `docker compose -f docker-compose.production.yml up -d --build`.
- SUPREME `/health` responde.
- SENTINELA `/health` responde.
- NGINX redireciona `/` para `/sentinela/`.
- Prometheus coleta `/metrics` com bearer token via `credentials_file`.
- Grafana acessivel.
- Backup e restore testados.
- Fluxo real IPED -> watcher/proxy -> SUPREME -> SENTINELA validado.
- `BOOTSTRAP_TOKEN` removido apos bootstrap.
- Nenhum `.env`, `.env.production`, `.pem`, `.key`, token local ou secret real versionado.

## 11. Rollback

Em falha de deploy:

```powershell
docker compose -f docker-compose.production.yml logs --tail=200
docker compose -f docker-compose.production.yml down
```

Restaure a versao anterior da branch/tag aprovada e suba novamente. Se banco foi alterado por migracao, restaure somente a partir de backup validado e registre o incidente.
