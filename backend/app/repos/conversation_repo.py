import datetime as dt
from typing import Sequence

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.orm import selectinload

from app.exceptions import NotFoundError, ValidationError
from app.models import (
    Conversation,
    ConversationStatus,
    ConversationTag,
    Message,
    MessageRole,
    Project,
    ProjectMatch,
    ProjectStatus,
    Subtag,
    TagSource,
)
from app.repos.location_repo import LocationRepo
from app.repos.tag_repo import TagRepo
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationModel,
    ConversationTagInput,
    ConversationTagModel,
    ConversationUpdate,
    MessageModel,
    ProjectMatchModel,
)
from app.schemas.default import ItemList
from app.schemas.project import ProjectModel
from app.services.chat_engine import ChatTurn, SubtagOption, TagAssignment, TagOption
from app.services.rag import SourceHit
from app.utils.auth import Actor, assert_owner
from app.utils.crud_repo import CRUDRepo

#: Stored messages given to the chat engine as the transcript of a saved conversation.
SAVED_HISTORY_MESSAGES = 20


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class ConversationRepo(CRUDRepo[Conversation, ConversationModel]):
    # Messages, tags and matches are removed with the conversation (ON DELETE CASCADE).
    protect_on_delete = ()

    def _with_tags(self):
        # populate_existing refreshes tag collections already loaded earlier in the same session.
        return (
            select(Conversation).where(Conversation.workspace.is_(False))
            .options(selectinload(Conversation.tags))
            .execution_options(populate_existing=True)
        )

    async def get_owned(self, conversation_id: int, actor: Actor) -> Conversation:
        """The conversation with its tags loaded, if ``actor`` owns it (see ``assert_owner``).
        :raises NotFoundError: missing. :raises ForbiddenError: not the owner."""
        conversation = await self.db.scalar(self._with_tags().where(Conversation.id == conversation_id))
        if conversation is None:
            raise NotFoundError(resource="Conversation", key={"id": conversation_id}, loc=("path", "conversation_id"))
        assert_owner(actor, conversation.user_id, conversation.visitor_id, loc=("path", "conversation_id"))
        return conversation

    async def start(self, data: ConversationCreate, actor: Actor) -> Conversation:
        """Creates (flushes, does not commit) a conversation owned by the logged-in user,
        or by the visitor cookie when anonymous. :raises NotFoundError: unknown location."""
        if data.location_id is not None:
            await LocationRepo(self.db).get_one(id=data.location_id, key_loc="body")
        conversation = Conversation(
            user_id=actor.user.id if actor.user is not None else None,
            visitor_id=None if actor.user is not None else actor.visitor_id,
            kind=data.kind,
            location_id=data.location_id,
            last_activity_at=_now(),
        )
        self.db.add(conversation)
        await self.db.flush()
        await self.db.refresh(conversation, attribute_names=["created_at", "tags"])
        return conversation

    async def search(
            self,
            *,
            user_id: int,
            status: ConversationStatus | None = None,
            tag_id: int | None = None,
            subtag_id: int | None = None,
            q: str | None = None,
            limit: int | None = None,
            offset: int = 0,
    ) -> ItemList[ConversationModel]:
        """The user's conversations, most recently active first. `q` matches a fragment
        of the title or of any message (case-insensitive)."""
        conditions = [Conversation.user_id == user_id, Conversation.workspace.is_(False)]
        if status is not None:
            conditions.append(Conversation.status == status)
        if tag_id is not None or subtag_id is not None:
            tagged = select(ConversationTag.id).where(ConversationTag.conversation_id == Conversation.id)
            if tag_id is not None:
                tagged = tagged.where(ConversationTag.tag_id == tag_id)
            if subtag_id is not None:
                tagged = tagged.where(ConversationTag.subtag_id == subtag_id)
            conditions.append(exists(tagged))
        if q:
            in_messages = select(Message.id).where(
                Message.conversation_id == Conversation.id,
                Message.content.icontains(q, autoescape=True),
            )
            conditions.append(or_(Conversation.title.icontains(q, autoescape=True), exists(in_messages)))

        total = await self.db.scalar(select(func.count()).select_from(Conversation).where(*conditions))
        query = (
            self._with_tags().where(*conditions)
            .order_by(Conversation.last_activity_at.desc(), Conversation.id.desc())
            .offset(offset).limit(limit)
        )
        items = (await self.db.scalars(query)).all()
        return ItemList[ConversationModel](total=total, items=[*items])

    async def update_conversation(self, conversation: Conversation, changes: ConversationUpdate) -> Conversation:
        """:raises ValidationError: a title for an anonymous conversation. :raises NotFoundError: unknown location."""
        data = changes.model_dump_null()
        if data.get("title") is not None and not conversation.saved:
            raise ValidationError(
                msg="Anonymous conversations keep no title.", loc=("body", "title"), input_=data["title"],
            )
        if data.get("location_id") is not None:
            await LocationRepo(self.db).get_one(id=data["location_id"], key_loc="body")
        for key, value in data.items():
            setattr(conversation, key, value)
        await self.db.commit()
        return await self.get_reloaded(conversation.id)

    async def get_reloaded(self, conversation_id: int) -> Conversation:
        return await self.db.scalar(self._with_tags().where(Conversation.id == conversation_id))

    async def detail(self, conversation: Conversation) -> ConversationDetail:
        messages = (await self.db.scalars(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id)
        )).all()
        matches = (await self.db.scalars(
            select(ProjectMatch).where(ProjectMatch.conversation_id == conversation.id).order_by(ProjectMatch.id)
        )).all()
        return ConversationDetail(
            **ConversationModel.model_validate(conversation).model_dump(),
            messages=[MessageModel.model_validate(m) for m in messages],
            projects=await ProjectMatchRepo(self.db).models(matches),
        )

    # ============ chat turn ============

    async def saved_history(self, conversation_id: int) -> list[ChatTurn]:
        """The last stored messages of a saved conversation, oldest first."""
        rows = (await self.db.scalars(
            select(Message).where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc()).limit(SAVED_HISTORY_MESSAGES)
        )).all()
        return [ChatTurn(role=m.role.value, content=m.content) for m in reversed(rows)]

    async def user_text(self, conversation_id: int) -> str:
        """All saved user turns for topic labeling, never assistant suggestions."""
        contents = (await self.db.scalars(select(Message.content).where(
            Message.conversation_id == conversation_id, Message.role == MessageRole.user,
        ).order_by(Message.id))).all()
        return "\n".join(contents)

    async def tag_options(self) -> list[TagOption]:
        """The admin's tag list for the chat engine."""
        return [
            TagOption(
                id=tag.id, name=tag.name, description=tag.description,
                subtags=tuple(SubtagOption(id=s.id, name=s.name, description=s.description) for s in tag.subtags),
            )
            for tag in await TagRepo(self.db).get_all_nested()
        ]

    async def save_turn(
            self,
            conversation: Conversation,
            *,
            user_message: str,
            content: str,
            sources: Sequence[SourceHit],
            tag_assignments: Sequence[TagAssignment] | None,
            project_ids: Sequence[int],
            outcome,
            title: str | None,
            tags: Sequence[TagOption],
            preserve_ai_tags: bool = False,
    ) -> tuple[Message | None, list[ProjectMatch]]:
        """
        Stores the result of one answer and commits:

        - saved conversations: the user and assistant messages, and the title when it has none;
          anonymous ones: no message, no title;
        - replaces the AI-assigned tags (manual tags stay), keeping only pairs from ``tags``;
        - adds a match per recommended published project not matched in this conversation yet;
        - sets ``outcome`` and ``last_activity_at``.

        Returns the assistant message (None when anonymous) and the matches of ``project_ids``.
        """
        assistant = None
        if conversation.saved:
            self.db.add(Message(conversation_id=conversation.id, role=MessageRole.user, content=user_message))
            assistant = Message(
                conversation_id=conversation.id, role=MessageRole.assistant, content=content,
                sources=[hit.as_source() for hit in sources],
            )
            self.db.add(assistant)
            if not conversation.title and title:
                conversation.title = title[:200]

        if tag_assignments is not None:
            await self._replace_ai_tags(conversation.id, _valid_assignments(tag_assignments, tags), replace=not preserve_ai_tags)
        matches = await ProjectMatchRepo(self.db).add_matches(conversation.id, project_ids)
        conversation.outcome = outcome
        conversation.last_activity_at = _now()
        await self.db.commit()
        if assistant is not None:
            await self.db.refresh(assistant)
        return assistant, matches

    async def _replace_ai_tags(self, conversation_id: int, assignments: Sequence[TagAssignment], *, replace: bool = True) -> None:
        if replace:
            await self.db.execute(delete(ConversationTag).where(
                ConversationTag.conversation_id == conversation_id, ConversationTag.source == TagSource.ai,
            ))
        manual = set((await self.db.execute(
            select(ConversationTag.tag_id, ConversationTag.subtag_id)
            .where(ConversationTag.conversation_id == conversation_id)
        )).tuples().all())
        for item in assignments:
            if (item.tag_id, item.subtag_id) not in manual:
                self.db.add(ConversationTag(
                    conversation_id=conversation_id, tag_id=item.tag_id, subtag_id=item.subtag_id, source=TagSource.ai,
                ))
        await self.db.flush()

    async def tags_of(self, conversation_id: int) -> list[ConversationTagModel]:
        rows = (await self.db.scalars(
            select(ConversationTag).where(ConversationTag.conversation_id == conversation_id).order_by(ConversationTag.id)
        )).all()
        return [ConversationTagModel.model_validate(r) for r in rows]

    async def replace_tags(self, conversation_id: int, items: Sequence[ConversationTagInput]) -> list[ConversationTagModel]:
        """
        Replaces all tags of the conversation with ``items`` as manual tags (later answers
        keep them). :raises NotFoundError: unknown tag or subtag.
        :raises ValidationError: a subtag of another tag, or a pair listed twice.
        """
        seen: set[tuple[int, int | None]] = set()
        for i, item in enumerate(items):
            loc = ("body", i)
            await TagRepo(self.db).get_one(id=item.tag_id, key_loc="body")
            if item.subtag_id is not None:
                subtag = await self.db.get(Subtag, item.subtag_id)
                if subtag is None:
                    raise NotFoundError(resource="Subtag", key={"id": item.subtag_id}, loc=(*loc, "subtag_id"))
                if subtag.tag_id != item.tag_id:
                    raise ValidationError(
                        msg=f"Subtag {subtag.id} does not belong to tag {item.tag_id}.",
                        loc=(*loc, "subtag_id"), input_=subtag.id,
                    )
            key = (item.tag_id, item.subtag_id)
            if key in seen:
                raise ValidationError(msg=f"Tag pair {key} is listed twice.", loc=loc, input_=item.model_dump())
            seen.add(key)

        await self.db.execute(delete(ConversationTag).where(ConversationTag.conversation_id == conversation_id))
        for tag_id, subtag_id in seen:
            self.db.add(ConversationTag(
                conversation_id=conversation_id, tag_id=tag_id, subtag_id=subtag_id, source=TagSource.manual,
            ))
        await self.db.commit()
        return await self.tags_of(conversation_id)


