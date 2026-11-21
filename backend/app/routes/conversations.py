import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, TypeVar

from fastapi import APIRouter, Path, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from app.config import settings
from app.dependencies import DatabaseDep, PaginationDep
from app.docs import Tags
from app.exceptions import DependencyUnavailable, DomainError
from app.middlewares.limiter import limiter
from app.models import Conversation, ConversationStatus
from app.repos.conversation_repo import ConversationRepo, ProjectMatchRepo
from app.schemas.conversation import (
    AssistantReply,
    ConversationCreate,
    ConversationDetail,
    ConversationModel,
    ConversationStart,
    ConversationTagInput,
    ConversationTagModel,
    ConversationUpdate,
    HistoryTurn,
    MessageCreate,
    SourceModel,
)
from app.schemas.default import Delete, ErrorResponse, ItemList, NOT_FOUND
from app.services.chat_engine import Answer, AnswerChunk, ChatEngine, ChatEngineDep, ChatTurn, ConversationContext, TagOption
from app.services.tagging import classify, assignments
from app.services.rag import SearchFilters, SourceHit, VectorStore, VectorStoreDep
from app.utils.auth import CurrentUserDep, VisitorDep, set_visitor_cookie

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/conversations",
    tags=[Tags.Conversations],
    responses={},
)

UNAVAILABLE = {"model": ErrorResponse, "description": "The AI service is unavailable; nothing was stored, resend the message"}
#: User turns joined into the vector search query, so follow-ups keep their context.
QUERY_USER_TURNS = 3

T = TypeVar("T")


# ============ chat turn ============


@dataclass
class Turn:
    """Everything the chat engine gets for one user message."""
    conversation: Conversation
    message: str
    context: ConversationContext
    history: list[ChatTurn]
    hits: list[SourceHit]
    tags: list[TagOption]


async def _ai_call(awaitable: Awaitable[T], what: str) -> T:
    """Awaits an AI adapter call, turning a failure into 503. Only the exception type is
    logged: adapter errors may quote the user's text, which must not reach the logs."""
    try:
        return await awaitable
    except DomainError:
        raise
    except Exception as exc:
        logger.warning("AI adapter call %s failed: %s", what, type(exc).__name__)
        # `from None`: the 5xx handler logs the traceback, which must not chain the adapter error.
        raise DependencyUnavailable(
            "The AI service is unavailable. Nothing was stored; try sending the message again."
        ) from None


async def _prepare_turn(
        repo: ConversationRepo,
        store: VectorStore,
        conversation: Conversation,
        message: str,
        client_history: list[HistoryTurn],
) -> Turn:
    """Builds the transcript (stored messages when saved, else the client's `history`)
    and runs the vector search."""
    if conversation.saved:
        history = await repo.saved_history(conversation.id)
    else:
        history = [ChatTurn(role=t.role.value, content=t.content) for t in client_history]
    history.append(ChatTurn(role="user", content=message))
    query = " ".join([t.content for t in history if t.role == "user"][-QUERY_USER_TURNS:])
    hits = await _ai_call(store.search(query, SearchFilters(location_id=conversation.location_id)), "search")
    return Turn(
        conversation=conversation,
        message=message,
        context=ConversationContext(
            id=conversation.id, kind=conversation.kind, location_id=conversation.location_id,
            saved=conversation.saved, title=conversation.title,
        ),
        history=history,
        hits=hits,
        tags=await repo.tag_options(),
    )


async def _finish_turn(repo: ConversationRepo, turn: Turn, answer: Answer) -> AssistantReply:
    user_text = ("\n".join([await repo.user_text(turn.conversation.id), turn.message])
                 if turn.conversation.saved else "\n".join(t.content for t in turn.history if t.role == "user"))
    classification = await classify(user_text, turn.tags, purpose="conversation")
    turn.conversation.classification = classification.model_dump(mode="json")
    # Keep the explicitly selected demo engine usable without provider configuration.
    labels = (answer.tag_assignments if classification.error_kind == "configuration"
              else assignments(classification) if classification.status in {"completed", "uncertain"} else None)
    assistant, matches = await repo.save_turn(
        turn.conversation,
        user_message=turn.message,
        content=answer.content,
        sources=answer.sources,
        tag_assignments=labels,
        preserve_ai_tags=classification.status in {"uncertain", "unavailable"},
        project_ids=answer.project_ids,
        outcome=answer.outcome,
        title=answer.title,
        tags=turn.tags,
    )
    return AssistantReply(
        message_id=assistant.id if assistant is not None else None,
        content=answer.content,
        sources=[SourceModel(**hit.as_source()) for hit in answer.sources],
        projects=await ProjectMatchRepo(repo.db).models(matches),
        tags=await repo.tags_of(turn.conversation.id),
        outcome=answer.outcome,
    )


