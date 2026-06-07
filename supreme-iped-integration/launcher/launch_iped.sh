#!/usr/bin/env bash
# =============================================================================
# launch_iped.sh — Wrapper de inicialização do IPED com integração SUPREME V4
#
# Uso:
#   chmod +x launch_iped.sh
#   ./launch_iped.sh [argumentos normais do IPED]
#
# O script:
#   1. Solicita o ID funcional do perito (não nome real)
#   2. Define as variáveis de ambiente necessárias para o SupremeAuditLogger
#   3. Inicia o supreme-proxy e o supreme-watcher em background
#   4. Lança o IPED com o classpath do patch
#   5. Ao encerrar o IPED, para os serviços em background graciosamente
# =============================================================================

set -euo pipefail

# ── Configurações — ajustar por instituição ────────────────────────────────

IPED_JAR="${IPED_JAR:-/opt/iped/iped.jar}"
IPED_PATCH_JAR="${IPED_PATCH_JAR:-/opt/iped/plugins/supreme-audit-patch.jar}"
SUPREME_PROXY_SCRIPT="${SUPREME_PROXY_SCRIPT:-/opt/supreme/supreme-proxy/proxy.py}"
SUPREME_WATCHER_SCRIPT="${SUPREME_WATCHER_SCRIPT:-/opt/supreme/supreme-watcher/watcher.py}"

# URL da Web API do IPED (usada internamente pelo IPED)
export IPED_API_URL="${IPED_API_URL:-http://localhost:1234}"
# Porta onde o proxy ficará ouvindo (o perito acessa esta porta)
export PROXY_PORT="${PROXY_PORT:-8081}"
# URL do backend SUPREME
export SUPREME_API_URL="${SUPREME_API_URL:-http://supreme.api.local/v1}"
# Token JWT do SUPREME (idealmente carregado de cofre)
export SUPREME_API_TOKEN="${SUPREME_API_TOKEN:-}"
# Arquivo de log de auditoria compartilhado entre Java e Python
export SUPREME_AUDIT_LOG="${SUPREME_AUDIT_LOG:-${HOME}/supreme_audit.ndjson}"
# Intervalo de polling do watcher (segundos)
export WATCHER_POLL_SECS="${WATCHER_POLL_SECS:-30}"

# SALT de pseudonimização — Em produção, carregar de cofre criptográfico.
# NUNCA armazenar o salt em backup automatizado ou repositório.
if [[ -z "${SUPREME_SALT:-}" ]]; then
    echo "AVISO: SUPREME_SALT não definido. Usando valor padrão inseguro."
    echo "Em produção: export SUPREME_SALT=\$(cat /vault/supreme.salt)"
    export SUPREME_SALT="DEFINIR_SALT_EM_PRODUCAO"
fi

# ── Coleta do ID funcional do perito ──────────────────────────────────────

echo "============================================================"
echo "  SUPREME V4 — Sistema de Telemetria de Exposição Ocupacional"
echo "============================================================"
echo ""
echo "AVISO: Esta sessão será monitorada para fins de pesquisa científica"
echo "sobre exposição ocupacional. Dados são pseudonimizados e usados"
echo "exclusivamente para fins do estudo aprovado pelo CEP."
echo ""

while true; do
    read -rp "Digite seu ID funcional (ex: perito_021): " user_id
    if [[ -n "$user_id" && "$user_id" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        break
    fi
    echo "ID inválido. Use apenas letras, números, _ ou -."
done

export SUPREME_USER_ID="$user_id"
echo ""
echo "Sessão iniciada para: $user_id (será pseudonimizado)"
echo "Arquivo de auditoria: $SUPREME_AUDIT_LOG"
echo ""

# ── Iniciar supreme-proxy em background ───────────────────────────────────

echo "[1/3] Iniciando supreme-proxy na porta $PROXY_PORT..."

PROXY_LOG="${HOME}/supreme_proxy.log"
python3 "$SUPREME_PROXY_SCRIPT" > "$PROXY_LOG" 2>&1 &
PROXY_PID=$!
echo "      PID do proxy: $PROXY_PID (log: $PROXY_LOG)"

# Aguardar proxy subir
sleep 2
if ! kill -0 "$PROXY_PID" 2>/dev/null; then
    echo "ERRO: supreme-proxy falhou ao iniciar. Verifique $PROXY_LOG"
    exit 1
fi

# ── Iniciar supreme-watcher em background ─────────────────────────────────

echo "[2/3] Iniciando supreme-watcher..."

WATCHER_LOG="${HOME}/supreme_watcher.log"
python3 "$SUPREME_WATCHER_SCRIPT" > "$WATCHER_LOG" 2>&1 &
WATCHER_PID=$!
echo "      PID do watcher: $WATCHER_PID (log: $WATCHER_LOG)"

# ── Lançar IPED ───────────────────────────────────────────────────────────

echo "[3/3] Iniciando IPED..."
echo ""
echo "NOTA: Configure a interface do IPED para usar a API via porta $PROXY_PORT"
echo "      em vez da porta padrão 1234."
echo ""

# Adicionar o patch ao classpath do IPED
# O patch JAR contém SupremeAuditLogger.class compilado
IPED_CP="${IPED_JAR}"
if [[ -f "$IPED_PATCH_JAR" ]]; then
    IPED_CP="${IPED_PATCH_JAR}:${IPED_JAR}"
fi

java \
    -cp "$IPED_CP" \
    -DSUPREME_AUDIT_LOG="$SUPREME_AUDIT_LOG" \
    -DSUPREME_USER_ID="$SUPREME_USER_ID" \
    iped.app.bootstrap.Bootstrap "$@"

IPED_EXIT=$?

# ── Encerrar serviços em background ───────────────────────────────────────

echo ""
echo "IPED encerrado (código: $IPED_EXIT). Aguardando processamento final..."
sleep "$WATCHER_POLL_SECS"

echo "Encerrando supreme-proxy (PID $PROXY_PID)..."
kill "$PROXY_PID" 2>/dev/null || true

echo "Encerrando supreme-watcher (PID $WATCHER_PID)..."
kill "$WATCHER_PID" 2>/dev/null || true

echo "Sessão SUPREME encerrada para: $user_id"
echo "Arquivo de auditoria: $SUPREME_AUDIT_LOG"

exit $IPED_EXIT
