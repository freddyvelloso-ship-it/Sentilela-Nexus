# SUPREME V4 + SENTINELA — Guia de Instalacao

Sistema de monitoramento longitudinal de exposicao ocupacional para peritos forenses que usam o IPED.

---

## Visao geral

```
SUPREME V4 + SENTINELA
├── supreme-backend/          <- Servidor de coleta (SUPREME API + workers)
├── sentinela/                <- Dashboard do pesquisador (Sentinela API + frontend)
├── supreme-iped-integration/ <- Watcher e proxy para a maquina do perito
├── LAUNCHER_IPED.ps1         <- Launcher principal (roda na maquina do perito)
└── SUBIR_LOCAL.ps1           <- Setup automatico para ambiente local (Windows + Docker Desktop)
```

Fluxo de dados:
```
IPED (patch Java) → audit.ndjson → watcher.py → SUPREME API (/v1/events/ingest)
                                                      |
                                          pipeline IEO + PSI (worker)
                                                      |
                                              SENTINELA (push)
                                                      |
                                         Dashboard War Room / Formularios
```

Fluxo psicometrico (launcher):
```
LAUNCHER_IPED.ps1
  1. GET  https://NGINX/v1/schedule/{id_hash}          [Bearer API_SECRET_KEY]
     <- retorna due_now: ["DASS21","OLBI",...]

  2. Abre no browser: https://NGINX/forms/{instrumento}?user={id_hash}&token={API_INGEST_TOKEN}
     <- form le ?token= da URL e usa como Bearer no submit

  3. POST https://NGINX/v1/psychometric/submit          [Bearer API_INGEST_TOKEN]
     <- backend valida token e grava score + atualiza schedule
```

---

## Setup local (Windows + Docker Desktop) — uso recomendado

Para ambiente de desenvolvimento/piloto local, use o script automatico:

```powershell
cd supreme_final
.\SUBIR_LOCAL.ps1        # sobe toda a stack, gera segredos, faz bootstrap
.\LAUNCHER_IPED.ps1      # lanca o IPED com pre-sessao psicometrica
```

Acessos apos SUBIR_LOCAL.ps1:
- Sentinela: https://localhost/sentinela/   (admin@local.test / SenhaForte123!)
- War Room:  https://localhost/sentinela/static/war_room.html
- Health:    https://localhost/health (SUPREME) | https://localhost/sentinela/health (SENTINELA)

> Certificado autoassinado: aceitar o aviso de seguranca no Chrome na primeira visita.

---

## Setup producao (SENTINELA em servidor da universidade)

### Pre-requisitos

**Servidor SUPREME (maquina da unidade PF)**
- Windows 10/11 ou Ubuntu 22.04
- Docker Desktop 4.x ou Docker Engine 24+
- Acesso de rede saindo na porta 443 para o servidor do SENTINELA

**Servidor SENTINELA (servidor da universidade)**
- Ubuntu 22.04 recomendado
- Docker Engine 24+
- IP fixo ou hostname DNS acessivel pelo SUPREME
- Portas 80 e 443 abertas para o SUPREME e navegadores dos pesquisadores

**Maquina do perito**
- Windows 10/11
- IPED 4.2.x com patch Java aplicado (ver Passo 4)

---

## Passo 0 — Gerar credenciais de producao

```bash
python3 -c "import secrets; print('SUPREME_SALT     =', secrets.token_hex(32))"
python3 -c "import secrets; print('SUPREME_API_KEY  =', secrets.token_hex(24))"
python3 -c "import secrets; print('SENTINELA_SECRET =', secrets.token_hex(32))"
python3 -c "import secrets; print('BOOTSTRAP_TOKEN  =', secrets.token_hex(16))"
python3 -c "import secrets; print('POSTGRES_PASS_S  =', secrets.token_hex(16))"
python3 -c "import secrets; print('POSTGRES_PASS_B  =', secrets.token_hex(16))"
```

**SUPREME_SALT: guarde OFFLINE (papel/cofre). Nunca em backups automaticos, git ou e-mail.**

---

## Passo 1 — Instalar o SENTINELA (fazer primeiro)

### 1.1 Configurar .env

```bash
cd sentinela/
cp .env.production.example .env.production
# Preencher todos os valores
```

| Variavel | Instrucao |
|---|---|
| `POSTGRES_PASSWORD` | POSTGRES_PASS_S gerado no Passo 0 |
| `SECRET_KEY` | SENTINELA_SECRET gerado no Passo 0 |
| `SUPREME_API_KEY` | SUPREME_API_KEY gerado no Passo 0 (mesmo valor no SUPREME) |
| `BOOTSTRAP_TOKEN` | BOOTSTRAP_TOKEN gerado no Passo 0 (uso unico) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 43200 (30 dias) para sessoes longas |

### 1.2 Subir

```bash
docker compose -f docker-compose.production.yml up -d --build sentinela sentinela-db
# Aguardar healthcheck (30-60s), depois verificar:
curl -k https://localhost/sentinela/health
# Esperado: {"status":"ok","service":"sentinela"}
```

