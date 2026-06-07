# SUPREME V4 + SENTINELA — Guia de Instalacao

Sistema de monitoramento longitudinal de exposicao ocupacional para peritos forenses que usam o IPED.

---

## Visao geral

```
SUPREME V4 + SENTINELA
├── supreme-backend/          <- Servidor de coleta (roda na maquina da unidade PF)
├── sentinela/                <- Dashboard do pesquisador (roda em servidor da universidade)
├── supreme-iped-integration/ <- Cliente (vai para a maquina do perito)
└── README_INSTALACAO.md      <- Este arquivo
```

Fluxo de dados:
```
IPED (patch Java) → audit.ndjson → watcher.py → SUPREME → pipeline IEO → SENTINELA
                                                         ↑
                                         formularios psicometricos (browser)
```

---

## Pre-requisitos

### Servidor SUPREME (maquina da unidade PF)
- Windows 10/11 ou Ubuntu 22.04
- Docker Desktop 4.x ou Docker Engine 24+
- Acesso de rede saindo para o servidor do SENTINELA (porta 8001)

### Servidor SENTINELA (servidor da universidade)
- Ubuntu 22.04 recomendado
- Docker Engine 24+
- IP fixo ou hostname DNS acessivel pelo SUPREME

### Maquina do perito
- Windows 10/11
- Python 3.10+
- IPED 4.2.x com patch Java aplicado (ver secao 4)

---

## Passo 0 — Gerar credenciais de producao

Execute em qualquer terminal Python para gerar todas as chaves:

```powershell
python -c "import secrets; print('SUPREME_SALT     =', secrets.token_hex(32))"
python -c "import secrets; print('SUPREME_API_KEY  =', secrets.token_hex(24))"
python -c "import secrets; print('SENTINELA_SECRET =', secrets.token_hex(32))"
python -c "import secrets; print('BOOTSTRAP_TOKEN  =', secrets.token_hex(16))"
python -c "import secrets; print('POSTGRES_PASS_S  =', secrets.token_hex(16))"
python -c "import secrets; print('POSTGRES_PASS_B  =', secrets.token_hex(16))"
```

**SUPREME_SALT: guarde OFFLINE (papel/cofre). Nunca em backups automaticos ou git.**

---

## Passo 1 — Instalar o SENTINELA (fazer primeiro)

### 1.1 Configurar .env

```bash
cd sentinela/
cp .env.production.example .env
# Preencher todos os valores marcados com !!!
```

Valores obrigatorios:
| Variavel | Instrucao |
|---|---|
| `POSTGRES_PASSWORD` | POSTGRES_PASS_S gerado no Passo 0 |
| `DATABASE_URL` | Atualizar com a mesma senha |
| `SECRET_KEY` | SENTINELA_SECRET gerado no Passo 0 |
| `SUPREME_API_KEY` | SUPREME_API_KEY gerado no Passo 0 (mesmo valor no SUPREME) |
| `BOOTSTRAP_TOKEN` | BOOTSTRAP_TOKEN gerado no Passo 0 (uso unico) |

### 1.2 Subir

```bash
docker compose up -d --build
curl http://localhost:8001/health
# Esperado: {"status":"ok","service":"sentinela"}
```

### 1.3 Criar usuario master

```bash
curl -X POST http://localhost:8001/auth/bootstrap \
  -H 'Content-Type: application/json' \
  -d '{"token":"SEU_BOOTSTRAP_TOKEN","email":"pesquisador@univ.br","password":"SENHA_FORTE","role":"master"}'
```

**Apos criar o usuario: remover BOOTSTRAP_TOKEN do .env e reiniciar.**

```bash
# Remover a linha BOOTSTRAP_TOKEN= do .env, depois:
docker compose restart api
```

---

## Passo 2 — Instalar o SUPREME Backend

### 2.1 Configurar .env

```bash
cd supreme-backend/
cp .env.production.example .env
# Preencher todos os valores marcados com !!!
```

Valores obrigatorios:
| Variavel | Instrucao |
|---|---|
| `SUPREME_SALT` | Gerado no Passo 0. GUARDAR OFFLINE. |
| `SENTINELA_URL` | URL do SENTINELA sem barra. Ex: http://192.168.1.100:8001 |
| `SENTINELA_API_KEY` | Identico ao SUPREME_API_KEY do .env do SENTINELA |
| `STUDY_START_DATE` | Data real de inicio da coleta: AAAA-MM-DD |
| `API_SECRET_KEY` | Chave forte (pode usar secrets.token_hex(32)) |

> **Linux**: `host.docker.internal` nao existe. Usar IP real do servidor SENTINELA em `SENTINELA_URL`.

### 2.2 Subir

```bash
cd supreme-backend/
docker compose up -d --build
curl http://localhost:8000/v1/health
# Esperado: {"status":"ok","database":"connected"}
```

### 2.3 Verificar push SUPREME → SENTINELA

```bash
docker logs supreme-backend-api-1 2>&1 | grep SENTINELA | head -5
# NAO deve aparecer: "SENTINELA push INATIVO"
```

---

