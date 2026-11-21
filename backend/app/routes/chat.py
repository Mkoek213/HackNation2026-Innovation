"""Durable chat HTTP adapter; provider and storage live behind app state."""
import base64
import json
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select
from starlette.responses import JSONResponse, StreamingResponse

from app.chat.schemas import (Artifact, ArtifactList, ArtifactPatch, ChatRequest, ChatResponse,
                             ConversationCreated, ConversationList, Conversation, MessageList,
                             CompletedEvent, ErrorEvent, serialize_event)
from app.chat.store import (ChatError, STARTERS, conversation_view, message_view)
from app.models.chat import ChatConversation, ChatMessage

router = APIRouter(prefix="/chat", tags=["Chat"])


def cursor_encode(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


def cursor_decode(cursor):
    try:
        return json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
    except Exception:
        raise ChatError("invalid_input", "Nieprawidłowy kursor historii.", 422) from None


async def owner_for(request, response, create=False):
    return await request.app.state.chat_owners.resolve(request, response, allow_create=create)


@router.post("/conversations", response_model=ConversationCreated)
async def create_conversation(request: Request, response: Response):
    owner = await owner_for(request, response, True)
    row, greeting = await request.app.state.chat_store.create(owner)
    return ConversationCreated(conversation=conversation_view(row), messages=[message_view(greeting)], starters=STARTERS)


@router.get("/conversations", response_model=ConversationList)
async def list_conversations(request: Request, response: Response, cursor: str | None = Query(None, max_length=2048), limit: int = Query(50, ge=1, le=100)):
    owner = await owner_for(request, response)
    async with request.app.state.chat_store.sessions() as db:
        query = select(ChatConversation).where(ChatConversation.owner_id == str(owner.id))
        if cursor:
            value = cursor_decode(cursor)
            try:
                from datetime import datetime
                stamp, cid = datetime.fromisoformat(value[0]), str(UUID(value[1]))
            except Exception:
                raise ChatError("invalid_input", "Nieprawidłowy kursor historii.", 422) from None
            query = query.where((ChatConversation.updated_at < stamp) | ((ChatConversation.updated_at == stamp) & (ChatConversation.id < cid)))
        rows = (await db.scalars(query.order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc()).limit(limit + 1))).all()
        items = [conversation_view(row) for row in rows[:limit]]
        return ConversationList(items=items, next_cursor=cursor_encode([items[-1].updated_at.isoformat(), str(items[-1].id)]) if len(rows) > limit else None)


@router.get("/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: UUID, request: Request, response: Response):
    owner = await owner_for(request, response)
    async with request.app.state.chat_store.sessions() as db:
        return conversation_view(await request.app.state.chat_store.owned(db, owner, conversation_id))


@router.get("/conversations/{conversation_id}/messages", response_model=MessageList)
async def messages(conversation_id: UUID, request: Request, response: Response, cursor: str | None = Query(None, max_length=2048), limit: int = Query(50, ge=1, le=100)):
    owner = await owner_for(request, response)
    position = -1
    if cursor:
        value = cursor_decode(cursor)
        if not isinstance(value, dict) or value.get("conversation") != str(conversation_id) or type(value.get("position")) is not int or value["position"] < 0:
            raise ChatError("invalid_input", "Nieprawidłowy kursor historii.", 422)
        position = value["position"]
    async with request.app.state.chat_store.sessions() as db:
        await request.app.state.chat_store.owned(db, owner, conversation_id)
        rows = (await db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == str(conversation_id), ChatMessage.position > position).order_by(ChatMessage.position).limit(limit + 1))).all()
        return MessageList(items=[message_view(row) for row in rows[:limit]], next_cursor=cursor_encode({"conversation": str(conversation_id), "position": rows[limit - 1].position}) if len(rows) > limit else None)


@router.get("/conversations/{conversation_id}/artifacts", response_model=ArtifactList)
async def list_artifacts(conversation_id: UUID, request: Request, response: Response):
    owner = await owner_for(request, response)
    response.headers["Cache-Control"] = "no-store"
    return ArtifactList(items=await request.app.state.chat_store.artifacts(owner, conversation_id))


@router.get("/conversations/{conversation_id}/artifacts/{artifact_id}", response_model=Artifact)
async def get_artifact(conversation_id: UUID, artifact_id: UUID, request: Request, response: Response):
    owner = await owner_for(request, response)
    response.headers["Cache-Control"] = "no-store"
    return await request.app.state.chat_store.artifact(owner, conversation_id, artifact_id)


@router.patch("/conversations/{conversation_id}/artifacts/{artifact_id}", response_model=Artifact)
async def patch_artifact(conversation_id: UUID, artifact_id: UUID, patch: ArtifactPatch, request: Request, response: Response):
    owner = await owner_for(request, response)
    response.headers["Cache-Control"] = "no-store"
    return await request.app.state.chat_store.patch_artifact(owner, conversation_id, artifact_id, patch)


@router.post("", response_model=ChatResponse)
async def chat_message(payload: ChatRequest, request: Request, response: Response):
    owner = await owner_for(request, response, True)
    service = request.app.state.chat_service
    store = request.app.state.chat_store
    turn, replay = await store.acquire(owner, payload, provider_available=service is not None)
    wants_stream = "text/event-stream" in request.headers.get("accept", "")
    if replay:
        result = await store.result(turn)
        if not wants_stream:
            return result
        async def replay_events():
            yield serialize_event(CompletedEvent(data=result))
        events = replay_events()
    else:
        async def frames():
            async for event in service.events(turn, artifact_id=payload.artifact_id):
                yield serialize_event(event) if event else b": heartbeat\n\n"
        events = frames()
    if wants_stream:
        return StreamingResponse(events, media_type="text/event-stream", headers={
            # no-transform stops proxy gzip (including Next.js rewrites) from buffering the stream
            "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
            **dict(response.headers),
        })
    async for event in service.events(turn, artifact_id=payload.artifact_id, disconnected=request.is_disconnected):
        if isinstance(event, CompletedEvent):
            return event.data
        if isinstance(event, ErrorEvent):
            return JSONResponse(event.data.model_dump(mode="json"), status_code=503, headers=dict(response.headers))