async def _answer(repo: ConversationRepo, store: VectorStore, engine: ChatEngine, conversation: Conversation,
                  message: str, history: list[HistoryTurn]) -> AssistantReply:
    turn = await _prepare_turn(repo, store, conversation, message, history)
    answer = await _ai_call(engine.answer(turn.context, turn.history, turn.hits, turn.tags), "answer")
    return await _finish_turn(repo, turn, answer)


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ============ endpoints ============


@router.post("",
             dependencies=None,
             response_model=ConversationStart,
             responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_503_SERVICE_UNAVAILABLE: UNAVAILABLE},
             status_code=status.HTTP_201_CREATED,
             summary="Start conversation",
             response_description="Successful Response")
@limiter.limit(settings.chat_rate_limit)
async def start_conversation(
        request: Request,
        response: Response,
        db: DatabaseDep,
        actor: VisitorDep,
        store: VectorStoreDep,
        engine: ChatEngineDep,
        data: ConversationCreate,
):
    """
    Start a conversation with its first message and get the first answer. Public. \\
    Logged in: the conversation is saved (messages, title) and appears in `GET /conversations`. \\
    Anonymous: owned by the `visitor_id` cookie; no message text or title is stored, only the
    tags, recommended projects and outcome (for statistics). The client keeps the transcript
    and sends it as `history` with the next messages. \\
    Raises 404 Not Found for an unknown `location_id`, 503 when the AI service fails (nothing is stored).
    """
    repo = ConversationRepo(db)
    conversation = await repo.start(data, actor)
    try:
        reply = await _answer(repo, store, engine, conversation, data.message, [])
    except DomainError:
        await db.rollback()
        raise
    conversation = await repo.get_reloaded(conversation.id)
    return ConversationStart(conversation=ConversationModel.model_validate(conversation), answer=reply)


@router.get("",
            dependencies=None,
            response_model=ItemList[ConversationModel],
            status_code=status.HTTP_200_OK,
            summary="Get my conversations",
            response_description="Successful Response")
async def get_conversations(
        db: DatabaseDep,
        user: CurrentUserDep,
        page: PaginationDep,
        tag_id: int | None = Query(None, ge=1, description="Only conversations with this tag."),
        subtag_id: int | None = Query(None, ge=1, description="Only conversations with this subtag."),
        q: str | None = Query(None, min_length=1, max_length=100, description="Title or message fragment."),
        conversation_status: ConversationStatus | None = Query(None, alias="status", description="Only conversations with this status."),
):
    """
    The logged-in user's saved conversations, most recently active first. \\
    Paginated with `?limit=&offset=`. Raises 401 Unauthorized when not logged in.
    """
    return await ConversationRepo(db).search(
        user_id=user.id, status=conversation_status, tag_id=tag_id, subtag_id=subtag_id, q=q,
        limit=page.limit, offset=page.offset,
    )


@router.get("/{conversation_id}",
            dependencies=None,
            response_model=ConversationDetail,
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Get conversation one",
            response_description="Successful Response")
async def get_conversation_one(
        db: DatabaseDep,
        actor: VisitorDep,
        conversation_id: int = Path(ge=1),
):
    """
    A conversation with its tags, messages (empty for anonymous ones) and recommended projects. \\
    Owner only: the logged-in user who started it, or the visitor cookie of an anonymous one, or the admin. \\
    Raises 404 Not Found when it does not exist, 403 Forbidden for someone else's conversation.
    """
    repo = ConversationRepo(db)
    return await repo.detail(await repo.get_owned(conversation_id, actor))


@router.patch("/{conversation_id}",
              dependencies=None,
              response_model=ConversationModel,
              responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
              status_code=status.HTTP_200_OK,
              summary="Update conversation",
              response_description="Successful Response")
async def update_conversation(
        db: DatabaseDep,
        user: CurrentUserDep,
        actor: VisitorDep,
        changes: ConversationUpdate,
        conversation_id: int = Path(ge=1),
):
    """
    Rename, archive (`{"status": "archived"}`) or set the location of a conversation. Login required, owner only. \\
    Raises 401 when not logged in, 403 for someone else's conversation, 404 when it or the location
    does not exist, 422 for a title of an anonymous conversation.
    """
    repo = ConversationRepo(db)
    conversation = await repo.get_owned(conversation_id, actor)
    return await repo.update_conversation(conversation, changes)


@router.delete("/{conversation_id}",
               dependencies=None,
               response_model=Delete,
               responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
               status_code=status.HTTP_200_OK,
               summary="Delete conversation",
               response_description="Successful Response")
async def delete_conversation(
        db: DatabaseDep,
        user: CurrentUserDep,
        actor: VisitorDep,
        conversation_id: int = Path(ge=1),
):
    """
    Delete a conversation with its messages, tags and project matches. Login required, owner only. \\
    Raises 401 when not logged in, 403 for someone else's conversation, 404 when it does not exist.
    """
    repo = ConversationRepo(db)
    await repo.get_owned(conversation_id, actor)
    return await repo.delete_one(id=conversation_id, key_loc="path")


