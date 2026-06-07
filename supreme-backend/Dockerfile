FROM python:3.11-slim

WORKDIR /app

# Dependências do sistema (libpq para asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências primeiro (cache de layer)
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.111" \
    "uvicorn[standard]>=0.29" \
    "pydantic>=2.7" \
    "pydantic-settings>=2.3" \
    "sqlalchemy[asyncio]>=2.0" \
    "asyncpg>=0.29" \
    "rq>=1.16" \
    "redis>=5.0" \
    "python-dotenv>=1.0" \
    "httpx>=0.27" \
    "prometheus-client>=0.20"

# Copiar código
COPY . .

RUN useradd --create-home --shell /usr/sbin/nologin appuser && chown -R appuser:appuser /app
USER appuser
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
