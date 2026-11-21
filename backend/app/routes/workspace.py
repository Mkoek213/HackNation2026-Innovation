"""Authenticated workspace answered by the Gemini agent (knowledge retrieval without a key), never the demo engine."""
import asyncio
import logging
import re
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.middlewares.limiter import limiter
from app.dependencies import DatabaseDep, PaginationDep
from app.models import ChatOperation, Conversation, ConversationOutcome, ConversationStatus, Message, MessageRole, User
from app.models.chat import ChatArtifact
from app.models.matter import Matter
from app.modules.knowledge import get_knowledge_service
from app.chat.workspace import ask, thread_conversation_id
from app.chat.handoff import append_matters_to_body, prepare_handoff, resolve_attachment
from app.schemas.chat import ChatInnovation, MAX_INNOVATIONS
from app.schemas.workspace import (
    Handoff, HandoffExport, HandoffSend, OperationModel, Rename, Result, Submission, ThreadDetail, ThreadModel,
)
from app.chat.handoff_pdf import render_pdf
from app.repos.conversation_repo import ConversationRepo
from app.services.mail import send_with_pdf
from app.services.pdf import pdf_filename, render_markdown_pdf
from app.services.chat_engine import short_title
from app.repos.workspace_repo import ChatOperationRepo, InnovationMatchRepo, WorkspaceRepo, now
from app.utils.auth import CurrentUserDep

logger = logging.getLogger(__name__)


def private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/workspace/conversations", tags=["Workspace"], dependencies=[Depends(private_response)])
RETRIEVAL_SECONDS = 90
AGENT_SECONDS = 630  # Above the agent's 600-second maximum deadline, allowing durable cleanup.
CONTEXT_CHARACTERS = 8000
CONTEXT_OPERATIONS = 10


@router.post("", response_model=ThreadModel, status_code=201)
async def create_thread(db: DatabaseDep, user: CurrentUserDep):
    thread = Conversation(user_id=user.id, workspace=True, last_activity_at=now())
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return thread


@router.get("")
async def history(db: DatabaseDep, user: CurrentUserDep, page: PaginationDep):
    threads = (await db.scalars(select(Conversation).where(
        Conversation.user_id == user.id, Conversation.workspace.is_(True),
        Conversation.status == ConversationStatus.active,
    ).order_by(Conversation.last_activity_at.desc(), Conversation.id.desc())
      .offset(page.offset).limit(page.limit))).all()
    for t in threads:
        await ChatOperationRepo(db).expire(t.id)
    await db.commit()
    pending_ids = set((await db.scalars(select(ChatOperation.conversation_id).where(
        ChatOperation.conversation_id.in_([t.id for t in threads]), ChatOperation.status == "processing",
    ))).all())
    return [ThreadModel(**ThreadModel.model_validate(t).model_dump(exclude={"pending"}), pending=t.id in pending_ids)
            for t in threads]


@router.get("/{thread_id}", response_model=ThreadDetail)
async def detail(thread_id: int, db: DatabaseDep, user: CurrentUserDep):
    thread = await WorkspaceRepo(db).owned(user.id, thread_id)
    await ChatOperationRepo(db).expire(thread_id)
    await db.commit()
    operations = (await db.scalars(select(ChatOperation).where(
        ChatOperation.conversation_id == thread_id,
    ).order_by(ChatOperation.id).execution_options(populate_existing=True))).all()
    return ThreadDetail(**ThreadModel.model_validate(thread).model_dump(),
                        tags=await ConversationRepo(db).tags_of(thread_id),
                        operations=[OperationModel.model_validate(o) for o in operations])


@router.get("/{thread_id}/handoff", response_model=Handoff)
async def handoff(thread_id: int, db: DatabaseDep, user: CurrentUserDep):
    thread = await WorkspaceRepo(db).owned(user.id, thread_id)
    await ChatOperationRepo(db).expire(thread_id)
    await db.commit()
    return await prepare_handoff(db, thread, settings.radar_contact_email, user.id)


