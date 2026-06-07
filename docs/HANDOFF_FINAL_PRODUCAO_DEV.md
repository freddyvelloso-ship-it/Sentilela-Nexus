# SUPREME V5 — Handoff final para produção e teste real

Data: 06/06/2026  
Status: **SENTINELA validado localmente via NGINX; SUPREME e IPED ainda exigem teste E2E com fluxo real.**

## 1. Objetivo deste arquivo

Este documento consolida todas as melhorias, correções e decisões técnicas feitas durante a estabilização do SUPREME V5 para que o time de desenvolvimento aplique no repositório final e prepare o teste com o sistema real.

O foco agora não é mais simular manualmente rotas isoladas. O próximo passo é testar o fluxo real:

```text
IPED real / audit.ndjson real
  -> watcher/proxy
  -> SUPREME API
  -> Redis/RQ worker
  -> cálculo IEO
  -> push para SENTINELA
  -> dashboard operacional
```

## 2. Correções críticas já incorporadas nesta versão

### 2.1 Segurança e autenticação

- Endpoints psicométricos protegidos por token.
- Separação de token de administração (`API_SECRET_KEY`) e token de ingestão (`API_INGEST_TOKEN`).
- Comparação de API key do SENTINELA com `hmac.compare_digest`.
- Bootstrap do SENTINELA de uso único e permanentemente desabilitado após criação do master.
- JWT do SENTINELA com `jti` para futura revogação/blacklist.
- `BOOTSTRAP_TOKEN` deve ser removido do ambiente após criação do usuário master.
- Todos os segredos devem ser rotacionados antes de produção, especialmente os que apareceram em logs locais.

### 2.2 Banco de dados e LGPD

- `erase_subject()` ampliado para cobrir tabelas adicionais, incluindo `psi_scores`, `psychometric_items` e `dead_letter_queue`.
- Logs e auditoria devem ser anonimizados, não simplesmente deletados, para preservar integridade de auditoria.
- Adicionada migration `006_hardening_audit_fixes.sql`.
- `pool_pre_ping=True` no SQLAlchemy para reduzir erro por conexão stale.
- `fetch_ieo()` deve retornar `algorithm_version` e `algorithm_parameters` para rastreabilidade científica.
- Rota de consentimento LGPD adicionada.
- Pipeline não deve processar sujeito sem consentimento ativo.

### 2.3 Infraestrutura

- Redis com senha obrigatória.
- Worker RQ consumindo `analytics` e `dead_letter`.
- NGINX com HTTPS, redirect HTTP -> HTTPS e HSTS.
- `supreme-api` e `sentinela` com healthcheck.
- Prometheus, Grafana e Loki mantidos na stack de observabilidade.
- Backup ampliado para incluir banco SUPREME e banco SENTINELA, com opção de criptografia GPG.
- `.dockerignore` adicionado para impedir cópia de `__pycache__`, `.pytest_cache` e `.pyc`.

### 2.4 CI/CD

- Removidos `|| true` de lint/testes no CI.
- Testes devem quebrar o build quando falharem.
- Docker Compose validado sintaticamente.

## 3. Correções descobertas durante instalação local

### 3.1 Front-end do SENTINELA apontava para porta errada

Problema encontrado:

```javascript
const API = 'http://localhost:8001';
```

Isso fazia o navegador tentar logar direto na porta 8001, que não estava publicada no host. O backend aceitava o login via NGINX, mas o front enviava para o destino errado.

Correção aplicada:

```javascript
const API = '/sentinela';
```

Arquivo:

```text
sentinela/static/index.html
```

Critério de aceite:

```powershell
curl.exe -k https://localhost/sentinela/ | Select-String "const API"
```

Resultado esperado:

```text
const API = '/sentinela';
```

### 3.2 NGINX precisava estar na rede backend

Problema encontrado: NGINX iniciou, mas não conseguia rotear corretamente para `sentinela` e `supreme-api` quando estava fora da rede dos serviços.

Correção exigida no Compose:

```yaml
services:
  nginx:
    networks:
      - backend
```

O serviço pode publicar `80` e `443` normalmente mesmo estando na rede `backend`.

