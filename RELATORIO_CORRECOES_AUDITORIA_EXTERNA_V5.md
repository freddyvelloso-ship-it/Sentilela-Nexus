# SUPREME V5 — Correções aplicadas após auditoria externa

Data: 2026-06-06  
Base: `SUPREME_V5_ENTERPRISE_PRODUCTION(1).zip`  
Entrega: `SUPREME_V5_ENTERPRISE_PRODUCTION_AUDIT_FIXES.zip`

## Escopo

Este pacote incorpora os achados críticos, altos e parte dos médios apontados em `AUDITORIA_SUPREME_V5.docx`, com foco em produção local/institucional segura.

## Correções aplicadas

### 1. Autenticação e segurança

- `BUG-01 / AUTH-01`: os endpoints psicométricos sob `/v1` agora usam `Depends(require_api_token)` no router.
- `SEC-01`: removido `unsafe-inline` da CSP do SUPREME e do SENTINELA; adicionados `object-src 'none'`, `base-uri 'self'` e `frame-ancestors 'none'`.
- `SEC-02`: comparação de `X-API-Key` no SENTINELA trocada para `hmac.compare_digest()`.
- `SEC-03`: Redis agora exige `REDIS_PASSWORD`; `REDIS_URL`, healthcheck e RQ worker foram atualizados.
- `SEC-04`: bootstrap do SENTINELA virou uso único persistente via `system_config.bootstrap_used`; comparação do bootstrap token também usa HMAC.
- `SEC-05`: JWT do SENTINELA agora inclui `jti`.
- `SEC-06`: CORS do SUPREME usa allowlist explícita de headers.

### 2. Banco de dados e LGPD

- `BUG-03`: `pool_pre_ping=True` adicionado ao SQLAlchemy engine.
- `BUG-04 / LGPD-01`: `erase_subject()` agora cobre `psi_scores`, `psychometric_items`, `dead_letter_queue` e `subject_consents`; `system_health_logs` e `audit_log` são anonimizados em vez de apagados.
- `BUG-05`: `fetch_ieo()` agora retorna `algorithm_version` e `algorithm_parameters`.
- `BUG-06`: criada migration 006 que remove `psychometric_data` como tabela órfã, mantendo `psychometric_submissions` como fonte canônica.
- `BUG-07`: migration 006 garante `instrument_schedule.last_submitted` com `ADD COLUMN IF NOT EXISTS`.
- `LGPD-03`: adicionado mecanismo formal de consentimento: `POST /v1/governance/consent/{id_hash}` com status `granted` ou `revoked`; o pipeline analítico não processa sujeito sem consentimento ativo.
- `LGPD-04`: criado `scripts/retention_cleanup.sh` para enforcement operacional de retenção: 18 meses para `events_raw`, 90 dias para `system_health_logs`.
- `LGPD-05`: apagamento de titular registra actor enriquecido com IP de origem.
- `LGPD-06`: formulários HTML receberam informativo LGPD antes da coleta.

### 3. Arquitetura e resiliência

- `BUG-02`: RQ worker agora escuta `analytics` e `dead_letter`.
- `ARQ-01`: push SUPREME → SENTINELA recebeu retry com backoff exponencial simples.
- `ARQ-04`: migration 006 força RLS em tabelas principais e concede `supreme_operator` ao role `supreme` usado no compose atual.
- `ARQ-06`: `algorithm_version` já estava vindo de `settings.algorithm_version`; mantido e validado.
- `DB-02`: `insert_events()` agora usa `pg_advisory_xact_lock(hashtext(event_hash))` para reduzir corrida entre SELECT e INSERT em ingestão concorrente.

### 4. Deploy, CI e backup

- `DEP-01`: Nginx recebeu server block HTTPS real, redirect HTTP → HTTPS e HSTS.
- `DEP-02`: removido `|| true` do CI; lint/teste agora falham o pipeline.
- `DEP-03`: adicionados `.dockerignore` em SUPREME e SENTINELA; removidos `__pycache__`, `.pytest_cache` e `.pyc` do pacote.
- `DEP-04`: TimescaleDB pinado para `timescale/timescaledb:2.16.1-pg16`.
- `DEP-05`: `supreme-api` recebeu healthcheck Docker via `/health` público mínimo.
- `DB-04 / DEP-07`: backup agora inclui banco SUPREME e SENTINELA e pode criptografar com GPG/AES256 quando `BACKUP_PASSPHRASE` estiver definida.

## Arquivos principais alterados

- `docker-compose.production.yml`
- `infra/nginx/conf.d/supreme.conf`
- `.github/workflows/ci.yml`
- `supreme-backend/src/app/api/psychometric.py`
- `supreme-backend/src/app/api/governance.py`
- `supreme-backend/src/app/db.py`
- `supreme-backend/src/app/main.py`
- `supreme-backend/src/app/middleware.py`
- `supreme-backend/src/worker/pipeline.py`
- `supreme-backend/src/engine/supreme/sentinela_push.py`
- `supreme-backend/supabase/migrations/006_hardening_audit_fixes.sql`
- `sentinela/src/app/api/ingest.py`
- `sentinela/src/app/api/auth_router.py`
- `sentinela/src/app/auth.py`
- `sentinela/src/app/middleware.py`
- `sentinela/migrations/001_sentinela_schema.sql`
- `scripts/backup_postgres.sh`
- `scripts/retention_cleanup.sh`

## Validação executada neste ambiente

```text
python -m py_compile $(find supreme-backend/src sentinela/src -name '*.py')
Resultado: OK
```

```text
cd supreme-backend && PYTHONPATH=. python -m pytest -q tests
Resultado: 4 passed
```

Limitação do ambiente: o teste do SENTINELA não foi executado porque a dependência `python-jose` não está instalada no sandbox, embora esteja corretamente declarada em `sentinela/requirements.txt`. Docker também não está disponível no sandbox, portanto `docker compose config` e `docker compose up` devem ser validados na sua máquina.

## Pendências que dependem de decisão institucional

- Criptografia de respostas psicométricas brutas em nível de aplicação (`LGPD-02`): a decisão correta depende de escolher se as respostas item-a-item serão preservadas para reprodutibilidade científica ou se apenas scores derivados serão retidos.
- Rotação automática de tokens estáticos (`AUTH-02`): exige Vault/AWS Secrets Manager/Docker Secrets ou outro cofre institucional.
- MFA/SSO institucional: depende do provedor de identidade da universidade/unidade.
- Teste de carga com volumetria real.
