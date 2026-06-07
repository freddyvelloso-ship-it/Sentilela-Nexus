# Correção e validação do SENTINELA — SUPREME V5

## Objetivo
Resolver a limitação apontada na validação anterior: o SENTINELA precisava ser testado de forma explícita, não apenas compilado ou assumido como válido por declaração de dependências.

## Problemas encontrados

1. **Dependência bcrypt sem pin explícito**
   - `passlib==1.7.4` pode instalar `bcrypt>=5` em ambientes novos.
   - `bcrypt 5` altera comportamento de senha longa e quebra hashing via Passlib em runtime.
   - Correção: adicionado `bcrypt==4.0.1` em `sentinela/requirements.txt`.

2. **Testes do SENTINELA exigiam variáveis obrigatórias sem fixture**
   - `SECRET_KEY` e `SUPREME_API_KEY` são obrigatórias por design fail-closed.
   - Em CI/teste local, isso fazia o import de `src.app.auth` falhar antes dos testes.
   - Correção: criado `sentinela/tests/conftest.py` com variáveis seguras apenas para ambiente de teste.

3. **Arquivo `sentinela/src/app/api/ingest.py` terminava incompleto**
   - A rota `/api/v1/ingest/ieo` não retornava resposta final explícita.
   - A rota `/api/v1/ingest/psychometric`, esperada pelo `push_psychometric()` do SUPREME, não estava registrada no fim do arquivo.
   - Correção: finalização de `receive_ieo()` e criação de `receive_psychometric()`.

4. **`docker-compose.production.yml` estava com YAML inválido**
   - O healthcheck do `supreme-api` tinha aspas quebradas dentro do comando Python inline.
   - Correção: comando reescrito com quoting YAML válido.

5. **SENTINELA sem healthcheck no compose de produção**
   - Correção: adicionado healthcheck HTTP para `http://localhost:8001/health`.

## Testes adicionados no SENTINELA

- `test_password_hashing.py`
  - Confirma hashing bcrypt.
  - Confirma verificação correta de senha válida e inválida.

- `test_auth_token.py`
  - Confirma que o JWT emitido contém `sub`, `role` e `jti`.
  - Garante revogabilidade futura por identificador de token.

- `test_ingest_security_and_routes.py`
  - Confirma que `_check_api_key()` aceita chave válida e rejeita chave inválida.
  - Confirma que o router expõe `/api/v1/ingest/ieo` e `/api/v1/ingest/psychometric`.
  - Confirma presença de `COALESCE` nos UPSERTs críticos para evitar sobrescrita por `NULL`.

## Validação executada

### SENTINELA

```bash
cd sentinela
SECRET_KEY=abcdefghijklmnopqrstuvwxyz1234567890 \
SUPREME_API_KEY=ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890 \
ENVIRONMENT=test \
python -m pytest -q
```

Resultado:

```text
5 passed, 1 warning
```

### Compilação SENTINELA

```bash
python -m compileall -q sentinela/src sentinela/tests
```

Resultado: OK.

### Backend SUPREME

```bash
cd supreme-backend
python -m pytest -q
```

Resultado:

```text
4 passed
```

### Compilação Backend

```bash
python -m compileall -q supreme-backend/src supreme-backend/tests
```

Resultado: OK.

### Compose de produção

```bash
python - <<'PY'
import yaml
with open('docker-compose.production.yml') as f:
    yaml.safe_load(f)
print('compose yaml ok')
PY
```

Resultado:

```text
compose yaml ok
```

## Observação operacional
O Docker não está disponível neste sandbox, portanto não foi possível executar `docker compose up --build`. A validação feita aqui cobre sintaxe Python, testes unitários do SUPREME, testes unitários do SENTINELA, rotas críticas do SENTINELA e validade estrutural do YAML de produção.