### 1.3 Criar usuario master (uso unico)

O token vai no HEADER X-Bootstrap-Token, nao no body:

```bash
curl -k -X POST https://localhost/sentinela/api/auth/bootstrap \
  -H 'Content-Type: application/json' \
  -H 'X-Bootstrap-Token: SEU_BOOTSTRAP_TOKEN' \
  -d '{"email":"pesquisador@univ.br","password":"SENHA_FORTE","role":"master"}'
# Esperado: {"id":1,"email":"pesquisador@univ.br","role":"master"}
```

**Apos criar o usuario: remover BOOTSTRAP_TOKEN do .env.production e reiniciar.**

```bash
# Comentar ou remover a linha BOOTSTRAP_TOKEN= do sentinela/.env.production
docker compose -f docker-compose.production.yml restart sentinela
```

### 1.4 Verificar login

```bash
curl -k -X POST https://localhost/sentinela/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"pesquisador@univ.br","password":"SENHA_FORTE"}'
# Esperado: {"access_token":"...","token_type":"bearer"}
```

---

## Passo 2 — Instalar o SUPREME Backend

### 2.1 Configurar .env

```bash
cd supreme-backend/
cp .env.production.example .env.production
```

| Variavel | Instrucao |
|---|---|
| `SUPREME_SALT` | Gerado no Passo 0. GUARDAR OFFLINE. |
| `SENTINELA_URL` | URL interna do sentinela. Ex: http://sentinela:8001 |
| `SENTINELA_API_KEY` | Identico ao SUPREME_API_KEY do .env do SENTINELA |
| `STUDY_START_DATE` | Data real de inicio da coleta: AAAA-MM-DD |
| `API_SECRET_KEY` | Chave forte — usada pelo launcher para consultar /v1/schedule/ |
| `API_INGEST_TOKEN` | Chave forte — usada pelo launcher/watcher para ingestao de eventos e submit de formularios |

### 2.2 Subir

```bash
docker compose -f docker-compose.production.yml up -d --build supreme-api supreme-db supreme-redis supreme-worker
# Verificar saude:
curl -k https://localhost/health
# Esperado: {"status":"ok"}
```

### 2.3 Verificar push SUPREME → SENTINELA

```bash
docker logs supreme_final-supreme-api-1 2>&1 | grep -i sentinela | head -5
# NAO deve aparecer: "SENTINELA push INATIVO"
```

---

## Passo 3 — Configurar a maquina do perito

O launcher principal e o `LAUNCHER_IPED.ps1` na raiz do projeto.
Ele le automaticamente as credenciais de `supreme-backend/.env.production`.

### 3.1 Pre-requisitos na maquina do perito

Copiar para a maquina do perito:
- `LAUNCHER_IPED.ps1`
- `supreme-backend/.env.production` (apenas as variaveis necessarias)

### 3.2 Uso

```powershell
cd caminho\para\supreme_final
.\LAUNCHER_IPED.ps1
# -> Abre caixa de dialogo pedindo ID funcional
# -> Consulta schedule API com API_SECRET_KEY
# -> Abre formularios pendentes no browser com token na URL
# -> Abre o IPED
# -> Apos fechar o IPED, abre PANAS pos-sessao
```

### 3.3 Token dos formularios psicometricos

O launcher passa `API_INGEST_TOKEN` como parametro de URL (`?token=`).
O formulario le esse token e o usa como `Authorization: Bearer` ao submeter para `/v1/psychometric/submit`.
O backend valida contra `API_INGEST_TOKEN` do `.env.production`.

**Se o submit falhar com 403**: verificar se o `API_INGEST_TOKEN` no `.env.production` da maquina do perito
e o que esta no container do SUPREME sao identicos.

---

## Passo 4 — Aplicar o patch Java no IPED

O patch registra eventos de abertura/fechamento de itens sem interceptar o conteudo.

### 4.1 Pre-requisitos

- JDK 11+ com JavaFX (recomendado: Liberica Full 11)
- Maven 3.8+
- Codigo-fonte do IPED na mesma tag da versao em producao

### 4.2 Modo rapido (JAR pre-compilado)

```powershell
# Copiar o JAR pre-compilado para a pasta plugins do IPED:
copy _patch_build\supreme-audit-patch.jar C:\iped-test-case\plugins\
# O IPED carrega automaticamente JARs da pasta plugins/ na inicializacao
```

### 4.3 Compilar do zero (para versoes diferentes do IPED)

```powershell
# 1. Clonar IPED na tag exata de producao
git clone https://github.com/sepinf-inc/IPED.git iped-source
cd iped-source
git checkout vX.Y.Z
mvn clean install -DskipTests -T4

# 2. Copiar e compilar o patch
copy supreme-iped-integration\iped-patch\src\main\java\iped\app\ui\SupremeAuditLogger.java `
     iped-source\iped-app\src\main\java\iped\app\ui\
