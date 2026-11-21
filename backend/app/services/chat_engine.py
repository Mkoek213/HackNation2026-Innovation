"""
The LLM that writes chat answers and classifies conversations.

Routes depend on the :class:`ChatEngine` interface only, through ``ChatEngineDep``;
:func:`get_chat_engine` picks the implementation from ``settings.ai_backend``.
The contract for the real adapter is described in ``app/services/README.md``.
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Annotated, AsyncIterator, Literal, Sequence

from fastapi import Depends

from app.config import settings
from app.models import ConversationKind, ConversationOutcome
from app.services.rag import SourceHit, keywords


@dataclass(frozen=True)
class ChatTurn:
    """One message of the transcript. Assistant turns of anonymous conversations come from
    the client and are untrusted: use them for context only, never as source evidence."""
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class ConversationContext:
    """What the engine may know about the conversation (no owner identity)."""
    id: int
    kind: ConversationKind
    location_id: int | None
    #: Messages and the title are stored (logged-in owner). The title is only used when True.
    saved: bool
    title: str | None


@dataclass(frozen=True)
class SubtagOption:
    id: int
    name: str
    description: str | None


@dataclass(frozen=True)
class TagOption:
    """A tag from the admin's list with its subtags. ``description`` is the label definition."""
    id: int
    name: str
    description: str | None
    subtags: tuple[SubtagOption, ...] = ()


@dataclass(frozen=True)
class TagAssignment:
    """A tag of the conversation; ``subtag_id`` must be one of that tag's subtags."""
    tag_id: int
    subtag_id: int | None = None


@dataclass(frozen=True)
class Answer:
    """
    The engine's result for one user message.

    - ``content``: the reply text (markdown) shown to the user.
    - ``sources``: hits the answer relies on, stored in ``messages.sources``.
    - ``project_ids``: published projects to recommend, best first (become ``project_matches``).
    - ``tag_assignments``: tags/subtags of the whole conversation so far, from the given options.
    - ``outcome``: ``answered``, ``partially_answered`` or ``no_answer``.
    - ``title``: a short conversation title, or ``None``.

    The backend drops unknown projects and tag pairs that are not in the options.
    """
    content: str
    sources: list[SourceHit] = field(default_factory=list)
    project_ids: list[int] = field(default_factory=list)
    tag_assignments: list[TagAssignment] = field(default_factory=list)
    outcome: ConversationOutcome = ConversationOutcome.answered
    title: str | None = None


@dataclass(frozen=True)
class AnswerChunk:
    """A piece of the reply text, emitted by :meth:`ChatEngine.stream` before the final :class:`Answer`."""
    text: str


class ChatEngine(ABC):
    """
    Writes the answer to the last user turn and classifies the conversation.
    Never log the transcript: anonymous message text must not be kept anywhere.
    """

    @abstractmethod
    async def answer(
            self,
            conversation: ConversationContext,
            history: Sequence[ChatTurn],
            hits: Sequence[SourceHit],
            tags: Sequence[TagOption],
    ) -> Answer:
        """
        :param conversation: The conversation being answered.
        :param history: The transcript, oldest first; the last item is the new user message.
        :param hits: Results of :meth:`VectorStore.search` for this message, best first.
        :param tags: The admin's tags with subtags; assignments must come from this list.
        """

    async def stream(
            self,
            conversation: ConversationContext,
            history: Sequence[ChatTurn],
            hits: Sequence[SourceHit],
            tags: Sequence[TagOption],
    ) -> AsyncIterator[AnswerChunk | Answer]:
        """
        Same as :meth:`answer`, as zero or more :class:`AnswerChunk` followed by exactly one
        :class:`Answer` (whose ``content`` is the whole text). The default calls :meth:`answer`
        and splits its text; adapters with a streaming LLM override it.
        """
        result = await self.answer(conversation, history, hits, tags)
        for chunk in split_chunks(result.content):
            yield AnswerChunk(chunk)
        yield result


