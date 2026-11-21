from copy import deepcopy

from sqlalchemy import BigInteger, Integer, inspect as sa_inspect, event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import settings


def _set_sqlite_pragmas(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
    finally:
        cur.close()


#: Primary/foreign key type: bigint on PostgreSQL, plain INTEGER on SQLite so
#: that SQLite keeps its rowid autoincrement behaviour.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):

    def to_dict(self, exclude: set[str] | str | None = None) -> dict:
        if exclude is None:
            exclude = set()
        if isinstance(exclude, str):
            exclude = {exclude}
        loaded = sa_inspect(self).dict
        res = dict()
        for k in self.__mapper__.c.keys():
            if k in exclude or k not in loaded:
                continue
            res[k] = loaded[k]
        return deepcopy(res)


class DatabaseSessionManager:
    def __init__(self):
        self.engine: AsyncEngine | None = None
        self.session_maker = None

    async def init_db(self):
        self.engine = create_async_engine(settings.database_url)

        if self.engine.dialect.name == "sqlite":
            event.listen(self.engine.sync_engine, "connect", _set_sqlite_pragmas)

        # Call validate_invariants if present
        @event.listens_for(Session, "before_flush")
        def _validate(session, flush_context, instances):
            for obj in (*session.new, *session.dirty):
                if hasattr(obj, "validate_invariants"):
                    obj.validate_invariants()

        from app import models  # noqa: F401, Make sure all models are loaded

        self.session_maker = async_sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine, expire_on_commit=False
        )

    async def create_db(self):
        """Create missing tables. Non-destructive, does not alter existing ones."""
        from app import models  # noqa: F401, Make sure all models are loaded
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def reset_db(self):
        """Drop all tables and recreate them. Used for debug/test fresh starts."""
        from app import models  # noqa: F401, Make sure all models are loaded
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    @property
    def dialect_name(self) -> str:
        if self.engine is None:
            raise Exception("DatabaseSessionManager is not initialized")
        return self.engine.dialect.name

    async def close(self):
        if self.engine is None:
            raise Exception("DatabaseSessionManager is not initialized")
        await self.engine.dispose()


sessionmanager = DatabaseSessionManager()