### 3.3 Prometheus não aceita `--config.expand-env=true` nesta imagem

Problema encontrado: `prom/prometheus:v2.55.1` reiniciava quando recebia a flag:

```text
--config.expand-env=true
```

Correção:

```yaml
prometheus:
  command:
    - --config.file=/etc/prometheus/prometheus.yml
    - --storage.tsdb.retention.time=30d
```

### 3.4 Geração de segredos não deve depender de Python no Windows

Problema encontrado: a máquina Windows não tinha `python` instalado. O comando para gerar segredos falhou e placeholders `COLE_SEGREDO_*` foram usados por engano.

Correção: usar PowerShell nativo:

```powershell
function New-Secret {
  $bytes = New-Object byte[] 32
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $rng.GetBytes($bytes)
  return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
}
```

### 3.5 Bootstrap/Login do SENTINELA deve usar JSON em arquivo no PowerShell

Problema encontrado: `curl.exe --data-raw $body` no PowerShell gerou JSON inválido.

Forma robusta validada:

```powershell
@'
{
  "email": "admin@local.test",
  "password": "SenhaForte123!",
  "role": "master"
}
'@ | Set-Content -Encoding UTF8 .ootstrap.json

curl.exe -k -X POST https://localhost/sentinela/api/auth/bootstrap `
  -H "Content-Type: application/json" `
  -H "X-Bootstrap-Token: SEU_BOOTSTRAP_TOKEN" `
  --data-binary "@bootstrap.json"
```

Login validado via API:

```powershell
@'
{
  "email": "admin@local.test",
  "password": "SenhaForte123!"
}
'@ | Set-Content -Encoding UTF8 .\login.json

curl.exe -k -X POST https://localhost/sentinela/api/auth/login `
  -H "Content-Type: application/json" `
  --data-binary "@login.json"
```

Resultado esperado:

```json
{"access_token":"...","token_type":"bearer"}
```

## 4. Estado validado localmente

Foi validado em ambiente Windows + Docker Desktop:

```text
SENTINELA: healthy
SUPREME API: healthy
NGINX: Up, portas 80/443 publicadas
Redis: healthy
PostgreSQL SUPREME: healthy
PostgreSQL SENTINELA: healthy
Worker: Up
Prometheus: Up
```

Healthchecks confirmados:

```powershell
curl.exe -k https://localhost/health
curl.exe -k https://localhost/sentinela/health
```

Resultados esperados:

```json
{"status":"ok"}
{"status":"ok","service":"sentinela"}
```

## 5. Pendente antes de produção real

### 5.1 Loki ainda precisa ser corrigido

Durante o teste local, o `loki` apareceu como `Restarting`. Isso não bloqueia SENTINELA/SUPREME, mas bloqueia observabilidade plena.

Ação do dev:

```powershell
docker compose -f docker-compose.production.yml -f docker-compose.local.yml logs --tail=200 loki
```

Corrigir conforme erro real. Hipóteses prováveis:

- permissão no volume `/loki`;
- configuração incompatível do Loki 3.2.1;
- necessidade de diretórios WAL/cache explícitos;
- uso de `user: "0:0"` apenas em ambiente local.

Critério de aceite para produção:

```text
loki Up, sem restart loop
Grafana consegue consultar datasource Loki
```

### 5.2 TLS real

O certificado autoassinado usado localmente gera `ERR_CERT_AUTHORITY_INVALID` no Chrome. Isso é esperado em teste local.

Produção exige:

- certificado válido de CA pública;
- domínio real;
- renovação automática ou procedimento documentado;
- HSTS apenas depois de confirmar HTTPS estável.

### 5.3 Segredos expostos nos logs locais devem ser rotacionados

Alguns tokens foram impressos durante o teste local. Antes de qualquer produção:

- gerar novos `API_SECRET_KEY`;
- gerar novo `API_INGEST_TOKEN`;
- gerar novo `BOOTSTRAP_TOKEN`, usar uma vez e remover;
- gerar novo `SUPREME_SALT`;
- gerar nova `SENTINELA_API_KEY`;
- gerar novas senhas de banco/Redis/Grafana.

