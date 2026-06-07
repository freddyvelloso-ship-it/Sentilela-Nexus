# SUPREME V4 + SENTINELA — Auditoria técnica e correções em 6 camadas

Data: 2026-06-05  
Escopo: pacote `SUPREME_V4_PRODUCAO_FINAL_v2.zip`  
Objetivo: elevar o sistema de protótipo avançado para uma base corrigida de pré-produção/piloto controlado.

## Veredito executivo

O pacote original não estava pronto para produção. O principal bloqueador era compilação quebrada em `supreme-backend/src/app/db.py` por bytes nulos. Além disso, havia autenticação incompleta no endpoint de ingestão, segredos hardcoded, CORS aberto, hash de senha fraco no SENTINELA, dashboard RQ exposto, deduplicação inconsistente entre proxy e watcher, e criação automática de tabelas no startup.

Este pacote corrigido remove os bloqueadores técnicos principais e entrega uma base mais segura para piloto controlado. Ainda não substitui uma homologação institucional completa, porque produção real exige TLS/reverse proxy, backup/restore testado, observabilidade, gestão formal de segredos e CI/CD externo.

---

## 1. Build / Dependências

### Achados
- `supreme-backend/src/app/db.py` continha 7017 bytes nulos e impedia importação.
- `supreme-backend/src/app/config.py` estava truncado: faltava `get_settings()` e `log_level`, embora esses símbolos fossem usados por `main.py` e `db.py`.
- O watcher usava `requests`, mas o requisito não estava declarado em `supreme-iped-integration/requirements.txt`.
- Não havia testes automatizados mínimos.

### Correções aplicadas
- Removidos bytes nulos de `supreme-backend/src/app/db.py`.
- Reescrita configuração tipada do backend com `get_settings()`, `LOG_LEVEL`, CORS parametrizável, segredo de API, token de ingestão e salt obrigatório.
- Incluído `requests>=2.32` nas dependências da integração IPED.
- Adicionados testes mínimos:
  - `supreme-backend/tests/test_event_hash_identity.py`
  - `supreme-backend/tests/test_security_dependency.py`
  - `sentinela/tests/test_password_hashing.py`
- Validação de sintaxe feita com `python -m compileall` para backend, SENTINELA, proxy e watcher.

### Status após correção
**Parcialmente concluída para pré-produção.** Compilação Python corrigida. Testes foram adicionados, mas a execução completa depende da instalação das dependências do ambiente.

---

## 2. Segurança

### Achados
- `POST /v1/events/ingest` aceitava eventos sem validar o token `Authorization: Bearer`.
- `SUPREME_SALT` possuía fallback inseguro (`DEFINA_SALT_OFFLINE`).
- `API_SECRET_KEY` possuía default inseguro.
- CORS aberto no SUPREME e no SENTINELA.
- SENTINELA usava `sha256(password)` sem salt adaptativo.
- RQ Dashboard estava exposto em `0.0.0.0:9181`.
- Postgres e Redis eram publicados em interfaces externas por padrão.

### Correções aplicadas
- Criado `supreme-backend/src/app/security.py` com `require_ingest_token()` usando comparação constante (`hmac.compare_digest`).
- Endpoint de ingestão agora exige `API_INGEST_TOKEN` via `Authorization: Bearer`.
- `API_SECRET_KEY`, `API_INGEST_TOKEN` e `SUPREME_SALT` agora são obrigatórios e rejeitam placeholders.
- CORS do SUPREME e SENTINELA agora usa `ALLOWED_ORIGINS`.
- SENTINELA agora usa `passlib`/bcrypt para senhas.
- Login do SENTINELA mantém compatibilidade com hashes SHA-256 antigos e faz rehash automático em bcrypt após autenticação bem-sucedida.
- RQ Dashboard foi removido do compose principal e movido para `docker-compose.observability.yml`, preso a `127.0.0.1` e profile `observability`.
- Portas Postgres, Redis, API SUPREME e API SENTINELA foram presas a `127.0.0.1` nos compose locais.
- Proxy e watcher agora falham se `SUPREME_SALT` ou `SUPREME_API_TOKEN` estiverem ausentes/fracos.

### Status após correção
**Melhorado substancialmente.** Ainda faltam TLS, reverse proxy, rotação de segredos, rate limit, auditoria de acesso e política formal de credenciais.

---

## 3. Banco de Dados

### Achados
- Senha de Postgres hardcoded no `docker-compose.yml` do SUPREME.
- Deduplicação baseada em `event_hash` não estava coerente entre evento imediato e evento enriquecido com duração real.
- `payload::jsonb` e `detail::jsonb` podiam ser interpretados incorretamente pelo SQLAlchemy `text()`.
- SENTINELA executava criação/migração de tabelas no startup.

### Correções aplicadas
- `POSTGRES_PASSWORD` passou a vir de variável de ambiente obrigatória.
- `DATABASE_URL` do compose passou a depender de `${POSTGRES_PASSWORD}`.
- `event_hash` agora exclui `duration_seconds`, preservando identidade do mesmo evento entre proxy e watcher.
- `insert_events()` agora atualiza `duration_seconds` de duplicata quando o watcher envia duração maior.
- Casts SQL trocados para `cast(:payload as jsonb)` e `cast(:detail as jsonb)`.
- SENTINELA recebeu `AUTO_INIT_DB=false` por padrão; criação automática só em desenvolvimento/piloto controlado.

