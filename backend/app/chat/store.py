"""Short transactions for ownership, ordered history and atomic turn acquisition."""
import hashlib
import secrets
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update, Table, Column, String, JSON, ForeignKey
from app.database.database import Base
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import column_property

from app.models.chat import ChatArtifact, ChatConversation, ChatMessage, ChatOwner, ChatTurn
from .ownership import ResolvedOwner
from .schemas import Artifact, Conversation, Message, ChatResponse, ErrorResponse

# Additive metadata table; no raw evidence or provider packets are stored.
chat_results = Table("chat_message_results", Base.metadata,
    Column("message_id", String(36), ForeignKey("chat_messages.id"), primary_key=True),
    Column("innovations", JSON, nullable=False))
# Metadata of live sources read in a turn (title/URL/pages/year); never fetched content.
chat_sources = Table("chat_message_sources", Base.metadata,
    Column("message_id", String(36), ForeignKey("chat_messages.id"), primary_key=True),
    Column("sources", JSON, nullable=False))
# IDs of artifacts committed by a turn, written in the same transaction as each artifact write.
chat_message_artifacts = Table("chat_message_artifacts", Base.metadata,
    Column("message_id", String(36), ForeignKey("chat_messages.id"), primary_key=True),
    Column("artifact_ids", JSON, nullable=False))

# Loaded with each message SELECT, including the existing owner-scoped history route.
ChatMessage.innovation_matches = column_property(select(chat_results.c.innovations).where(
    chat_results.c.message_id == ChatMessage.id).correlate_except(chat_results).scalar_subquery())
ChatMessage.source_metadata = column_property(select(chat_sources.c.sources).where(
    chat_sources.c.message_id == ChatMessage.id).correlate_except(chat_sources).scalar_subquery())
ChatMessage.artifact_links = column_property(select(chat_message_artifacts.c.artifact_ids).where(
    chat_message_artifacts.c.message_id == ChatMessage.id).correlate_except(chat_message_artifacts).scalar_subquery())

GREETING = ("Cześć! Pomogę Ci opisać i zgłosić innowację, sprawdzić podobne rozwiązania "
            "albo znaleźć rozwiązanie do wdrożenia. Opisz, czego potrzebujesz - wspólnie wybierzemy kolejny krok.")
STARTERS = ["Chcę zgłosić innowację z mojej szkoły lub uczelni", "Czy ktoś już rozwiązał podobny problem?", "Szukam rozwiązania do wdrożenia w gminie"]


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def conversation_view(row):
    return Conversation(id=row.id, title=row.title, created_at=aware(row.created_at), updated_at=aware(row.updated_at))


def message_view(row):
    return Message(id=row.id, conversation_id=row.conversation_id, role=row.role, content=row.content,
                   position=row.position, turn_id=row.turn_id, status=row.status,
                   innovations=row.__dict__.get("innovation_matches") or [],
                   sources=row.__dict__.get("source_metadata") or [],
                   artifact_ids=row.__dict__.get("artifact_links") or [],
                   created_at=aware(row.created_at), updated_at=aware(row.updated_at))


def artifact_view(row):
    return Artifact(id=row.id, conversation_id=row.conversation_id, type=row.type, title=row.title,
                    content_markdown=row.content_markdown, revision=row.revision,
                    innovation_id=row.innovation_id, sources=row.sources or [], updated_at=aware(row.updated_at))


class ChatError(Exception):
    def __init__(self, code, message, http_status=409, *, turn_id=None, status=None, current_artifact=None):
        self.http_status = http_status
        self.error = ErrorResponse(code=code, message=message,
                                   retryable=code not in ("not_found", "artifact_revision_conflict"),
                                   turn_id=turn_id, status=status, current_artifact=current_artifact,
                                   current_revision=current_artifact.revision if current_artifact else None)


def missing():
    return ChatError("not_found", "Nie znaleziono rozmowy.", 404)


def missing_artifact():
    return ChatError("not_found", "Nie znaleziono dokumentu.", 404)


def stale(row):
    return ChatError("artifact_revision_conflict", "Treść została zmieniona. Sprawdź aktualną wersję.",
                     current_artifact=artifact_view(row))


class CookieOwnerResolver:
    def __init__(self, sessions, settings):
        self.sessions, self.settings = sessions, settings

    async def resolve(self, request, response, *, allow_create=False):
        token = request.cookies.get(self.settings.owner_cookie_name, "")
        digest = hashlib.sha256(token.encode()).hexdigest()
        async with self.sessions() as db:
            owner = await db.scalar(select(ChatOwner).where(ChatOwner.token_hash == digest)) if token else None
            if owner is None:
                if not allow_create:
                    raise missing()
                token = secrets.token_urlsafe(32)
                owner = ChatOwner(id=str(uuid4()), token_hash=hashlib.sha256(token.encode()).hexdigest())
                db.add(owner)
                await db.commit()
                response.set_cookie(self.settings.owner_cookie_name, token, httponly=True,
                                    secure=self.settings.owner_cookie_secure, samesite="lax", path="/",
                                    max_age=60 * 60 * 24 * 365)
            return ResolvedOwner(UUID(owner.id))


