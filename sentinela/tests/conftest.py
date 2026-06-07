import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-abcdefghijklmnopqrstuvwxyz-1234567890")
os.environ.setdefault("SUPREME_API_KEY", "test-supreme-api-key-abcdefghijklmnopqrstuvwxyz-1234567890")
os.environ.setdefault("BOOTSTRAP_TOKEN", "test-bootstrap-token-abcdefghijklmnopqrstuvwxyz")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sentinela:sentinela@localhost:5432/sentinela_test")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost")
