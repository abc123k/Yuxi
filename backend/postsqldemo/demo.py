import asyncio
import sys
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 必须放在最顶层！
if sys.platform == "win32":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from postsqldemo.mapper.user import User


def create_engine_and_session():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:WD500ASUS@192.168.31.75:5432/inose",
        echo=True,
        pool_size=10,
        max_overflow=20,
    )
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, AsyncSessionLocal


async def query(session_factory, user_id: int):
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


async def init_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(User.metadata.create_all)


async def main():
    engine, AsyncSessionLocal = create_engine_and_session()
    try:
        await init_db(engine)
        result = await query(AsyncSessionLocal, 1)
        print(result.username)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
