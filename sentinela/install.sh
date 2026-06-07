#!/usr/bin/env bash
# =============================================================================
# SENTINELA — Script de instalacao para VPS Ubuntu 22.04 / Debian 12
# Uso: bash install.sh [SEU_DOMINIO.com]
# =============================================================================
set -euo pipefail

DOMAIN="${1:-}"
APP_DIR="/opt/sentinela"
APP_USER="sentinela"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERR]${NC}   $*"; exit 1; }

[[ $EUID -ne 0 ]] && error "Execute como root: sudo bash install.sh"

# ── 1. Atualizar sistema ──────────────────────────────────────────────────────
info "Atualizando pacotes..."
apt-get update -qq && apt-get upgrade -y -qq

# ── 2. Instalar Docker ────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    info "Instalando Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
else
    info "Docker ja instalado: $(docker --version)"
fi

# ── 3. Instalar Nginx (para HTTPS) ────────────────────────────────────────────
if ! command -v nginx &>/dev/null; then
    info "Instalando Nginx..."
    apt-get install -y -qq nginx
    systemctl enable --now nginx
fi

# ── 4. Criar usuario de sistema ───────────────────────────────────────────────
if ! id "$APP_USER" &>/dev/null; then
    info "Criando usuario $APP_USER..."
    useradd -r -s /bin/false -d "$APP_DIR" "$APP_USER"
    usermod -aG docker "$APP_USER"
fi

# ── 5. Criar diretorio da aplicacao ───────────────────────────────────────────
info "Criando $APP_DIR..."
mkdir -p "$APP_DIR"
chown "$APP_USER":"$APP_USER" "$APP_DIR"

# ── 6. Copiar arquivos (assume que o script esta dentro da pasta sentinela/) ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
info "Copiando arquivos de $SCRIPT_DIR para $APP_DIR..."
rsync -a --exclude='.env' --exclude='__pycache__' --exclude='*.pyc' \
    "$SCRIPT_DIR/" "$APP_DIR/"
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

# ── 7. Gerar .env se nao existir ──────────────────────────────────────────────
if [[ ! -f "$APP_DIR/.env" ]]; then
    info "Gerando .env com segredos aleatorios..."
    PG_PASS=$(openssl rand -hex 20)
    SECRET=$(openssl rand -hex 32)
    API_KEY=$(openssl rand -hex 32)
    BOOT_TOKEN=$(openssl rand -hex 16)

    cat > "$APP_DIR/.env" <<EOF
POSTGRES_PASSWORD=$PG_PASS
DATABASE_URL=postgresql+asyncpg://sentinela:${PG_PASS}@db:5432/sentinela
SECRET_KEY=$SECRET
SUPREME_API_KEY=$API_KEY
BOOTSTRAP_TOKEN=$BOOT_TOKEN
ALGORITHM=HS256
EOF
    chmod 600 "$APP_DIR/.env"
    chown "$APP_USER":"$APP_USER" "$APP_DIR/.env"

    echo ""
    warn "======================================================"
    warn "  .env gerado em $APP_DIR/.env"
    warn "  SUPREME_API_KEY = $API_KEY"
    warn "  BOOTSTRAP_TOKEN = $BOOT_TOKEN"
    warn "  Configure SUPREME_API_KEY no .env do SUPREME V4!"
    warn "  Guarde estes valores em lugar seguro."
    warn "======================================================"
    echo ""
else
    info ".env ja existe, mantendo."
fi

# ── 8. Nginx ──────────────────────────────────────────────────────────────────
if [[ -n "$DOMAIN" ]]; then
    info "Configurando Nginx para $DOMAIN..."
    sed "s/SEU_DOMINIO.com/$DOMAIN/g" "$APP_DIR/nginx/sentinela.conf" \
        > "/etc/nginx/sites-available/sentinela"
    ln -sf /etc/nginx/sites-available/sentinela /etc/nginx/sites-enabled/sentinela
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl reload nginx

    # Certbot
    if ! command -v certbot &>/dev/null; then
        info "Instalando Certbot..."
        apt-get install -y -qq certbot python3-certbot-nginx
    fi
    info "Obtendo certificado SSL para $DOMAIN..."
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
        --email "admin@$DOMAIN" --redirect || warn "Certbot falhou — configure manualmente."
else
    warn "Dominio nao fornecido — Nginx nao configurado. Use: bash install.sh meudominio.com"
fi

# ── 9. Subir servicos ──────────────────────────────────────────────────────────
info "Subindo SENTINELA com Docker Compose..."
cd "$APP_DIR"
docker compose pull --quiet 2>/dev/null || true
docker compose up -d --build

# ── 10. Aguardar saude ────────────────────────────────────────────────────────
info "Aguardando API ficar pronta..."
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8001/health &>/dev/null; then
        info "API respondendo!"
        break
    fi
    sleep 2
done

# ── 11. Instrucoes finais ─────────────────────────────────────────────────────
BOOT_TOKEN_VAL=$(grep BOOTSTRAP_TOKEN "$APP_DIR/.env" | cut -d= -f2)
BASE_URL="${DOMAIN:+https://$DOMAIN}"
BASE_URL="${BASE_URL:-http://$(curl -s ifconfig.me):8001}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  SENTINELA instalado com sucesso!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  Dashboard: $BASE_URL"
echo ""
echo "  Criar usuario master (execute UMA vez):"
echo ""
echo "  curl -X POST $BASE_URL/api/auth/bootstrap \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -H 'X-Bootstrap-Token: $BOOT_TOKEN_VAL' \\"
echo "    -d '{\"email\":\"seu@email.com\",\"password\":\"suasenha\"}'"
echo ""
echo "  Apos criar o master, remova BOOTSTRAP_TOKEN do .env:"
echo "  sed -i '/BOOTSTRAP_TOKEN/d' $APP_DIR/.env"
echo "  docker compose restart api"
echo ""
echo "  Logs: cd $APP_DIR && docker compose logs -f api"
echo ""
