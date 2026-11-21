"""Maintenance endpoints for schedulers, protected by the shared RADAR_ADMIN_TOKEN."""
import hmac
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from app.database.database import sessionmanager
from app.modules.knowledge.settings import load_knowledge_settings
from app.services.conversation_tagging import sweep

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


@router.post("/tagging/sweep")
async def tagging_sweep(x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None):
    """Tags idle workspace conversations; Cloud Scheduler calls it every few minutes."""
    expected = load_knowledge_settings().admin_token
    if expected is None or x_admin_token is None or not hmac.compare_digest(x_admin_token.encode(), expected.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Valid X-Admin-Token required.")
    return await sweep(sessionmanager.session_maker)