@router.post("/{thread_id}/handoff/send")
async def send_handoff(thread_id: int, data: HandoffSend, db: DatabaseDep, user: CurrentUserDep):
    """Send the reviewed handoff via SMTP when configured; otherwise returns 503 for client fallback."""
    thread = await WorkspaceRepo(db).owned(user.id, thread_id)
    await ChatOperationRepo(db).expire(thread_id)
    await db.commit()
    if await db.scalar(select(ChatOperation.id).where(
        ChatOperation.conversation_id == thread.id, ChatOperation.status == "processing",
    )):
        raise HTTPException(409, "Poczekaj na zakończenie odpowiedzi przed wysłaniem wiadomości.")
    title, markdown = await resolve_attachment(db, user.id, thread.id, data.artifact_id, data.matter_id)
    body = data.body
    if data.include_matters:
        matters = (await db.scalars(
            select(Matter).where(Matter.user_id == user.id).order_by(Matter.updated_at.desc()).limit(20),
        )).all()
        body = append_matters_to_body(body, list(matters))
    packet = data.packet + (f"\n\nDODATKOWY DOKUMENT: {title}\n{markdown}" if title and markdown else "")
    pdf_bytes = await asyncio.to_thread(render_pdf, data.subject, packet)
    await asyncio.to_thread(
        send_with_pdf, recipient=str(data.recipient), subject=data.subject, body=body,
        pdf_bytes=pdf_bytes, pdf_name="podsumowanie-radar.pdf",
    )
    return {"sent": True}


@router.get("/{thread_id}/artifacts/{artifact_id}/pdf")
async def artifact_pdf(thread_id: int, artifact_id: str, db: DatabaseDep, user: CurrentUserDep):
    await WorkspaceRepo(db).owned(user.id, thread_id)
    cid = str(thread_conversation_id(thread_id))
    artifact = await db.scalar(select(ChatArtifact).where(
        ChatArtifact.id == artifact_id, ChatArtifact.conversation_id == cid,
    ))
    if artifact is None:
        raise HTTPException(404, "Nie znaleziono dokumentu.")
    pdf = render_markdown_pdf(artifact.title, artifact.content_markdown)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{pdf_filename(artifact.title)}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{thread_id}/handoff/pdf")
async def handoff_pdf(thread_id: int, data: HandoffExport, db: DatabaseDep, user: CurrentUserDep):
    thread = await WorkspaceRepo(db).owned(user.id, thread_id)
    await ChatOperationRepo(db).expire(thread_id)
    await db.commit()
    # Reuse the pending-turn guard. Export only the reviewed text supplied by the owner;
    # edits/exclusions are ephemeral and never overwrite canonical facts or drafts.
    await prepare_handoff(db, thread, settings.radar_contact_email)
    pdf = await asyncio.to_thread(render_pdf, data.title, data.packet)
    return Response(pdf, media_type="application/pdf", headers={
        "Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="podsumowanie-radar.pdf"',
        "X-Content-Type-Options": "nosniff",
    })


@router.patch("/{thread_id}", response_model=ThreadModel)
async def rename(thread_id: int, data: Rename, db: DatabaseDep, user: CurrentUserDep):
    thread = await WorkspaceRepo(db).owned(user.id, thread_id, lock=True)
    thread.title = data.title
    await db.commit()
    return thread


@router.post("/{thread_id}/innovations/{innovation_id}/open")
async def open_innovation(
        thread_id: int, db: DatabaseDep, user: CurrentUserDep,
        innovation_id: str = Path(min_length=1, max_length=120, pattern=r"^[a-z0-9-]+$"),
):
    """Marks an innovation shown in this thread as opened (for the admin ranking). 404 when it was not shown."""
    await WorkspaceRepo(db).owned(user.id, thread_id)
    await InnovationMatchRepo(db).open(thread_id, innovation_id)
    await db.commit()
    return {"opened": innovation_id}


@router.delete("/{thread_id}")
async def archive(thread_id: int, db: DatabaseDep, user: CurrentUserDep):
    thread = await WorkspaceRepo(db).owned(user.id, thread_id, lock=True)
    thread.status = ConversationStatus.archived
    await db.commit()
    return {"archived": thread.id}