@router.post("/{conversation_id}/messages",
             dependencies=None,
             response_model=AssistantReply,
             responses={status.HTTP_404_NOT_FOUND: NOT_FOUND, status.HTTP_503_SERVICE_UNAVAILABLE: UNAVAILABLE},
             status_code=status.HTTP_200_OK,
             summary="Send message",
             response_description="Successful Response")
@limiter.limit(settings.chat_rate_limit)
async def send_message(
        request: Request,
        response: Response,
        db: DatabaseDep,
        actor: VisitorDep,
        store: VectorStoreDep,
        engine: ChatEngineDep,
        data: MessageCreate,
        conversation_id: int = Path(ge=1),
):
    """
    Send a message and get the assistant's answer `{content, sources, projects, tags, outcome}`. Owner only. \\
    Anonymous conversations: send the earlier turns as `history` (at most 10 items and 8 000 characters,
    422 above); nothing of the text is stored. Saved conversations ignore `history` and use the stored messages. \\
    Raises 403 for someone else's conversation, 404 when it does not exist, 503 when the AI service fails
    (nothing is stored).
    """
    repo = ConversationRepo(db)
    conversation = await repo.get_owned(conversation_id, actor)
    try:
        return await _answer(repo, store, engine, conversation, data.content, data.history)
    except DomainError:
        await db.rollback()
        raise


@router.post("/{conversation_id}/messages/stream",
             dependencies=None,
             response_class=StreamingResponse,
             responses={
                 status.HTTP_200_OK: {
                     "content": {"text/event-stream": {}},
                     "description": "Server-Sent Events: `token`… `projects` `done` (or `error`)",
                 },
                 status.HTTP_404_NOT_FOUND: NOT_FOUND,
                 status.HTTP_503_SERVICE_UNAVAILABLE: UNAVAILABLE,
             },
             summary="Send message (stream)",
             response_description="Server-Sent Events")
@limiter.limit(settings.chat_rate_limit)
async def stream_message(
        request: Request,
        response: Response,
        db: DatabaseDep,
        actor: VisitorDep,
        store: VectorStoreDep,
        engine: ChatEngineDep,
        data: MessageCreate,
        conversation_id: int = Path(ge=1),
):
    """
    Same as `POST /conversations/{id}/messages`, as Server-Sent Events:

    - `token` `{"text": "..."}`: the next piece of the answer text (repeated);
    - `projects`: the recommended projects (`ProjectMatchModel[]`), sent once the answer is stored;
    - `done`: the full `AssistantReply`;
    - `error` `{"detail": [...]}` instead of `projects`/`done` when the AI service fails mid-answer
      (nothing is stored).

    Errors before the first event (403, 404, 422, 503) are normal JSON responses.
    """
    repo = ConversationRepo(db)
    conversation = await repo.get_owned(conversation_id, actor)
    turn = await _prepare_turn(repo, store, conversation, data.content, data.history)
    events = aiter(engine.stream(turn.context, turn.history, turn.hits, turn.tags))
    # The first event is awaited here, so an adapter that fails right away still gives a 503.
    first = await _ai_call(anext(events, None), "stream")

    async def body() -> AsyncIterator[str]:
        item = first
        try:
            while isinstance(item, AnswerChunk):
                yield _sse("token", {"text": item.text})
                item = await anext(events, None)
            if not isinstance(item, Answer):
                raise RuntimeError("The chat engine stream ended without an Answer.")
            reply = await _finish_turn(repo, turn, item)
        except Exception as exc:
            logger.warning("AI adapter call stream failed: %s", type(exc).__name__)
            await db.rollback()
            error = DependencyUnavailable("The AI service is unavailable. Nothing was stored; try sending the message again.")
            yield _sse("error", {"detail": error.errors()})
            return
        yield _sse("projects", [p.model_dump(mode="json") for p in reply.projects])
        yield _sse("done", reply.model_dump(mode="json"))

    streaming = StreamingResponse(body(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # no proxy buffering (nginx)
    })
    # The route returns a Response, so the cookie VisitorDep may have set is not merged in.
    set_visitor_cookie(streaming, actor.visitor_id)
    return streaming


@router.put("/{conversation_id}/tags",
            dependencies=None,
            response_model=list[ConversationTagModel],
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Replace conversation tags",
            response_description="Successful Response")
async def replace_conversation_tags(
        db: DatabaseDep,
        user: CurrentUserDep,
        actor: VisitorDep,
        items: list[ConversationTagInput],
        conversation_id: int = Path(ge=1),
):
    """
    Replace the conversation's tags (manual correction): `[{tag_id, subtag_id?}]`. Login required, owner only. \\
    Manual tags are kept by later answers; the AI only replaces its own tags. \\
    Raises 401 when not logged in, 403 for someone else's conversation, 404 for an unknown conversation,
    tag or subtag, 422 when a subtag belongs to another tag or a pair is listed twice.
    """
    repo = ConversationRepo(db)
    await repo.get_owned(conversation_id, actor)
    return await repo.replace_tags(conversation_id, items)