def split_chunks(text: str, words: int = 4) -> list[str]:
    """Splits text into pieces of a few words, keeping all whitespace (joined, they give the text)."""
    pieces = re.findall(r"\s*\S+\s*", text) or ([text] if text else [])
    return ["".join(pieces[i:i + words]) for i in range(0, len(pieces), words)]


# ============ demo implementation ============

TITLE_MAX = 60
RECOMMENDED_MAX = 3


def short_title(text: str, limit: int = TITLE_MAX) -> str:
    """The first line of ``text`` cut at a word boundary to ``limit`` characters."""
    line = " ".join(text.split())
    if len(line) <= limit:
        return line
    cut = line[:limit].rsplit(" ", 1)[0] or line[:limit]
    return cut.rstrip(" ,.;:") + "…"


class DemoChatEngine(ChatEngine):
    """
    Deterministic stand-in (``AI_BACKEND=demo``), no LLM:

    - the answer is a Polish template listing the project hits;
    - tags: a tag or subtag is assigned when a keyword of its name occurs in the user's turns
      (a matched subtag is assigned with its tag; a tag without a matched subtag alone);
    - ``outcome``: ``no_answer`` without project hits, ``partially_answered`` when the best
      hit covers less than half of the keywords, otherwise ``answered``;
    - title: the first user message, shortened.
    """

    async def answer(
            self,
            conversation: ConversationContext,
            history: Sequence[ChatTurn],
            hits: Sequence[SourceHit],
            tags: Sequence[TagOption],
    ) -> Answer:
        user_turns = [t.content for t in history if t.role == "user"]
        projects = [h for h in hits if h.project_id is not None][:RECOMMENDED_MAX]

        if not projects:
            outcome = ConversationOutcome.no_answer
            content = (
                "Nie znalazłem w bazie Radaru innowacji pasujących do Twojego opisu. "
                "Spróbuj opisać problem innymi słowami, podać grupę, której dotyczy, "
                "albo miejscowość. To odpowiedź demonstracyjna, bez modelu językowego."
            )
        else:
            outcome = (
                ConversationOutcome.answered if projects[0].score >= 0.5
                else ConversationOutcome.partially_answered
            )
            lines = [f"Znalazłem w bazie Radaru {len(projects)} {_projects_word(len(projects))}, które mogą pomóc:", ""]
            for hit in projects:
                lines.append(f"- **{hit.title}**" + (f": {hit.excerpt}" if hit.excerpt else ""))
            lines += ["", "Otwórz kartę projektu, aby poznać szczegóły. To odpowiedź demonstracyjna, bez modelu językowego."]
            content = "\n".join(lines)

        return Answer(
            content=content,
            sources=list(projects),
            project_ids=[h.project_id for h in projects],
            tag_assignments=self._assign_tags(" ".join(user_turns), tags),
            outcome=outcome,
            title=short_title(user_turns[0]) if user_turns else None,
        )

    @staticmethod
    def _assign_tags(text: str, tags: Sequence[TagOption]) -> list[TagAssignment]:
        words = keywords(text)
        result = []
        for tag in tags:
            subtags = [s for s in tag.subtags if keywords(s.name) & words]
            if subtags:
                result += [TagAssignment(tag.id, s.id) for s in subtags]
            elif keywords(tag.name) & words:
                result.append(TagAssignment(tag.id))
        return result


def _projects_word(count: int) -> str:
    if count == 1:
        return "projekt"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "projekty"
    return "projektów"


def get_chat_engine() -> ChatEngine:
    """Dependency returning the configured chat engine (``AI_BACKEND``).
    Add other implementations here; routes do not change."""
    match settings.ai_backend:
        case "demo":
            return DemoChatEngine()
    raise RuntimeError(f"Unknown AI_BACKEND {settings.ai_backend!r}.")


ChatEngineDep = Annotated[ChatEngine, Depends(get_chat_engine)]