## Passo 3 — Configurar a maquina do perito

### 3.1 Instalar dependencias Python

```powershell
cd supreme-iped-integration\
pip install -r requirements.txt
```

### 3.2 Editar o launcher

Abra `launcher\launch_iped.ps1` e ajuste no topo:

```powershell
$IpedHome            = "C:\IPED"                       # caminho real do IPED
$IpedExe             = "$IpedHome\IPED-SearchApp.exe"  # executavel real
$env:SUPREME_API_URL = "http://IP_DO_SUPREME:8000"     # URL do SUPREME Backend
$env:SUPREME_SALT    = "O_MESMO_SALT_DO_SERVIDOR"      # SALT (mesmo do Passo 0)
```

### 3.3 Criar atalho na area de trabalho

Copiar a pasta `supreme-iped-integration\launcher\` para `C:\SUPREME\launcher\`
e criar um atalho do Windows apontando para `launch_iped.vbs` com nome **IPED SUPREME**.

O arquivo `.vbs` abre o launcher sem janela de terminal visivel.

---

## Passo 4 — Aplicar o patch Java no IPED

O patch registra eventos de abertura/fechamento de itens sem interceptar o conteudo.

### 4.1 Pre-requisitos

- [JDK Liberica Full 11](https://bell-sw.com/pages/downloads/#jdk-11-lts) (com JavaFX)
- Maven 3.8+
- Codigo fonte do IPED na **mesma tag** da versao em producao

### 4.2 Compilar e aplicar

```powershell
# 1. Clonar IPED na tag exata de producao
git clone https://github.com/sepinf-inc/IPED.git iped-source
cd iped-source
git checkout vX.Y.Z
mvn clean install -DskipTests -T4

# 2. Copiar SupremeAuditLogger.java
copy supreme-iped-integration\iped-patch\src\main\java\iped\app\ui\SupremeAuditLogger.java `
     iped-source\iped-app\src\main\java\iped\app\ui\

# 3. Editar ResultTableListener.java conforme iped-patch/BUILD.md

# 4. Recompilar
cd iped-source\iped-app
mvn clean package -DskipTests

# 5. Substituir JAR (com backup)
copy C:\IPED\iped-app-X.Y.Z.jar C:\IPED\iped-app-X.Y.Z.jar.bak
copy iped-source\iped-app\target\iped-app-X.Y.Z.jar C:\IPED\iped-app-X.Y.Z.jar
```

Ver `supreme-iped-integration/iped-patch/BUILD.md` para instrucoes detalhadas.

> **ATENCAO**: o patch nunca foi testado com o IPED real de producao da PF.
> Testar em ambiente controlado antes do deploy definitivo.

---

## Uso diario (perito)

1. Clicar duas vezes no atalho **IPED SUPREME** na area de trabalho
2. Digitar o ID funcional na caixa que aparecer
3. Se houver formularios no prazo: preencher no navegador e confirmar envio
4. Usar o IPED normalmente
5. Ao fechar o IPED: aguardar o PANAS abrir (ate 15 segundos) e preencher

**Frequencia dos formularios** (automatica, nao requer acao do pesquisador):
- PANAS-Short: apos cada sessao (2 dias)
- DASS-21: quinzenal (14 dias)
- OLBI / SRQ-20: mensal (30 dias)

---

## Verificacoes de saude

```bash
# SUPREME Backend
curl http://IP_SUPREME:8000/v1/health

# SENTINELA
curl http://IP_SENTINELA:8001/health

# Log de auditoria na maquina do perito
Get-Content $env:USERPROFILE\supreme_audit.ndjson | Select-Object -Last 5
```

---

## Exportacao de dados (pesquisador)

No dashboard SENTINELA (http://IP_SENTINELA:8001), menu **Exportar** → CSV para R.

Ou via API:
```bash
curl -H "Authorization: Bearer SEU_TOKEN" \
     http://IP_SENTINELA:8001/api/export/csv > dados_supreme.csv
```

---

## Seguranca — pontos criticos

| Item | Regra |
|---|---|
| `SUPREME_SALT` | NUNCA em backups automaticos, git ou e-mail. Guardar offline. |
| `.env` | NUNCA commitar no git. Usar `.env.production.example` como template. |
| `BOOTSTRAP_TOKEN` | Uso unico. Remover do .env apos criar usuario master. |
| Banco de dados | Backup regular dos volumes Docker. |
| Dados dos peritos | Pseudonimizados por SHA-256+SALT desde a captura. Sem o SALT, reidentificacao e tecnicamente impossivel. |

---

## Suporte — diagnostico de problemas

```bash
# Logs do SUPREME
docker logs supreme-backend-api-1 --tail 50

# Logs do SENTINELA
docker logs sentinela-api-1 --tail 50

# Verificar se push SENTINELA esta ativo (nao deve aparecer "INATIVO")
docker logs supreme-backend-api-1 2>&1 | grep SENTINELA | head -10

# Dead Letter Queue (deve ser 0 em operacao normal)
curl http://IP_SUPREME:8000/v1/health
# campo: "queue_dead_letter_size": 0
```