# Editar ResultTableListener.java conforme iped-patch/BUILD.md
cd iped-source\iped-app
mvn clean package -DskipTests
copy target\*.jar C:\IPED\plugins\supreme-audit-patch.jar
```

Ver `supreme-iped-integration/iped-patch/BUILD.md` para instrucoes detalhadas.

> **ATENCAO**: testar em ambiente controlado antes do deploy definitivo.

---

## Uso diario (perito)

1. Abrir PowerShell e executar `.\LAUNCHER_IPED.ps1`
2. Digitar o ID funcional na caixa que aparecer
3. Se houver formularios no prazo: preencher no navegador e aguardar confirmacao de envio
4. Usar o IPED normalmente
5. Ao fechar o IPED: aguardar o PANAS abrir e preencher

**Frequencia dos formularios (automatica):**
- PANAS-Short: pos-sessao (janela de 2 dias)
- DASS-21: quinzenal (14 dias)
- OLBI / SRQ-20: mensal (30 dias)

---

## Rotas de API — referencia rapida

### SUPREME Backend (via NGINX em https://HOST)

| Metodo | Rota | Token | Descricao |
|---|---|---|---|
| GET | `/health` | nenhum | Health check |
| POST | `/v1/events/ingest` | Bearer API_INGEST_TOKEN | Ingesta eventos do watcher/proxy |
| GET | `/v1/schedule/{id_hash}` | Bearer API_SECRET_KEY | Consulta formularios pendentes |
| POST | `/v1/psychometric/submit` | Bearer API_INGEST_TOKEN | Submit de formulario psicometrico |
| GET | `/forms/{instrumento}` | nenhum (token na URL) | Serve HTML do formulario |

### SENTINELA (via NGINX em https://HOST/sentinela)

| Metodo | Rota completa | Token | Descricao |
|---|---|---|---|
| GET | `/sentinela/health` | nenhum | Health check |
| POST | `/sentinela/api/auth/bootstrap` | Header X-Bootstrap-Token | Cria primeiro usuario master (uso unico) |
| POST | `/sentinela/api/auth/login` | nenhum | Login, retorna JWT |
| GET | `/sentinela/api/dashboard/overview` | Bearer JWT | KPIs da unidade |
| GET | `/sentinela/api/dashboard/participants` | Bearer JWT (master) | Lista participantes |
| POST | `/sentinela/api/dashboard/participants/{id_hash}/lifecycle` | Bearer JWT (master) | Ciclo de vida |
| GET | `/sentinela/api/export/csv` | Bearer JWT | Export CSV para R |

---

## Verificacoes de saude

```bash
# SUPREME (via NGINX)
curl -k https://IP_SUPREME/health

# SENTINELA (via NGINX)
curl -k https://IP_SENTINELA/sentinela/health

# Schedule de um perito (substitua o hash)
curl -k -H "Authorization: Bearer API_SECRET_KEY" \
  https://IP_SUPREME/v1/schedule/HASH_DO_PERITO

# Log de auditoria na maquina do perito
Get-Content $env:USERPROFILE\supreme_audit.ndjson | Select-Object -Last 5
```

---

## Exportacao de dados (pesquisador)

No dashboard SENTINELA (https://IP_SENTINELA/sentinela/), aba **War Room** → botao Exportar.

Ou via API (JWT obtido no login):
```bash
curl -k -H "Authorization: Bearer SEU_JWT" \
     https://IP_SENTINELA/sentinela/api/export/csv > dados_supreme.csv
```

---

## Diagnostico de problemas

```bash
# Logs do SUPREME API
docker logs supreme_final-supreme-api-1 --tail 50

# Logs do SENTINELA
docker logs supreme_final-sentinela-1 --tail 50

# Logs do worker de pipeline
docker logs supreme_final-supreme-worker-1 --tail 30

# Submit falha com 403 — verificar token
docker exec supreme_final-supreme-api-1 env | grep API_INGEST_TOKEN
# Deve bater com o valor em supreme-backend/.env.production

# Dead Letter Queue (deve ser 0 em operacao normal)
curl -k https://IP_SUPREME/health
# campo: "queue_dead_letter_size": 0
```

---

## Seguranca — pontos criticos

| Item | Regra |
|---|---|
| `SUPREME_SALT` | NUNCA em backups automaticos, git ou e-mail. Guardar offline. |
| `.env.production` | NUNCA commitar no git. Usar `.env.production.example` como template. |
| `BOOTSTRAP_TOKEN` | Uso unico. Remover do .env apos criar usuario master. |
| `API_INGEST_TOKEN` na URL | O token aparece na URL dos formularios — usar HTTPS obrigatoriamente. |
| Banco de dados | Backup regular dos volumes Docker. |
| Dados dos peritos | Pseudonimizados por SHA-256+SALT desde a captura. Sem o SALT, reidentificacao e tecnicamente impossivel. |
