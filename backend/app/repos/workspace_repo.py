"""Owned workspace persistence, using the existing per-resource repository convention."""
import datetime as dt

from sqlalchemy import select, update

from app.exceptions import NotFoundError
from app.models import ChatOperation, Conversation, ConversationStatus, InnovationMatch
from app.schemas.chat import ChatInnovation
from app.schemas.workspace import OperationModel, Result, ThreadModel
from app.utils.crud_repo import CRUDRepo

OPERATION_LEASE_SECONDS = 720  # Above AGENT_SECONDS in app.routes.workspace.


def now():
    return dt.datetime.now(dt.timezone.utc)


class WorkspaceRepo(CRUDRepo[Conversation, ThreadModel]):
    async def owned(self, user_id: int, thread_id: int, *, lock=False):
        query = select(Conversation).where(
            Conversation.id == thread_id, Conversation.user_id == user_id,
            Conversation.workspace.is_(True), Conversation.status == ConversationStatus.active,
        )
        thread = await self.db.scalar(query.with_for_update() if lock else query)
        if thread is None:
            raise NotFoundError(resource="Conversation", key=thread_id)
        return thread


class InnovationMatchRepo:
    def __init__(self, db):
        self.db = db

    async def record(self, thread_id: int, innovations: list[ChatInnovation]):
        """Adds the innovations not yet shown in this thread. The caller commits."""
        known = set((await self.db.scalars(select(InnovationMatch.innovation_id).where(
            InnovationMatch.conversation_id == thread_id,
        ))).all())
        for innovation in innovations:
            if innovation.id not in known:
                known.add(innovation.id)
                self.db.add(InnovationMatch(conversation_id=thread_id, innovation_id=innovation.id, title=innovation.title))

    async def open(self, thread_id: int, innovation_id: str):
        """:raises NotFoundError: the innovation was not shown in this thread."""
        updated = await self.db.execute(update(InnovationMatch).where(
            InnovationMatch.conversation_id == thread_id, InnovationMatch.innovation_id == innovation_id,
        ).values(opened=True))
        if not updated.rowcount:
            raise NotFoundError(resource="InnovationMatch", key=innovation_id)


class ChatOperationRepo(CRUDRepo[ChatOperation, OperationModel]):
    async def expire(self, thread_id=None, *, user_id=None):
        scope = (ChatOperation.conversation_id.in_(select(Conversation.id).where(
            Conversation.user_id == user_id, Conversation.workspace.is_(True),
        )) if user_id is not None else ChatOperation.conversation_id == thread_id)
        await self.db.execute(update(ChatOperation).where(
            scope, ChatOperation.status == "processing",
            ChatOperation.started_at < now() - dt.timedelta(seconds=OPERATION_LEASE_SECONDS),
        ).values(status="failed", result=Result(
            answer="Przetwarzanie zostało przerwane. Możesz ponowić wiadomość.", outcome="unavailable",
        ).model_dump()))
