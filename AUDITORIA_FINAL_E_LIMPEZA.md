# AUDITORIA FINAL E LIMPEZA — SUPREME V4/V5 + SENTINELA + IPED

**Data da auditoria:** 2026-06-07  
**Pacote analisado:** `SUPREME V4 - IPED (1).7z`  
**Caminho auditado como versão candidata:** `supreme_final/`  
**Status geral:** **aprovado apenas para teste local controlado; não aprovado para produção real sem correções críticas.**

---

## 1. Sumário executivo

O pacote contém uma versão consolidada em `supreme_final/`, além de versões legadas na raiz (`sentinela/`, `supreme-backend/`, `supreme-iped-integration/`) e documentos acadêmicos. A pasta `supreme_final/` é a única estrutura que parece representar o sistema final integrado.

A arquitetura principal está presente e coerente em alto nível:

```text
IPED / patch Java / proxy / watcher
        ↓
SUPREME Backend FastAPI
        ↓
Pipeline IEO, baseline, risco, PSI
        ↓
SENTINELA dashboard
        ↓
Exportação, War Room, Grafana, Prometheus, Loki
```

A base técnica evoluiu bastante. Há Docker Compose de produção/local, healthchecks, autenticação por bearer token no backend, autenticação JWT no Sentinela, migrações SQL, testes unitários mínimos, NGINX, observabilidade e scripts Windows de bootstrap.

Mesmo assim, encontrei quatro bloqueadores para produção real:

1. **Segredos reais estão versionados no pacote** em `.env`, `.env.production` e `certs/privkey.pem`.
2. **O fluxo psicométrico do launcher está quebrado ou incompleto**, porque as rotas de schedule e submissão exigem token, mas o launcher abre formulários sem token válido.
3. **A documentação principal ainda está inconsistente com as rotas reais** do Sentinela e do SUPREME.
4. **O pacote mistura versão final, versões antigas, caches, `.pyc`, `.pytest_cache`, certificados e arquivos sensíveis**, o que torna perigoso enviar o ZIP inteiro para dev ou produção.

---

## 2. O que foi validado

### 2.1 Estrutura encontrada

Dentro de `supreme_final/` existem os componentes esperados:

```text
supreme_final/
├── docker-compose.production.yml
├── docker-compose.local.yml
├── infra/
│   ├── nginx/
│   ├── prometheus/
│   ├── grafana/
│   └── loki/
├── scripts/
├── sentinela/
├── supreme-backend/
└── supreme-iped-integration/
```

### 2.2 Testes executados nesta auditoria

No ambiente de auditoria, Docker não estava disponível, então não foi possível subir containers. Foram executadas validações Python estáticas e testes unitários.

| Área | Comando/validação | Resultado |
|---|---|---|
| Backend SUPREME | `pytest -q` com `PYTHONPATH=.` e variáveis fake fortes | **4 passed** |
| SENTINELA | `pytest -q` com `PYTHONPATH=.` e variáveis fake fortes | **5 passed, 1 warning** |
| IPED integration | `pytest -q` | **sem testes encontrados** |
| Sintaxe Python | `python -m compileall` nos módulos principais | **ok** |
| Docker | `docker --version` | **não disponível no sandbox** |

### 2.3 Testes que ainda precisam ocorrer na sua máquina

```powershell
cd C:\Users\nunas\Downloads\SUPREME_V5_TESTE_LOCAL\supreme_final
.\SUBIR_LOCAL.ps1
```

Depois:

```powershell
docker compose -f docker-compose.production.yml -f docker-compose.local.yml ps
docker compose -f docker-compose.production.yml -f docker-compose.local.yml logs -f supreme-api
docker compose -f docker-compose.production.yml -f docker-compose.local.yml logs -f sentinela
docker compose -f docker-compose.production.yml -f docker-compose.local.yml logs -f supreme-iped-watcher
```

---

## 3. Achados críticos

### CRÍTICO 1 — Segredos reais dentro do pacote