def context_query(operations, content):
    completed = [o for o in operations if o.status == "completed"][-CONTEXT_OPERATIONS:]
    last = next((o.result["innovations"] for o in reversed(completed) if o.result.get("innovations")), [])
    # References are resolved only against candidates actually shown in this thread.
    ordinal = re.search(r"\b(pierwsz\w*|drug\w*|trzeci\w*|[123](?=\s+(?:propozyc|innowac)))\b", content.lower())
    if ordinal:
        if not last:
            return content, {"id": None}
        word = ordinal.group(1)
        index = 0 if word.startswith("pierwsz") else 1 if word.startswith("drug") else 2 if word.startswith("trzeci") else int(word) - 1
        if index < len(last):
            candidate = last[index]
            return f"{candidate['title']}\n{candidate['solution'][:3400]}\n{content}", candidate
        return content, {"id": None}
    for candidate in last:
        if candidate["title"].casefold() in content.casefold():
            return f"{candidate['title']}\n{candidate['solution'][:3400]}\n{content}", candidate
    previous = "\n".join(o.content for o in completed[-3:])
    return f"{previous[-(CONTEXT_CHARACTERS - len(content) - 1):]}\n{content}", None


async def retrieve(operations, content):
    query, selected = context_query(operations, content)
    if selected is not None and selected["id"] is None:
        return Result(answer="W poprzedniej odpowiedzi nie ma propozycji o tym numerze. Wskaż jej tytuł.", outcome="no_match")
    service = await get_knowledge_service()
    results = await service.retrieve(query, pool=MAX_INNOVATIONS)
    if selected:
        results = [r for r in results if r.innovation.id == selected["id"]]
        if not results:
            return Result(answer="Nie udało się odczytać wskazanej propozycji z bazy wiedzy. Spróbuj ponownie.", outcome="unavailable")
    innovations = [ChatInnovation.from_retrieved(r) for r in results]
    if selected:
        answer = innovations[0].solution or "Źródła nie zawierają krótkiego opisu tej propozycji."
    elif innovations:
        answer = "Znalazłem powiązane innowacje w bazie wiedzy. Otwórz tytuł, aby przeczytać opis i źródła. Dopasowanie nie zostało jeszcze ocenione."
    else:
        answer = "Nie znalazłem powiązanych innowacji. Opisz sytuację inaczej lub dodaj szczegóły."
    return Result(answer=answer, innovations=innovations, outcome="matched" if innovations else "no_match")


async def agent(request, user_id, thread_id, content):
    """Answer with the same flexible agent used by the standalone chat API."""
    state = request.app.state
    response = await ask(state.chat_store, state.chat_service, user_id, thread_id, content)
    innovations = []
    for match in response.innovations:
        innovations.append(ChatInnovation(
            id=match.id, title=match.title, source_url=match.source_url, video_url=match.video_url,
            solution=match.solution, retrieval_score=match.retrieval_score or 0.0, evidence=match.evidence,
            fit_reason=match.fit_reason, limitations=match.limitations,
        ))
    return Result(answer=response.answer, innovations=innovations, artifacts=response.artifacts, sources=response.sources,
                  matters=response.matters, creator=response.creator, suggestions=response.suggestions, outcome="matched" if innovations else "no_match")


