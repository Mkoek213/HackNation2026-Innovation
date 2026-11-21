"""The Gemini agent behind the authenticated workspace.

Each account owns one server-side chat owner and each workspace thread one agentic chat
conversation, both with deterministic IDs. The owner's cookie token is random and never
issued, so the anonymous /chat API cannot reach account conversations.
"""
import hashlib
import secrets
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.exc import IntegrityError

from app.models.chat import ChatConversation, ChatOwner
from .ownership import ResolvedOwner
from .schemas import ChatRequest, CompletedEvent, ErrorEvent

NAMESPACE = uuid5(NAMESPACE_URL, "https://radar.pcinn.org/workspace")


class AgentFailed(Exception):
    pass


async def account_owner(store, user_id):
    owner_id = str(uuid5(NAMESPACE, f"user:{user_id}"))
    async with store.sessions() as db:
        if await db.get(ChatOwner, owner_id) is None:
            db.add(ChatOwner(id=owner_id, token_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest()))
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()  # Created concurrently.
    return ResolvedOwner(UUID(owner_id))


def thread_conversation_id(thread_id):
    return uuid5(NAMESPACE, f"thread:{thread_id}")


async def thread_conversation(store, owner, thread_id):
    cid = thread_conversation_id(thread_id)
    async with store.sessions() as db:
        if await db.get(ChatConversation, str(cid)) is None:
            store.new_conversation(db, owner, cid=cid)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
    return cid


async def ask(store, service, user_id, thread_id, message):
    """Run one agent turn to completion and return its ChatResponse."""
    owner = await account_owner(store, user_id)
    cid = await thread_conversation(store, owner, thread_id)
    turn, _ = await store.acquire(owner, ChatRequest(message=message, conversation_id=cid))
    async for event in service.events(turn, account=(user_id, thread_id)):
        if isinstance(event, CompletedEvent):
            return event.data
        if isinstance(event, ErrorEvent):
            raise AgentFailed(event.data.code)
    raise AgentFailed("provider_error")
