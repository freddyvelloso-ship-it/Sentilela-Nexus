import asyncio, os
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

engine = create_async_engine(os.environ['DATABASE_URL'])
Session = sessionmaker(engine, class_=AsyncSession)
ctx = CryptContext(schemes=['bcrypt'], deprecated='auto')

async def main():
    h = ctx.hash('SenhaForte123!')
    async with Session() as db:
        await db.execute(text(
            'INSERT INTO sentinela_users (email, password_hash, role) VALUES (:e,:h,:r) '
            'ON CONFLICT (email) DO UPDATE SET password_hash=EXCLUDED.password_hash, role=EXCLUDED.role'
        ), {'e': 'admin@local.test', 'h': h, 'r': 'master'})
        await db.execute(text(
            "INSERT INTO system_config(key,value) VALUES('bootstrap_used','true') "
            "ON CONFLICT(key) DO UPDATE SET value='true'"
        ))
        await db.commit()
    print('OK — admin@local.test / SenhaForte123!')

asyncio.run(main())
