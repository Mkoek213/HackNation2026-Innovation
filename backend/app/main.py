import os

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

from app.chat.store import ChatError
from app.dependencies import DatabaseDep
from app.exceptions import DependencyUnavailable
from app.handlers import register_exception_handlers
from app.lifespan import lifespan
from app.middlewares.limiter import register_rate_limiter
from app.middlewares.security import register_security_middlewares
from app.modules import knowledge
from app.routes import router
from app.docs import tags_metadata

description = f'''
**Build from:** {os.getenv('BUILD_TIME', "unknown")} rev. {os.getenv("CI_COMMIT_SHORT_SHA", "unknown")}.
'''
app = FastAPI(
    lifespan=lifespan,
    title="Radar innowacji API",
    openapi_tags=tags_metadata,
    description=description,
    docs_url=None,
)
register_exception_handlers(app)


@app.exception_handler(ChatError)
async def chat_error_handler(request, exc):
    return JSONResponse(exc.error.model_dump(mode="json"), status_code=exc.http_status)


register_rate_limiter(app)
register_security_middlewares(app)
app.include_router(router)
app.include_router(knowledge.router)


@app.get("/")
async def root():
    response = RedirectResponse(url="/docs.html")
    return response


class HealthStatus(BaseModel):
    status: str = "ok"


@app.get("/healthcheck",
         response_model=HealthStatus,
         summary="Healthcheck")
async def healthcheck(db: DatabaseDep):
    """
    Liveness and database check for the Docker `HEALTHCHECK`. \
    Returns `{"status": "ok"}` when the database answers, otherwise 503 `dependency_unavailable`.
    """
    try:
        await db.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        raise DependencyUnavailable("The database is unavailable.") from None
    return HealthStatus()


@app.get("/docs.html", include_in_schema=False)
async def docs_html():
    return get_swagger_ui_html(openapi_url=app.openapi_url, title=app.title)


app.mount("/", StaticFiles(directory="static"), name="static")