class ChatStore:
    def __init__(self, sessions):
        self.sessions = sessions

    async def owned(self, db, owner, cid):
        row = await db.scalar(select(ChatConversation).where(ChatConversation.id == str(cid),
                                                            ChatConversation.owner_id == str(owner.id)))
        if row is None:
            raise missing()
        return row

    def new_conversation(self, db, owner, title="Nowa rozmowa", cid=None):
        timestamp = now()
        row = ChatConversation(id=str(cid or uuid4()), owner_id=str(owner.id), title=title,
                               created_at=timestamp, updated_at=timestamp, next_position=1)
        db.add(row)
        greeting = ChatMessage(id=str(uuid4()), conversation_id=row.id, role="assistant", content=GREETING,
                               position=0, turn_id=None, status="completed", created_at=timestamp, updated_at=timestamp)
        db.add(greeting)
        return row, greeting

    async def create(self, owner):
        async with self.sessions() as db:
            row, greeting = self.new_conversation(db, owner)
            await db.commit()
            return row, greeting

    async def acquire(self, owner, payload, *, provider_available=True):
        fingerprint = hashlib.sha256(payload.model_dump_json(exclude={"client_request_id"}).encode()).hexdigest()
        try:
            async with self.sessions() as db:
                if payload.conversation_id:
                    await self.owned(db, owner, payload.conversation_id)
                target = await self.artifact_row(db, payload.conversation_id, payload.artifact_id) if payload.artifact_id else None
                previous = await db.scalar(select(ChatTurn).where(ChatTurn.owner_id == str(owner.id),
                                                                 ChatTurn.request_id == str(payload.client_request_id))) if payload.client_request_id else None
                if previous:
                    if previous.request_hash != fingerprint:
                        raise ChatError("request_id_conflict", "Ten identyfikator żądania ma inną treść.")
                    if previous.status != "completed":
                        raise ChatError("turn_in_progress" if previous.status == "running" else "turn_interrupted",
                                        "Odśwież historię. Aby spróbować ponownie, wyślij nowe żądanie.")
                    return previous, True
                if payload.expected_artifact_revision is not None and target.revision != payload.expected_artifact_revision:
                    raise stale(target)
                if not provider_available:
                    raise ChatError("service_unavailable", "Rozmowa jest chwilowo niedostępna.", 503)
                row = await self.owned(db, owner, payload.conversation_id) if payload.conversation_id else self.new_conversation(db, owner, payload.message[:80])[0]
                await db.flush()
                tid, uid, aid = (str(uuid4()) for _ in range(3))
                acquired = await db.execute(update(ChatConversation).where(ChatConversation.id == row.id,
                    ChatConversation.active_turn.is_(None)).values(active_turn=tid, next_position=ChatConversation.next_position + 2,
                                                                  updated_at=now()))
                if acquired.rowcount != 1:
                    raise ChatError("turn_in_progress", "W tej rozmowie trwa już odpowiedź.")
                await db.refresh(row)
                turn = ChatTurn(id=tid, owner_id=str(owner.id), conversation_id=row.id,
                                request_id=str(payload.client_request_id or uuid4()), request_hash=fingerprint,
                                status="running", user_message_id=uid, assistant_message_id=aid)
                db.add(turn)
                for mid, role, content, position, status in [(uid, "user", payload.message, row.next_position - 2, "completed"),
                                                            (aid, "assistant", "", row.next_position - 1, "running")]:
                    db.add(ChatMessage(id=mid, conversation_id=row.id, role=role, content=content,
                                       position=position, turn_id=tid, status=status, created_at=now(), updated_at=now()))
                await db.commit()
                return turn, False
        except IntegrityError:
            raise ChatError("turn_in_progress", "Żądanie jest już przetwarzane. Odśwież historię.") from None

    async def checkpoint(self, turn, text, status="running", *, innovations=None, sources=None):
        async with self.sessions() as db:
            result = await db.execute(update(ChatTurn).where(ChatTurn.id == turn.id, ChatTurn.status == "running").values(status=status))
            if result.rowcount != 1:
                raise ChatError("turn_interrupted", "Odpowiedź została przerwana.", turn_id=turn.id, status="interrupted")
            await db.execute(update(ChatMessage).where(ChatMessage.id == turn.assistant_message_id).values(content=text, status=status, updated_at=now()))
            if status != "running":
                await db.execute(update(ChatConversation).where(ChatConversation.id == turn.conversation_id,
                    ChatConversation.active_turn == turn.id).values(active_turn=None, updated_at=now()))
            if innovations is not None:
                await db.execute(chat_results.insert().values(message_id=turn.assistant_message_id,
                    innovations=[m.model_dump(mode="json") for m in innovations]))
            if sources:
                await db.execute(chat_sources.insert().values(message_id=turn.assistant_message_id,
                    sources=[s.model_dump(mode="json") for s in sources]))
            await db.commit()

    async def result(self, turn):
        async with self.sessions() as db:
            message = await db.get(ChatMessage, turn.assistant_message_id)
            matches = await db.scalar(select(chat_results.c.innovations).where(chat_results.c.message_id == message.id))
            sources = await db.scalar(select(chat_sources.c.sources).where(chat_sources.c.message_id == message.id))
            ids = await db.scalar(select(chat_message_artifacts.c.artifact_ids).where(chat_message_artifacts.c.message_id == message.id))
            rows = (await db.scalars(select(ChatArtifact).where(ChatArtifact.id.in_(ids or [])))).all()
            artifacts = sorted((artifact_view(a) for a in rows), key=lambda a: ids.index(str(a.id)))
            return ChatResponse(answer=message.content, innovations=matches or [], sources=sources or [],
                                artifacts=artifacts,
                                conversation_id=turn.conversation_id,
                                turn_id=turn.id, message_id=message.id, status=message.status)

    async def artifact_row(self, db, cid, aid):
        row = await db.scalar(select(ChatArtifact).where(ChatArtifact.id == str(aid), ChatArtifact.conversation_id == str(cid)))
        if row is None:
            raise missing_artifact()
        return row

    async def artifacts(self, owner, cid):
        async with self.sessions() as db:
            await self.owned(db, owner, cid)
            rows = (await db.scalars(select(ChatArtifact).where(ChatArtifact.conversation_id == str(cid))
                                     .order_by(ChatArtifact.updated_at.desc(), ChatArtifact.id))).all()
            return [artifact_view(row) for row in rows]

    async def artifact(self, owner, cid, aid):
        async with self.sessions() as db:
            await self.owned(db, owner, cid)
            return artifact_view(await self.artifact_row(db, cid, aid))

    async def patch_artifact(self, owner, cid, aid, patch):
        """Manual edit: owner and conversation are verified before any revision is disclosed."""
        async with self.sessions() as db:
            await self.owned(db, owner, cid)
            await self.artifact_row(db, cid, aid)
        return await self.write_artifact(cid, aid, patch.expected_revision,
                                         content=patch.content_markdown, title=patch.title)

    async def write_artifact(self, cid, aid, expected_revision, *, content, title=None, sources=None, message_id=None):
        """Atomic compare-and-swap of the current content; never keeps previous versions."""
        values = {"content_markdown": content, "revision": ChatArtifact.revision + 1, "updated_at": now()}
        if title:
            values["title"] = title
        if sources is not None:
            values["sources"] = sources
        async with self.sessions() as db:
            result = await db.execute(update(ChatArtifact).where(ChatArtifact.id == str(aid),
                ChatArtifact.conversation_id == str(cid), ChatArtifact.revision == expected_revision).values(**values))
            if result.rowcount != 1:
                raise stale(await self.artifact_row(db, cid, aid))
            await self.link(db, message_id, aid)
            await self.touch(db, cid)
            await db.commit()
            return artifact_view(await self.artifact_row(db, cid, aid))

    async def create_artifact(self, cid, *, type, title, content, innovation_id=None, sources=(), message_id=None):
        timestamp = now()
        row = ChatArtifact(id=str(uuid4()), conversation_id=str(cid), type=type, title=title, content_markdown=content,
                           revision=1, innovation_id=innovation_id, sources=list(sources),
                           created_at=timestamp, updated_at=timestamp)
        async with self.sessions() as db:
            db.add(row)
            await db.flush()
            await self.link(db, message_id, row.id)
            await self.touch(db, cid)
            await db.commit()
            return artifact_view(row)

    async def link(self, db, message_id, aid):
        if message_id is None:
            return
        ids = await db.scalar(select(chat_message_artifacts.c.artifact_ids).where(chat_message_artifacts.c.message_id == str(message_id)))
        if ids is None:
            await db.execute(chat_message_artifacts.insert().values(message_id=str(message_id), artifact_ids=[str(aid)]))
        elif str(aid) not in ids:
            await db.execute(update(chat_message_artifacts).where(chat_message_artifacts.c.message_id == str(message_id))
                             .values(artifact_ids=[*ids, str(aid)]))

    async def touch(self, db, cid):
        await db.execute(update(ChatConversation).where(ChatConversation.id == str(cid)).values(updated_at=now()))

    async def recover(self):
        """Run before accepting requests; a single backend process owns running turns."""
        async with self.sessions() as db:
            await db.execute(update(ChatMessage).where(ChatMessage.status == "running").values(status="interrupted", updated_at=now()))
            await db.execute(update(ChatTurn).where(ChatTurn.status == "running").values(status="interrupted"))
            await db.execute(update(ChatConversation).where(ChatConversation.active_turn.is_not(None)).values(active_turn=None))
            await db.commit()
