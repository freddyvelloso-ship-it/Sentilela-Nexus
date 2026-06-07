# SENTINELA — Comandos operacionais
# Uso: make <comando>

.PHONY: up down restart logs build shell backup restore create-user status

# ── Dev / Prod ────────────────────────────────────────────────────────────────

up:
	docker compose up -d --build

down:
	docker compose down

restart:
	docker compose restart api

logs:
	docker compose logs -f api

build:
	docker compose build api

status:
	docker compose ps
	@echo ""
	@curl -s http://localhost:8001/health | python3 -m json.tool 2>/dev/null || echo "API nao responde"

shell:
	docker compose exec api bash

db-shell:
	docker compose exec db psql -U sentinela sentinela

# ── Usuarios ──────────────────────────────────────────────────────────────────

create-user:
	@read -p "Email: " EMAIL; \
	 read -sp "Senha: " PASS; echo; \
	 read -p "Role (master/pibic): " ROLE; \
	 TOKEN=$$(grep '^SECRET_KEY' .env | cut -d= -f2); \
	 echo "Use o endpoint /api/auth/users apos autenticar como master."

bootstrap:
	@BOOT=$$(grep BOOTSTRAP_TOKEN .env 2>/dev/null | cut -d= -f2); \
	 if [ -z "$$BOOT" ]; then echo "BOOTSTRAP_TOKEN nao definido no .env"; exit 1; fi; \
	 read -p "Email do master: " EMAIL; \
	 read -sp "Senha: " PASS; echo; \
	 curl -s -X POST http://localhost:8001/api/auth/bootstrap \
	   -H "Content-Type: application/json" \
	   -H "X-Bootstrap-Token: $$BOOT" \
	   -d "{\"email\":\"$$EMAIL\",\"password\":\"$$PASS\"}" | python3 -m json.tool; \
	 echo ""; \
	 echo "Remova o BOOTSTRAP_TOKEN do .env e reinicie: make restart"

disable-bootstrap:
	sed -i '/^BOOTSTRAP_TOKEN/d' .env
	$(MAKE) restart
	@echo "Bootstrap desabilitado."

# ── Backup / Restore ──────────────────────────────────────────────────────────

backup:
	@mkdir -p backups
	@FILENAME="backups/sentinela_$$(date +%Y%m%d_%H%M%S).sql.gz"; \
	 docker compose exec -T db pg_dump -U sentinela sentinela | gzip > "$$FILENAME"; \
	 echo "Backup salvo: $$FILENAME"

restore:
	@read -p "Arquivo de backup (.sql.gz): " FILE; \
	 gunzip -c "$$FILE" | docker compose exec -T db psql -U sentinela sentinela; \
	 echo "Restore concluido."

# ── Export CSV ────────────────────────────────────────────────────────────────

export-csv:
	@read -p "Token JWT (obtenha via login): " JWT; \
	 curl -s -H "Authorization: Bearer $$JWT" \
	   "http://localhost:8001/api/export/csv" \
	   -o "sentinela_export_$$(date +%Y%m%d).csv"; \
	 echo "CSV salvo: sentinela_export_$$(date +%Y%m%d).csv"
