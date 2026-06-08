# Sentilela Nexus

Stack SUPREME V4/SENTINELA/IPED para coleta de eventos operacionais do IPED, processamento analitico no SUPREME e visualizacao no SENTINELA.

## Componentes

- `supreme-backend/`: API SUPREME, workers, ingestao, metricas e pipeline analitico.
- `sentinela/`: aplicacao SENTINELA, autenticacao, dashboard e exportacao.
- `supreme-iped-integration/`: watcher/proxy e patch de integracao com IPED.
- `infra/`: NGINX, Prometheus, Grafana e Loki.
- `scripts/`: automacoes de setup, smoke test, backup/restore e gate de producao.

## Comeco rapido local

Para teste local validado, use:

```powershell
.\SUBIR_LOCAL.ps1
```

Depois consulte:

- SUPREME health: `http://localhost/v1/health`
- SENTINELA: `http://localhost/sentinela/`
- Grafana: `http://localhost/grafana/`

Detalhes do fluxo local ficam em `docs/TESTE_LOCAL.md`.

## Producao e homologacao

Para preparar o ambiente real, siga `DEPLOY.md`.

Arquivos reais de ambiente e certificados nunca devem ser versionados:

- `.env`
- `supreme-backend/.env.production`
- `sentinela/.env.production`
- `infra/prometheus/supreme-api-token.local`
- `certs/fullchain.pem`
- `certs/privkey.pem`

Antes do go-live, o gate abaixo deve passar no servidor alvo:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\production_readiness_check.ps1
```

## Seguranca

- Nao commitar `.env`, `.env.production`, certificados, tokens, senhas ou chaves privadas.
- `SUPREME_SALT` deve ser guardado fora do Git e fora de backups automaticos.
- `API_SECRET_KEY` protege administracao e metricas.
- `API_INGEST_TOKEN` protege ingestao.
- `SENTINELA_API_KEY` no SUPREME deve ser igual a `SUPREME_API_KEY` no SENTINELA.
- `BOOTSTRAP_TOKEN` do SENTINELA deve ficar vazio apos criar o usuario master.

## Checks principais

```powershell
powershell -ExecutionPolicy Bypass -File scripts\production_readiness_check.ps1 -TemplateMode -SkipDockerCompose
```

```bash
cd supreme-backend
ruff check src tests
pytest -q
docker build -t supreme-backend:ci .
```

```bash
cd sentinela
pytest -q
docker build -t sentinela:ci .
```

## Documentacao relacionada

- `DEPLOY.md`: deploy de homologacao/producao.
- `docs/PRODUCAO_ENTERPRISE.md`: checklist enterprise e gate final.
- `AUDITORIA_PRODUCAO_READINESS.md`: auditoria de prontidao.
- `README_INSTALACAO.md`: instalacao detalhada e fluxo IPED.
- `docs/TESTE_LOCAL.md`: validacao local do stack.