def _valid_assignments(assignments: Sequence[TagAssignment], tags: Sequence[TagOption]) -> list[TagAssignment]:
    """Keeps the engine's assignments that exist in the admin's list, once each, in order."""
    allowed: set[tuple[int, int | None]] = set()
    for tag in tags:
        allowed.add((tag.id, None))
        allowed.update((tag.id, s.id) for s in tag.subtags)
    result, seen = [], set()
    for item in assignments:
        key = (item.tag_id, item.subtag_id)
        if key in allowed and key not in seen:
            seen.add(key)
            result.append(TagAssignment(*key))
    return result


class ProjectMatchRepo(CRUDRepo[ProjectMatch, ProjectMatchModel]):

    async def add_matches(self, conversation_id: int, project_ids: Sequence[int]) -> list[ProjectMatch]:
        """Matches of ``project_ids`` (in that order, published projects only), creating the
        missing ones. A project is matched once per conversation. Flushes, does not commit."""
        wanted = list(dict.fromkeys(project_ids))
        if not wanted:
            return []
        published = set((await self.db.scalars(
            select(Project.id).where(Project.id.in_(wanted), Project.status == ProjectStatus.published)
        )).all())
        existing = {m.project_id: m for m in (await self.db.scalars(
            select(ProjectMatch).where(ProjectMatch.conversation_id == conversation_id, ProjectMatch.project_id.in_(wanted))
        )).all()}
        result = []
        for project_id in wanted:
            if project_id not in published:
                continue
            match = existing.get(project_id)
            if match is None:
                match = ProjectMatch(conversation_id=conversation_id, project_id=project_id, opened=False)
                self.db.add(match)
            result.append(match)
        await self.db.flush()
        for match in result:
            await self.db.refresh(match, attribute_names=["created_at"])
        return result

    async def models(self, matches: Sequence[ProjectMatch]) -> list[ProjectMatchModel]:
        """Matches with their project cards."""
        ids = {m.project_id for m in matches}
        projects = {p.id: p for p in (await self.db.scalars(select(Project).where(Project.id.in_(ids)))).all()} if ids else {}
        return [
            ProjectMatchModel(
                id=m.id, project_id=m.project_id, conversation_id=m.conversation_id, opened=m.opened,
                created_at=m.created_at, project=ProjectModel.model_validate(projects[m.project_id]),
            )
            for m in matches
        ]

    async def open_match(self, match_id: int, actor: Actor) -> ProjectMatchModel:
        """Marks the match as opened by the owner of its conversation.
        :raises NotFoundError: missing. :raises ForbiddenError: not the owner."""
        match = await self.get_one(id=match_id, key_loc="path")
        conversation = await self.db.get(Conversation, match.conversation_id)
        assert_owner(actor, conversation.user_id, conversation.visitor_id, loc=("path", "match_id"))
        if not match.opened:
            match.opened = True
            await self.db.commit()
        return (await self.models([match]))[0]
