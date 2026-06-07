# SUPREME V4 — Integração com IPED

Camada de integração entre o IPED Digital Forensic Tool e o backend SUPREME V4.
Captura eventos de atividade do perito com **duration_seconds preciso** usando
a combinação de um patch Java (B) e um proxy HTTP (C).

---

## Arquitetura

```
[Perito digita ID no launcher]
         ↓
[IPED lança com SupremeAuditLogger no classpath]
         ↓
[Perito trabalha na UI do IPED]
         │
         ├─ UI events → SupremeAuditLogger.java → supreme_audit.ndjson
         │              (open_time / close_time por item)
         │
         └─ API calls → supreme-proxy/proxy.py  → SUPREME /events/ingest
                        (intercepta /content, /thumb, /text)
                              ↓ lê
                        supreme_audit.ndjson (duration_seconds real)

[supreme-watcher/watcher.py] → lê eventos "close" do ndjson
                             → envia eventos com duração precisa
                             → SUPREME /events/ingest
```

---

## Componentes

| Arquivo | Linguagem | Função |
|---------|-----------|--------|
| `iped-patch/src/.../SupremeAuditLogger.java` | Java | Hook na UI do IPED — registra open/close |
| `iped-patch/ResultTableListener.patch` | Diff | Instruções de instalação do patch |
| `supreme-proxy/proxy.py` | Python | Intercepta API do IPED em tempo real |
| `supreme-watcher/watcher.py` | Python | Lê NDJSON com duração precisa e envia ao SUPREME |
| `launcher/launch_iped.sh` | Bash | Wrapper Linux/Mac |
| `launcher/launch_iped.bat` | Batch | Wrapper Windows |

---

## Dados capturados por evento

| Campo SUPREME | Fonte | Precisão |
|---|---|---|
| `timestamp` | SupremeAuditLogger (open_ts) | Milissegundo |
| `event_type` | Derivado do mediaType + evento Java | Alta |
| `media_type` | mediaType do item (MIME → image/video/preview) | Alta |
| `severity` | `nudityClass` (IPED DIETask, 1-5 = COPINE direto) | Alta |
| `duration_seconds` | close_ts − open_ts do SupremeAuditLogger | Milissegundo |
| `user_identifier` | ID funcional coletado no launcher → SHA-256 + salt | Pseudonimizado |
| `source_tool` | Fixo: `"iped"` | — |

---

## Instalação

### 1. Dependências Python

```bash
pip install -r requirements.txt
```

### 2. Compilar o patch Java

```bash
cd iped-patch
javac -cp /path/to/iped.jar:lucene-core-9.2.0.jar \
      src/main/java/iped/app/ui/SupremeAuditLogger.java \
      -d out/

jar cf supreme-audit-patch.jar -C out/ .
cp supreme-audit-patch.jar /opt/iped/plugins/
```

### 3. Aplicar o patch no ResultTableListener

Seguir as instruções em `iped-patch/ResultTableListener.patch`.
As modificações são mínimas: 2 chamadas de método e 1 bloco try/catch.

Alternativa sem recompilar o IPED: colocar o JAR do patch no diretório
`plugins/` do IPED e substituir apenas `ResultTableListener.class` no
`iped-app.jar` com a versão modificada.

### 4. Configurar variáveis de ambiente

```bash
export SUPREME_SALT="$(cat /cofre/supreme.salt)"   # OFFLINE em produção
export SUPREME_API_URL="https://supreme.api.local/v1"
export SUPREME_API_TOKEN="eyJ..."
export IPED_API_URL="http://localhost:1234"
export PROXY_PORT="8081"
```

### 5. Lançar

**Linux/Mac:**
```bash
./launcher/launch_iped.sh /evidencias/caso_001.E01 -o /output/caso_001
```

**Windows:**
```bat
launcher\launch_iped.bat C:\evidencias\caso_001.E01 -o C:\output\caso_001
```

---

## Segurança

- O **salt** de pseudonimização nunca é armazenado em banco de dados ou backup automatizado
- O **user_identifier real** nunca é enviado ao SUPREME — apenas o SHA-256(id + salt)
- O proxy usa apenas **leitura** da API do IPED (não modifica evidências)
- O SupremeAuditLogger usa apenas `doc.get()` (leitura do índice Lucene — somente leitura)
- O arquivo `supreme_audit.ndjson` contém user_ids reais — proteger com permissões de SO

---

## Fluxo de dados completo

```
IPED (porta 1234) ←→ supreme-proxy (porta 8081) ←→ Perito

IPED UI → SupremeAuditLogger → supreme_audit.ndjson
                                       ↓
                              supreme-watcher (polling 30s)
                                       ↓
                              SUPREME /v1/events/ingest
                                       ↓
                              events_raw (PostgreSQL)
                                       ↓
                    Session Builder → Metrics Engine → IEO Engine
                                       ↓
                              ieo_logs + risk_flags
```
