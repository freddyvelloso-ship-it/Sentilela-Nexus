from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from .config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def init_db():
    import pathlib
    migrations = [
        "/app/migrations/001_sentinela_schema.sql",
        "/app/migrations/002_participant_lifecycle.sql",
    ]
    async with engine.begin() as conn:
        for migration_file in migrations:
            p = pathlib.Path(migration_file)
            if not p.exists():
                continue
            migration_sql = p.read_text()
            statements = [s.strip() for s in migration_sql.split(";") if s.strip()]
            for stmt in statements:
                await conn.execute(text(stmt))