Arquivos sensíveis encontrados:

```text
supreme_final/.env
supreme_final/supreme-backend/.env.production
supreme_final/sentinela/.env.production
supreme_final/certs/privkey.pem
supreme_final/certs/fullchain.pem
```

Risco:

- exposição de `API_SECRET_KEY`
- exposição de `API_INGEST_TOKEN`
- exposição de `SUPREME_SALT`
- exposição de `SECRET_KEY` do Sentinela
- exposição de chave privada TLS
- comprometimento da pseudonimização longitudinal se o mesmo salt for usado em produção

Correção obrigatória:

- remover esses arquivos do Git e do ZIP enviado ao dev
- rotacionar todos os segredos já usados
- gerar novo `SUPREME_SALT` antes de qualquer coleta real
- nunca reaproveitar os valores que vieram neste pacote

Status da limpeza que eu fiz:

- o pacote limpo gerado nesta auditoria remove `.env`, `.env.production`, `.pyc`, `.pytest_cache` e certificados reais
- os arquivos `.env.example` e `.env.production.example` foram preservados

---

### CRÍTICO 2 — Fluxo psicométrico do launcher não fecha ponta a ponta

O código real exige autenticação nas rotas psicométricas:

- `GET /v1/schedule/{id_hash}` está dentro de `router = APIRouter(dependencies=[Depends(require_api_token)])`
- `POST /v1/psychometric/submit` exige `require_ingest_token`

Mas o launcher `supreme-iped-integration/launcher/launch_iped.ps1` chama:

```powershell
Invoke-RestMethod -Uri "$BackendUrl/v1/schedule/$idHash" -Method GET
```

sem header `Authorization`.

E abre formulários assim:

```powershell
/forms/panas?user=$idHash&backend=$BackendUrl
```

sem `token=`.

Os HTMLs dos formulários tentam enviar:

```javascript
Authorization: 'Bearer ' + token
```

Como o token não é fornecido, a submissão tende a falhar com `Bearer token ausente` ou `Token inválido`.

Impacto:

- o IPED pode abrir
- o watcher/proxy podem enviar eventos
- mas os formulários psicométricos provavelmente não submetem dados no fluxo real do perito

Correção recomendada:

Opção segura:

1. Criar um endpoint específico para emissão de token curto de formulário, com escopo limitado a `id_hash`, `instrument`, `expiração` e `submit only`.
2. O launcher chama o endpoint com `API_INGEST_TOKEN` ou outro segredo local seguro.
3. O formulário recebe `token` curto na URL.
4. `POST /v1/psychometric/submit` valida esse token de formulário, não o token global de ingestão.

Correção rápida para teste local:

- passar `API_INGEST_TOKEN` como query string no launcher, mas isso **não deve ser solução de produção**, porque expõe token global no histórico do navegador.

---

### CRÍTICO 3 — Documentação principal não bate com as rotas reais

`README_INSTALACAO.md` ainda orienta chamadas como:

```bash
curl -X POST http://localhost:8001/auth/bootstrap
```

Mas o código real do Sentinela usa:

```text
/api/auth/bootstrap
```

com header:

```text
X-Bootstrap-Token: <token>
```

Também há documentação dizendo:

```bash
curl http://localhost:8000/v1/health
```

mas `/v1/health` está protegido pelo token do backend. O health público real é:

```text
/health
```

Impacto:

- o dev pode seguir o README e achar que o sistema quebrou
- o deploy pode ser validado por comandos errados
- automação de smoke test pode divergir da documentação

Correção:

- fazer do `docs/HANDOFF_FINAL_PRODUCAO_DEV.md` o documento principal
- reescrever `README_INSTALACAO.md` com as rotas reais
- separar `TESTE_LOCAL.md`, `DEPLOY_PRODUCAO.md` e `CHECKLIST_GO_LIVE.md`

---

### CRÍTICO 4 — O ZIP original não deve ser enviado inteiro ao dev

O pacote original mistura:

- versão final em `supreme_final/`
- versão antiga na raiz
- documentos `.docx`
- ZIP interno `SUPREME_V4_DEPLOY.zip`
- `.env` reais
- certificados reais
- caches Python
- artefatos de teste

Correção:

- enviar apenas o pacote limpo `SUPREME_FINAL_LIMPO_PARA_CODEX_DEV.zip`
- manter o ZIP original como arquivo histórico privado, não como base de produção

---

## 4. Achados altos

### ALTO 1 — Scripts locais imprimem segredos no terminal

`SUBIR_LOCAL.ps1` imprime no final:

```powershell
API_INGEST_TOKEN
API_SECRET_KEY
Grafana password
```

Para teste local isso ajuda. Para produção ou handoff externo é inadequado.

Correção:

- manter esse comportamento apenas em script local
- criar `SUBIR_PRODUCAO.ps1` ou `DEPLOY_PRODUCAO.sh` sem impressão de segredos
- escrever segredos apenas em `.env` local protegido

---

### ALTO 2 — Launcher PowerShell tem salt dev fixo

`supreme-iped-integration/launcher/launch_iped.ps1` define:

```powershell
$env:SUPREME_SALT = "dev-salt-local-troque-em-producao"
```

Impacto:

- risco de pseudonimização fraca se alguém usar esse launcher sem ajustar
- risco de inconsistência entre hash do launcher, watcher e backend

Correção:

- remover valor default em produção
- fazer o launcher falhar se `SUPREME_SALT` não estiver definido
- carregar o salt de um arquivo local protegido ou variável de ambiente de máquina

---

### ALTO 3 — Proxy loga identificador bruto do usuário

`supreme-proxy/proxy.py` registra:

```python
user={raw_user}
```

Impacto:

- o banco recebe hash, mas o log do proxy pode conter ID funcional bruto
- isso contraria o princípio de pseudonimização operacional

Correção:

- logar apenas prefixo do hash, por exemplo `id_hash[:8]`
- nunca logar `raw_user`

---

### ALTO 4 — Integração IPED ainda carece de teste automatizado

Em `supreme-iped-integration/` não há testes automatizados ativos. O teste local retornou:

```text
no tests ran
```

Correção:

Criar pelo menos:

- teste de `pseudonymize()` com salt fixo
- teste de `build_supreme_event()` a partir de NDJSON sintético
- teste de `compute_event_hash()` garantindo deduplicação com duração tardia
- teste de `proxy.classify_request()`
- teste de ingestão fake com `requests_mock` ou `httpx.MockTransport`

---

## 5. Achados médios

| Severidade | Achado | Arquivo/local | Correção |
|---|---|---|---|
| Média | Versão aparece como V4 em muitos lugares e V5 em scripts/handoff | README, scripts, compose | Padronizar nome comercial e técnico |
| Média | Backend usa dependências sem pinagem rígida no Dockerfile | `supreme-backend/Dockerfile` | Usar lock/constraints para produção |
| Média | `docker compose deploy.replicas` pode ser ignorado fora de Swarm | `docker-compose.production.yml` | Usar `docker compose up --scale supreme-worker=N` ou documentar limitação |
| Média | `API_SECRET_KEY` protege métricas e analytics, mas não há usuários/roles no backend | `security.py` | Aceitável para MVP, mas documentar como token administrativo |
| Média | O patch Java é descrito, mas precisa ser validado contra a tag real do IPED da PF | `iped-patch/BUILD.md` | Teste em IPED real controlado antes de produção |
| Média | Certificado autoassinado é bom para local, não para produção | `certs/` e `SUBIR_LOCAL.ps1` | Produção deve usar certificado emitido corretamente |
| Média | Há documentos antigos e relatórios misturados com produto | raiz do pacote | Separar `/docs/research` de `/docs/deploy` |

---

## 6. O que está bom

### 6.1 Arquitetura

A separação entre `supreme-backend`, `sentinela` e `supreme-iped-integration` está correta. O fluxo IPED → SUPREME → SENTINELA está implementado em código, não apenas documentado.

