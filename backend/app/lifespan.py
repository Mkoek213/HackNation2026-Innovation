import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database.database import sessionmanager
from app.models import UserRole
from app.modules.knowledge import warm_up as warm_up_knowledge
from app.schemas.user import UserCreate

logger = logging.getLogger('uvicorn.error')


async def _ensure_admin() -> None:
    """Creates the bootstrap admin from ADMIN_USERNAME / ADMIN_PASSWORD when
    that username does not exist yet. Never touches an existing account."""
    if not settings.admin_username or not settings.admin_password:
        return
    from app.repos.user_repo import UserRepo
    async with sessionmanager.session_maker() as db:
        repo = UserRepo(db)
        if await repo.get_by_username(settings.admin_username) is not None:
            return
        await repo.create_user(UserCreate(
            username=settings.admin_username,
            password=settings.admin_password,
            role=UserRole.admin,
        ))
        logger.info("Created bootstrap admin %r.", settings.admin_username)


async def _tag_conversations() -> None:
    """In-process trigger for local runs; Cloud Run disables it and uses Cloud Scheduler."""
    from app.services.conversation_tagging import sweep
    while True:
        await asyncio.sleep(settings.tagging_sweep_seconds)
        try:
            await sweep(sessionmanager.session_maker)
        except Exception as exc:  # Keep the loop alive; the next sweep retries.
            logger.warning("Conversation tagging sweep failed: %s", type(exc).__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await sessionmanager.init_db()
    if settings.debug:
        logger.critical("DEBUG MODE IS ON")
        logger.critical("Make sure to not use it on production.")

    # SQLite (tests, local runs without Postgres) creates its tables here.
    # Every other database is managed only by Alembic migrations
    # (`alembic upgrade head`, run by scripts/entrypoint.sh), so schema drift
    # is not hidden by create_all.
    if sessionmanager.dialect_name == "sqlite":
        if settings.debug and settings.reset_db:
            logger.info("Resetting database...")
            await sessionmanager.reset_db()
        else:
            await sessionmanager.create_db()
    elif settings.reset_db:
        logger.warning("RESET_DB is ignored on %s; use `alembic downgrade base && alembic upgrade head`.",
                       sessionmanager.dialect_name)

    from app.chat.runtime import start_chat
    await start_chat(_app, sessionmanager.session_maker)

    await _ensure_admin()

    # Connect to Qdrant and check the embedding API in the background,
    # so the API starts immediately and the first chat message does not wait for it.
    warm_up = asyncio.create_task(warm_up_knowledge())
    tagging = asyncio.create_task(_tag_conversations()) if settings.tagging_sweep_seconds else None

    yield

    warm_up.cancel()
    if tagging:
        tagging.cancel()
    if _app.state.chat_service is not None:
        await _app.state.chat_service.provider.aclose()

    if sessionmanager.engine is not None:
        await sessionmanager.close()
