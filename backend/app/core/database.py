from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings

def get_async_db_url(url: str) -> str:
    if not url:
        return url
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

# For async database connections
engine = create_async_engine(
    get_async_db_url(settings.DATABASE_URL),
    echo=False,
    future=True,
    pool_pre_ping=True,
    # Resilience for free-tier DB blips (e.g. Aiven single-node stalls):
    # never let a request hang forever on a stalled connection.
    pool_recycle=1800,      # replace pooled connections older than 30 min
    pool_timeout=10,        # max wait for a free pool slot before erroring
    # Aiven free plan allows only 20 connections (3 reserved by the server ->
    # 17 usable, incl. Aiven's own background agents). One Render instance =
    # one process serving API + worker + Telegram poller, so 7 max keeps us
    # safely under the cap; bursts queue up to 10s instead of erroring.
    pool_size=3,
    max_overflow=4,
    connect_args={
        "timeout": 10,          # asyncpg connect timeout (seconds)
        "command_timeout": 60,  # per-query timeout (seconds)
    },
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