### 5.4 Teste real IPED -> SUPREME -> SENTINELA ainda não foi executado

Ainda falta validar a integração com IPED real. O teste deve usar o fluxo real do arquivo `audit.ndjson` ou mecanismo equivalente produzido pelo IPED.

Critérios mínimos:

1. IPED gera evento real.
2. Watcher/proxy lê evento real.
3. Evento chega em `/v1/events/ingest`.
4. `events_raw` recebe o evento.
5. Worker RQ processa.
6. Consentimento LGPD permite processamento.
7. IEO é calculado com `algorithm_version`.
8. Resultado é enviado ao SENTINELA.
9. Dashboard mostra dado do sujeito pseudonimizado.
10. Logs/auditoria registram acesso/processamento.

## 6. Comandos de smoke test recomendados

### 6.1 Status geral

```powershell
docker compose -f docker-compose.production.yml -f docker-compose.local.yml ps
```

### 6.2 SUPREME health

```powershell
curl.exe -k https://localhost/health
```

### 6.3 SENTINELA health

```powershell
curl.exe -k https://localhost/sentinela/health
```

### 6.4 Front do SENTINELA usando rota correta

```powershell
curl.exe -k https://localhost/sentinela/ | Select-String "const API"
```

Esperado:

```text
const API = '/sentinela';
```

### 6.5 Login SENTINELA via API

```powershell
curl.exe -k -X POST https://localhost/sentinela/api/auth/login `
  -H "Content-Type: application/json" `
  --data-binary "@login.json"
```

Esperado: `access_token`.

### 6.6 Métricas SUPREME protegidas

```powershell
curl.exe -k https://localhost/metrics `
  -H "Authorization: Bearer SEU_API_SECRET_KEY"
```

### 6.7 Ingestão SUPREME

```powershell
@'
{
  "events": [
    {
      "id_hash": "local_test_user_001",
      "timestamp": "2026-06-06T20:30:00Z",
      "event_type": "view",
      "artifact_id": "artifact_test_001",
      "severity": 2,
      "duration_seconds": 30,
      "source": "local_test"
    }
  ]
}
'@ | Set-Content -Encoding UTF8 .\event_test.json

curl.exe -k -X POST https://localhost/v1/events/ingest `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer SEU_API_INGEST_TOKEN" `
  --data-binary "@event_test.json"
```

### 6.8 Verificação no banco

```powershell
docker exec -it supreme_final-supreme-db-1 psql -U supreme -d supreme
```

```sql
SELECT COUNT(*) FROM events_raw;
SELECT id_hash, event_type, artifact_id, severity, duration_seconds, source
FROM events_raw
ORDER BY timestamp DESC
LIMIT 10;
```

## 7. Arquivos alterados ou adicionados nesta entrega

```text
sentinela/static/index.html
  - API base alterada de http://localhost:8001 para /sentinela.

docker-compose.production.yml
  - NGINX conectado à rede backend.
  - Prometheus sem flag incompatível --config.expand-env=true.
  - Grafana preparado para subpath /grafana/.

docker-compose.local.yml
  - Override local validado para Windows/Docker Desktop.

scripts/windows_local_setup_validado.ps1
  - Setup local sem dependência de Python no Windows.
  - Geração de segredos via PowerShell.
  - Criação de .env, .env.production, certs e override local.

docs/HANDOFF_FINAL_PRODUCAO_DEV.md
  - Este documento de handoff.
```

## 8. Recomendação final para o dev

Aplicar estes patches no repositório principal e só então testar o sistema real.

Não iniciar teste real com IPED usando a versão anterior do ZIP, porque nela o front do SENTINELA ainda aponta para `http://localhost:8001`, o NGINX pode ficar fora da rede backend, e o Prometheus usa flag incompatível.

Versão mínima aceitável para teste real:

```text
SENTINELA login via UI: OK
SUPREME health: OK
SUPREME metrics autenticado: OK
Ingestão manual: OK
Banco recebe events_raw: OK
Worker processa jobs: OK
IPED real gera audit.ndjson: pendente
Watcher/proxy envia para SUPREME: pendente
IEO aparece no SENTINELA: pendente
Loki observability: pendente para produção plena
```
