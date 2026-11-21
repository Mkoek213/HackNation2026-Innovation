"""Topic tagging of idle workspace conversations, outside the chat request path.

Fastino latency varies from about one second to a timeout, so tagging never runs while a
reply is being produced. A conversation is due once it has been idle for
`tagging_idle_seconds` and its tags do not cover its last activity yet. Failed attempts
leave it due, so the next sweep retries them.
"""
import asyncio
import datetime as dt
import logging
import time

from sqlalchemy import exists, or_, select

from app.config import settings
from app.models import ChatOperation, Conversation
from app.repos.conversation_repo import ConversationRepo
from app.repos.workspace_repo import now
from app.services.tagging import assignments, classify

logger = logging.getLogger(__name__)
BATCH = 20
PARALLEL = 4
_running = asyncio.Lock()  # One sweep per process; concurrent sweeps elsewhere are resolved per row.


async def sweep(session_maker) -> dict[str, int]:
    """Tags up to BATCH due conversations. Returns counts for logs and the internal endpoint."""
    if _running.locked():
        return {"due": 0, "tagged": 0, "failed": 0}
    async with _running:
        started = time.monotonic()
        idle_before = now() - dt.timedelta(seconds=settings.tagging_idle_seconds)
        async with session_maker() as db:
            due = (await db.execute(select(Conversation.id, Conversation.last_activity_at).where(
                Conversation.workspace.is_(True),
                Conversation.last_activity_at <= idle_before,
                or_(Conversation.tagged_at.is_(None), Conversation.tagged_at < Conversation.last_activity_at),
                exists().where(ChatOperation.conversation_id == Conversation.id, ChatOperation.status == "completed"),
                ~exists().where(ChatOperation.conversation_id == Conversation.id, ChatOperation.status == "processing"),
            ).order_by(Conversation.last_activity_at.desc()).limit(BATCH))).all()
            if not due:
                return {"due": 0, "tagged": 0, "failed": 0}
            options = await ConversationRepo(db).tag_options()
            texts = ["\n".join((await db.scalars(select(ChatOperation.content).where(
                ChatOperation.conversation_id == conversation_id, ChatOperation.status == "completed",
            ).order_by(ChatOperation.id))).all()) for conversation_id, _ in due]

        gate = asyncio.Semaphore(PARALLEL)

        async def decide(text):
            async with gate:
                # A stalled request is retried quickly; a typical decision takes 1-2 s.
                return await classify(text, options, purpose="conversation", read_timeout=5, deadline=15, retries=1)

        results = await asyncio.gather(*(decide(text) for text in texts))
        tagged = failed = 0
        async with session_maker() as db:
            repo = ConversationRepo(db)
            for (conversation_id, covered), result in zip(due, results):
                if result.status == "unavailable":
                    failed += 1  # Stays due; keeps the previous classification and tags.
                    continue
                conversation = await db.get(Conversation, conversation_id, with_for_update=True)
                if conversation is None or (conversation.tagged_at is not None and conversation.tagged_at >= covered):
                    continue  # Removed, or tagged by a concurrent sweep.
                conversation.classification = result.model_dump(mode="json")
                if result.status in {"completed", "uncertain"}:
                    await repo._replace_ai_tags(conversation_id, assignments(result), replace=result.status == "completed")
                # The activity snapshot, not the current time: a message sent meanwhile keeps it due.
                conversation.tagged_at = covered
                tagged += 1
            await db.commit()
        logger.info("Conversation tagging: due=%d tagged=%d failed=%d seconds=%.2f",
                    len(due), tagged, failed, time.monotonic() - started)
        return {"due": len(due), "tagged": tagged, "failed": failed}