### Status após correção
**Parcialmente concluído.** O modelo está mais consistente, mas produção ainda exige migrations versionadas, backup/restore testado, política de retenção, partições futuras automatizadas e testes com banco real.

---

## 4. Arquitetura

### Achados
- O sistema tem uma arquitetura conceitual correta: IPED → watcher/proxy → SUPREME → pipeline IEO → SENTINELA.
- A fronteira entre telemetria operacional e dashboard estava razoavelmente separada.
- Porém, havia acoplamento operacional excessivo por variáveis soltas e comportamento divergente entre proxy e watcher.
- O pipeline dependia de convenções implícitas, sem contratos de execução testados.

### Correções aplicadas
- Introduzido contrato explícito de autenticação entre agentes e backend (`API_INGEST_TOKEN`).
- Unificada identidade de evento para permitir enriquecimento tardio sem duplicação.
- Centralizada configuração crítica no SUPREME e SENTINELA.
- Separado observability dashboard do core runtime.
- Adicionados testes de contrato para hash de evento e segurança de ingestão.

### Status após correção
**Pré-produção controlada.** A arquitetura agora é coerente para piloto. Para produção institucional, ainda precisa de ADRs, diagramas operacionais, CI/CD e política formal de deploy.

---

## 5. Produto

### Achados
- O produto entrega uma tese clara: monitoramento longitudinal de exposição ocupacional para peritos forenses.
- A instalação ainda presume operador técnico.
- Falta onboarding robusto: configuração guiada, validação de pré-requisitos, tela de status dos agentes, mensagens de erro amigáveis e checklist de saúde.
- Não há definição explícita de papéis operacionais, ciclo de suporte ou critérios de aceite.

### Correções aplicadas
- Foram criados exemplos `.env` mais explícitos para desenvolvimento e produção.
- Configurações inseguras agora falham cedo, reduzindo erro silencioso de operador.
- Dashboard RQ foi retirado do caminho principal para reduzir superfície de confusão/risco.

### Status após correção
**Não concluído como produto final.** A base técnica melhorou, mas ainda falta camada de experiência operacional e documentação de uso por perfil: perito, pesquisador, admin de TI e coordenador institucional.

---

## 6. Escalabilidade

### Achados
- Há uso de Postgres particionado, Redis e worker RQ, o que é bom para evolução.
- Mas o compose é single-node e não há estratégia de escala horizontal, backpressure, métricas, tracing, alertas ou retenção ativa.
- Deduplicação fazia SELECT-then-INSERT e pode sofrer corrida sob concorrência alta.

### Correções aplicadas
- O sistema agora tem separação mais clara entre core runtime e observability opcional.
- O hash de evento e enriquecimento tardio foram estabilizados.
- Testes de contrato reduzem regressão em componentes de ingestão.

### Status após correção
**Não concluído para escala.** Para escala real, implementar:
1. reverse proxy TLS;
2. filas por prioridade;
3. retry/backoff com DLQ observável;
4. métricas Prometheus/OpenTelemetry;
5. particionamento contínuo;
6. backup/restore automatizado;
7. CI/CD com testes e análise estática;
8. hardening de containers;
9. política de retenção de 18 meses aplicada por job;
10. carga sintética para validar throughput.

---

## Arquivos alterados ou adicionados

### SUPREME Backend
- `supreme-backend/src/app/config.py`
- `supreme-backend/src/app/security.py`
- `supreme-backend/src/app/api/ingest.py`
- `supreme-backend/src/app/main.py`
- `supreme-backend/src/app/db.py`
- `supreme-backend/src/engine/supreme/models.py`
- `supreme-backend/docker-compose.yml`
- `supreme-backend/docker-compose.observability.yml`
- `supreme-backend/.env.example`
- `supreme-backend/.env.production.example`
- `supreme-backend/supabase/migrations/001_supreme_schema.sql`
- `supreme-backend/tests/test_event_hash_identity.py`
- `supreme-backend/tests/test_security_dependency.py`

### SENTINELA
- `sentinela/src/app/config.py`
- `sentinela/src/app/auth.py`
- `sentinela/src/app/main.py`
- `sentinela/src/app/api/ingest.py`
- `sentinela/docker-compose.yml`
- `sentinela/.env.example`
- `sentinela/.env.production.example`
- `sentinela/tests/test_password_hashing.py`

### Integração IPED
- `supreme-iped-integration/supreme-watcher/watcher.py`
- `supreme-iped-integration/supreme-proxy/proxy.py`
- `supreme-iped-integration/requirements.txt`

---

## Checklist para próxima etapa

Antes de qualquer implantação real:

1. Gerar segredos reais com `openssl rand -hex 32` ou cofre institucional.
2. Aplicar migrations em banco limpo e validar rollback lógico.
3. Rodar testes em ambiente com dependências instaladas.
4. Colocar SUPREME e SENTINELA atrás de reverse proxy TLS.
5. Validar ingestão real com IPED em estação controlada.
6. Criar backup/restore e testar restauração.
7. Configurar logs estruturados, métricas e alertas.
8. Rodar teste de carga sintético.
9. Congelar versão para piloto.
10. Escrever termo operacional de retenção, acesso e pseudonimização.

## Veredito final

Após as correções, o sistema saiu de “não executável / inseguro para produção” para “base técnica corrigida para piloto controlado”. Ainda não deve ser vendido como produção institucional plena sem a camada operacional de DevOps, segurança perimetral, observabilidade e governança de dados.