@router.post("/{thread_id}/messages", response_model=OperationModel)
@limiter.limit(settings.chat_rate_limit)
async def submit(request: Request, response: Response, thread_id: int, data: Submission, db: DatabaseDep,
                 user: CurrentUserDep):
    started = time.monotonic()
    # Admission is serialized per account on PostgreSQL. SQLite briefly locks writes;
    # knowledge retrieval runs outside this transaction and holds no admission lock.
    await db.execute(update(User).where(User.id == user.id).values(id=user.id))
    thread = await WorkspaceRepo(db).owned(user.id, thread_id, lock=True)
    await ChatOperationRepo(db).expire(user_id=user.id)
    operation = await db.scalar(select(ChatOperation).where(
        ChatOperation.conversation_id == thread_id, ChatOperation.key == str(data.key),
    ))
    if operation:
        if operation.content != data.content:
            raise HTTPException(409, "Klucz wiadomości jest już używany.")
        if operation.status != "failed":
            await db.commit()
            return operation
    previous = list(reversed((await db.scalars(select(ChatOperation).where(
        ChatOperation.conversation_id == thread_id,
    ).order_by(ChatOperation.id.desc()).limit(CONTEXT_OPERATIONS))).all()))
    # Workspace rule: only one in-flight send across the owner's threads.
    busy = await db.scalar(select(ChatOperation.id).join(Conversation).where(
        Conversation.user_id == user.id, Conversation.workspace.is_(True),
        ChatOperation.status == "processing",
        ChatOperation.id != (operation.id if operation else -1),
    ))
    if busy or any(o.status == "processing" for o in previous):
        raise HTTPException(409, "Poczekaj na zakończenie poprzedniej wiadomości.")
    if operation and previous[-1].id != operation.id:
        raise HTTPException(409, "Możesz ponowić tylko ostatnią wiadomość.")
    attempt = str(uuid4())
    try:
        if not operation:
            message = Message(conversation_id=thread_id, role=MessageRole.user, content=data.content)
            db.add(message)
            await db.flush()
            operation = ChatOperation(conversation_id=thread_id, key=str(data.key), content=data.content,
                                      user_message_id=message.id, attempt=attempt, started_at=now())
            db.add(operation)
            if not thread.title:
                thread.title = short_title(data.content)
        else:
            claimed = await db.execute(update(ChatOperation).where(
                ChatOperation.id == operation.id, ChatOperation.status == "failed",
                ChatOperation.attempt == operation.attempt,
            ).values(status="processing", attempt=attempt, started_at=now(), result=None))
            if not claimed.rowcount:
                await db.rollback()
                raise HTTPException(409, "Wiadomość jest już przetwarzana. Odśwież rozmowę.")
        thread.last_activity_at = now()
        await db.commit()
        await db.refresh(operation)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Wiadomość jest już przetwarzana. Odśwież rozmowę.") from None
    operation_id = operation.id
    admitted = time.monotonic()
    # Topic tags are assigned once the conversation is idle (app/services/conversation_tagging.py).
    try:
        if request.app.state.chat_service is not None:
            result = await asyncio.wait_for(agent(request, user.id, thread_id, data.content), timeout=AGENT_SECONDS)
        else:  # Without a Gemini key the workspace falls back to plain knowledge retrieval.
            result = await asyncio.wait_for(retrieve(previous, data.content), timeout=RETRIEVAL_SECONDS)
    except Exception:
        # Never log user input or replace a failed answer with a demo response.
        result = Result(answer="Asystent jest teraz niedostępny. Możesz ponowić wiadomość.", outcome="unavailable")
    answered = time.monotonic()
    # A stale worker must never finish a later retry. Claim completion atomically.
    claimed = await db.execute(update(ChatOperation).where(
        ChatOperation.id == operation_id, ChatOperation.attempt == attempt, ChatOperation.status == "processing",
    ).values(status="failed" if result.outcome == "unavailable" else "completed", result=result.model_dump(mode="json")))
    if claimed.rowcount and result.outcome != "unavailable":
        thread.outcome = ConversationOutcome.answered if result.outcome == "matched" else ConversationOutcome.no_answer
        await InnovationMatchRepo(db).record(thread_id, result.innovations)
        assistant = Message(conversation_id=thread_id, role=MessageRole.assistant, content=result.answer,
                            sources=[*[e.model_dump() for i in result.innovations for e in i.evidence],
                                     *[s.model_dump(mode="json") for s in result.sources]])
        db.add(assistant)
        await db.flush()
        await db.execute(update(ChatOperation).where(ChatOperation.id == operation_id).values(assistant_message_id=assistant.id))
    await db.commit()
    logger.info("Workspace message: admission=%.2f answer=%.2f total=%.2f",
                admitted - started, answered - admitted, time.monotonic() - started)
    return await db.scalar(select(ChatOperation).where(ChatOperation.id == operation_id).execution_options(populate_existing=True))