### 6.2 Segurança básica

Há melhorias reais:

- bearer token no backend
- JWT no Sentinela
- bcrypt para senha
- rejeição de placeholders em produção
- CORS bloqueia `*` em produção
- `.dockerignore` remove `.env` e `.pyc` do build context
- NGINX tem headers básicos
- healthchecks em containers principais

### 6.3 Pipeline analítico

O pipeline possui estrutura funcional:

- ingestão de eventos
- deduplicação via `event_hash`
- fila RQ
- cálculo de janelas
- baseline
- IEO
- flags
- push ao Sentinela
- PSI psicométrico
- exportação para R

### 6.4 Testes mínimos

Os testes existentes passam. Eles cobrem:

- segurança de token de ingestão
- identidade do hash de evento ignorando duração tardia
- hashing bcrypt no Sentinela
- rotas de ingestão no Sentinela
- semântica de API key

---

## 7. Limpeza aplicada nesta entrega

Foi criado um pacote limpo contendo apenas `supreme_final/` sanitizado.

Removido:

```text
.env
.env.production
certs/*.pem
__pycache__/
*.pyc
.pytest_cache/
```

Preservado:

```text
.env.example
.env.production.example
Dockerfiles
Docker Compose
migrações SQL
scripts de instalação
código fonte
testes
infra NGINX, Prometheus, Grafana e Loki
_patch_build/supreme-audit-patch.jar
```

Também foi adicionado no pacote limpo:

```text
AUDITORIA_FINAL_E_LIMPEZA.md
.gitignore
certs/README.md
```

---

## 8. Checklist antes de enviar para o Codex

1. Subir o pacote limpo em um repositório GitHub privado.
2. Criar branch:

```bash
git checkout -b audit/final-cleanup
```

3. Fazer commit inicial:

```bash
git add .
git commit -m "chore: import sanitized supreme final package"
```

4. Pedir ao Codex a correção controlada dos bloqueadores.

Prompt recomendado:

```text
Você é o engenheiro responsável pela correção final do SUPREME V4/V5 + SENTINELA + IPED Integration antes de teste real.

Leia AUDITORIA_FINAL_E_LIMPEZA.md e corrija apenas os bloqueadores críticos e altos.

Prioridade obrigatória:
1. Corrigir o fluxo psicométrico launcher -> schedule -> formulário -> submit sem expor token global em URL.
2. Atualizar README_INSTALACAO.md para refletir as rotas reais.
3. Remover qualquer impressão de segredos em scripts que não sejam explicitamente locais.
4. Remover log de identificador bruto no proxy.
5. Criar testes para supreme-iped-integration.
6. Garantir que nenhum .env, .env.production, certificado privado, .pyc ou .pytest_cache volte ao repositório.

Não altere a fórmula da IEO.
Não altere a lógica científica.
Não reescreva a arquitetura.
Não remova o watcher nem o proxy.
Não substitua o sistema por outro produto.

Ao final, gere:
- docs/RELATORIO_CORRECOES_CODEX.md
- docs/CHECKLIST_GO_LIVE.md
- testes passando em backend, sentinela e iped integration
```

---

## 9. Status final da auditoria

| Critério | Status |
|---|---|
| Estrutura candidata identificada | **ok** |
| Código backend compila | **ok** |
| Código Sentinela compila | **ok** |
| Testes backend | **ok: 4 passed** |
| Testes Sentinela | **ok: 5 passed** |
| Testes IPED integration | **pendente: não existem testes ativos** |
| Docker local | **não validado neste ambiente** |
| Segredos removidos do pacote limpo | **ok** |
| Pronto para Codex | **sim, usando o pacote limpo** |
| Pronto para produção real | **não** |

Conclusão: o sistema está em bom ponto para coworking com Codex e teste local controlado. Para produção real com peritos e IPED real, primeiro corrija os bloqueadores de autenticação psicométrica, documentação, logs sensíveis e rotação de segredos.
