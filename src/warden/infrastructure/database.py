from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from warden.adapters.outbound.persistence.models import Base


def build_engine(database_url: str) -> AsyncEngine:
    is_memory = ":memory:" in database_url
    kwargs: dict = {"echo": False}
    if not is_memory:
        kwargs["pool_size"] = 1
        kwargs["max_overflow"] = 0
    return create_async_engine(database_url, **kwargs)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
        await conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
