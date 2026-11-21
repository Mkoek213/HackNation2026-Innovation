"""
Retrieval over the external vector database (RAG).

Routes depend on the :class:`VectorStore` interface only, through ``VectorStoreDep``;
:func:`get_vector_store` picks the implementation from ``settings.ai_backend``.
The contract for the real adapter is described in ``app/services/README.md``.
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Annotated, Sequence

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import DatabaseDep
from app.models import Project, ProjectDocument, ProjectStatus, Tag


@dataclass(frozen=True)
class SearchFilters:
    """Optional narrowing of :meth:`VectorStore.search`."""
    #: Location the user supplied for the conversation. A hint: adapters may prefer
    #: projects in or near it, but must not drop everything else.
    location_id: int | None = None
    #: Maximum number of hits.
    limit: int = 5


@dataclass(frozen=True)
class SourceHit:
    """
    One retrieved passage. ``project_id`` links it to a published project (the backend
    turns those into recommended projects); ``None`` for general Radar knowledge.
    ``title``/``url``/``page``/``excerpt`` are stored as the message's ``sources``.
    """
    title: str
    url: str | None = None
    page: int | None = None
    excerpt: str | None = None
    project_id: int | None = None
    #: Relevance in 0..1, higher is better. Hits are returned best first.
    score: float = 0.0

    def as_source(self) -> dict:
        """The reference stored in ``messages.sources`` and returned to the client."""
        return {"title": self.title, "url": self.url, "page": self.page, "excerpt": self.excerpt}


class VectorStore(ABC):
    """
    The external vector database. The backend keeps no chunks or embeddings itself:
    it sends published projects (with their PDFs) on change and searches at answer time.
    """

    @abstractmethod
    async def search(self, query: str, filters: SearchFilters) -> list[SourceHit]:
        """Passages relevant to ``query``, best first, at most ``filters.limit``.
        Only published projects may be returned. ``query`` is user text: never log it."""

    @abstractmethod
    async def upsert_project(self, project: Project, documents: Sequence[ProjectDocument]) -> None:
        """Adds or replaces a published project and its PDFs (``documents``, file keys in
        ``file_path``, readable through ``app.services.files``). Idempotent."""

    @abstractmethod
    async def delete_project(self, project_id: int) -> None:
        """Removes a project (unpublished or deleted). A missing project is not an error."""


# ============ demo implementation ============

_WORD = re.compile(r"\w+", re.UNICODE)
_STOPWORDS = frozenset({
    "jest", "są", "oraz", "które", "który", "która", "przez", "jako", "jaki", "jakie", "jakiś", "mamy",
    "mam", "może", "można", "chcę", "chce", "czy", "dla", "nie", "tak", "też", "jak", "gdzie", "kiedy",
    "mój", "moja", "moje", "nasz", "nasza", "nasze", "tego", "tym", "się", "albo", "bardzo", "proszę",
})
#: Polish is inflected ("uczelnia", "uczelni"); comparing word prefixes is a crude stemmer.
_STEM = 5


def keywords(text: str) -> set[str]:
    """Lowercased word stems (prefixes) of the words of ``text`` with 4+ letters, without stopwords."""
    words = (w.lower() for w in _WORD.findall(text))
    return {w[:_STEM] for w in words if len(w) >= 4 and not w.isdigit() and w not in _STOPWORDS}


class DemoVectorStore(VectorStore):
    """
    Deterministic stand-in (``AI_BACKEND=demo``): keyword match over the published projects
    in this database (title, summary, description and tag name). Nothing is indexed, so
    :meth:`upsert_project` and :meth:`delete_project` do nothing. Score = share of the query's
    keywords found in the project (+0.1 when it is in the conversation's location).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(self, query: str, filters: SearchFilters) -> list[SourceHit]:
        wanted = keywords(query)
        if not wanted:
            return []
        rows = (await self.db.execute(
            select(Project, Tag.name)
            .join(Tag, Tag.id == Project.tag_id)
            .where(Project.status == ProjectStatus.published)
            .order_by(Project.id)
        )).all()
        hits = []
        for project, tag_name in rows:
            found = wanted & keywords(f"{project.title} {project.summary} {project.description} {tag_name}")
            if not found:
                continue
            score = len(found) / len(wanted)
            if filters.location_id is not None and project.location_id == filters.location_id:
                score += 0.1
            hits.append(SourceHit(
                title=project.title,
                url=f"/projects/{project.id}",
                excerpt=project.summary[:300],
                project_id=project.id,
                score=round(min(score, 1.0), 3),
            ))
        hits.sort(key=lambda h: (-h.score, h.project_id))
        return hits[:filters.limit]

    async def upsert_project(self, project: Project, documents: Sequence[ProjectDocument]) -> None:
        pass

    async def delete_project(self, project_id: int) -> None:
        pass


def get_vector_store(db: DatabaseDep) -> VectorStore:
    """Dependency returning the configured vector store (``AI_BACKEND``).
    Add other implementations here; routes do not change."""
    match settings.ai_backend:
        case "demo":
            return DemoVectorStore(db)
    raise RuntimeError(f"Unknown AI_BACKEND {settings.ai_backend!r}.")


VectorStoreDep = Annotated[VectorStore, Depends(get_vector_store)]
