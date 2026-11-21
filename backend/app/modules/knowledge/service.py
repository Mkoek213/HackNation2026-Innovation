import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Any

from anyio import to_thread
from qdrant_client import models

from app.database.database import sessionmanager
from app.repos.conversation_repo import ConversationRepo
from app.schemas.tagging import AssignedLabel, Classification
from app.services.tagging import classify, assignments

from .documents import DocumentStorage
from .chunking import chunk_blocks
from .embeddings import Embedder, GeminiEmbedder
from .errors import InnovationNotFound, KnowledgeUnavailable
from .extract import SUPPORTED_SUFFIXES, dedupe_formats, expand_archives, extract
from .schemas import (
    CategoriesUpdate,
    CatalogPage,
    Evidence,
    IngestResult,
    InnovationArea,
    InnovationAssessment,
    InnovationCard,
    InnovationMeta,
    InnovationSummary,
    InnovationUpdate,
    RetrievedInnovation,
    StoredDocument,
)
from .settings import KnowledgeSettings, load_knowledge_settings
from .store import PointData, QdrantStore, make_client, meta_to_card_payload, point_id
from .taxonomy import (CATEGORY_LABELS, INNOVATION_TYPE_LABELS, INSTITUTION_TYPE_LABELS, MATURITY_LABELS,
                       Category, Maturity)

logger = logging.getLogger(__name__)

_RRF_K = 60
# Stage-1 ranking weights. Card and summary are short, curated and equally sized for every innovation;
# full materials only add recall for terms that appear nowhere else, so long reports cannot dominate.
_RANKING_WEIGHTS = {"card": 1.0, "card_terms": 0.7, "summary": 1.0, "full": 0.5}


async def document_tag_options():
    if sessionmanager.session_maker is None:
        return []
    async with sessionmanager.session_maker() as db:
        return await ConversationRepo(db).tag_options()


def card_text(meta: InnovationMeta) -> str:
    c = meta.card
    parts = [
        meta.title,
        "Sektory: " + ", ".join(CATEGORY_LABELS[cat] for cat in meta.categories),
        f"Rodzaj innowacji: {INNOVATION_TYPE_LABELS[meta.innovation_type]}" if meta.innovation_type else "",
        f"Źródło: {INSTITUTION_TYPE_LABELS[meta.institution_type]}" if meta.institution_type else "",
        f"Instytucja: {meta.institution}" if meta.institution else "",
        f"Poziom wdrożenia: {MATURITY_LABELS[meta.maturity]}" if meta.maturity else "",
        f"Problem: {c.problem}" if c.problem else "",
        f"Na czym polega: {c.solution}" if c.solution else "",
        f"Nowość: {c.novelty}" if c.novelty else "",
        f"Dla kogo: {c.target_users}" if c.target_users else "",
        f"Stan i dowody: {c.evidence}" if c.evidence else "",
        f"Streszczenie: {meta.assessment.summary}" if meta.assessment.summary else "",
    ]
    return "\n".join(p for p in parts if p)


def chunk_text(title: str, section: str | None, doc_type: str, text: str) -> str:
    """Embedded text carries a context header; the stored text stays verbatim."""
    return f"{title} | {section or doc_type}\n{text}"


def evidence_from_payload(payload: dict, documents: list[StoredDocument]) -> Evidence:
    """Resolve exact current IDs only; legacy filenames are never used as identity."""
    document = next((d for d in documents if d.id == payload.get("document_id")), None)
    page = payload.get("page_start")
    page_url = (f"{document.download_url}#page={page}"
                if document and page and document.content_type == "application/pdf" else None)
    return Evidence(
        role=payload.get("role", "full"), page_url=page_url,
        text=payload["text"], doc_type=payload["doc_type"], section=payload.get("section"),
        source_file=payload.get("source_file"), page_start=payload.get("page_start"), page_end=payload.get("page_end"),
        document_id=document.id if document else None,
        document_url=document.download_url if document else None,
        content_type=document.content_type if document else None,
    )


class KnowledgeService:
    def __init__(self, store: QdrantStore, embedder: Embedder, settings: KnowledgeSettings):
        self.store = store
        self.embedder = embedder
        self.settings = settings
        self.documents = DocumentStorage(settings)
        # ponytail: process-local serialization; distributed locks if multiple writers are deployed.
        self._write_lock = asyncio.Lock()

    @classmethod
    async def create(cls, settings: KnowledgeSettings, embedder: Embedder | None = None) -> "KnowledgeService":
        if not settings.qdrant_url:
            raise KnowledgeUnavailable("Knowledge base is not configured (set QDRANT_URL).")
        if embedder is None:
            embedder = GeminiEmbedder(settings.gemini_api_key, settings.embedding_model, settings.embedding_dimensions)
        client = make_client(settings.qdrant_url, settings.qdrant_api_key)
        store = QdrantStore(client, settings.qdrant_collection, embedder.dense_dim)
        try:
            await store.ensure_collection()
        except Exception as e:
            await client.close()
            await embedder.aclose()
            logger.exception("Qdrant unavailable")
            raise KnowledgeUnavailable("Knowledge base is unreachable.") from e
        return cls(store, embedder, settings)

    async def close(self) -> None:
        await self.store.client.close()
        await self.embedder.aclose()

    # ---------- writes ----------

    async def ingest(self, meta: InnovationMeta, files: list[Path], workdir: Path,
                     summary: Path | None = None) -> IngestResult:
        """Extract, chunk and embed everything first; only then replace the indexed version,
        so a failing upload never removes the previously published innovation.
        `summary` is the innovation's short overview (PDF/DOCX); `files` are its full materials."""
        async with self._write_lock:
            return await self._ingest(meta, files, workdir, summary)

    async def _ingest(self, meta: InnovationMeta, files: list[Path], workdir: Path,
                      summary: Path | None = None, import_baseline: dict | None = None) -> IngestResult:
        if summary is not None and summary.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError("Summary must be a PDF or DOCX file.")
        expanded = await to_thread.run_sync(
            lambda: expand_archives(files, workdir, max_bytes=self.settings.max_upload_mb * 1024 * 1024)
        )
        if summary is not None:  # the same file sent twice is the summary, not a full material
            expanded = [p for p in expanded if p.name != summary.name]
            expanded.insert(0, summary)
        role_of = {path: ("summary" if path == summary else "full") for path in expanded}
        stored_by_path = {path: self.documents.describe(meta.id, path, role_of[path]) for path in expanded
                          if path.suffix.lower() in SUPPORTED_SUFFIXES}
        candidates = dedupe_formats(expanded)
        documents, skipped = [], []
        for path in candidates:
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                skipped.append(path.name)
                continue
            doc = await to_thread.run_sync(extract, path)
            (documents.append(doc) if doc else skipped.append(path.name))

        previous = await self.store.get_innovation(meta.id)
        if previous:
            meta = self._with_discovery_fields(previous, meta)
        for path, stored_doc in stored_by_path.items():
            def digest():
                with path.open("rb") as stream:
                    return hashlib.file_digest(stream, "sha256").hexdigest()
            stored_doc.content_sha256 = await to_thread.run_sync(digest)
            old = next((d for d in previous.documents if d.content_sha256 == stored_doc.content_sha256), None) if previous else None
            if old:
                stored_doc.tags = old.tags
        # The same administrator-defined taxonomy is used for document and conversation statistics.
        tag_options = await document_tag_options() if documents else []
        for doc in documents:
            stored_by_path[doc.path].classification = await classify(
                "\n".join(block.text for block in doc.blocks), tag_options, purpose="document",
            )
            stored_doc = stored_by_path[doc.path]
            if stored_doc.classification.status in {"completed", "uncertain"}:
                retained = [t for t in stored_doc.tags if t.source == "manual" or stored_doc.classification.status == "uncertain"]
                retained_pairs = {(t.tag_id, t.subtag_id) for t in retained}
                stored_doc.tags = retained + [AssignedLabel(tag_id=t.tag_id, subtag_id=t.subtag_id)
                                          for t in assignments(stored_doc.classification)
                                          if (t.tag_id, t.subtag_id) not in retained_pairs]
        for stored_doc in stored_by_path.values():
            if stored_doc.classification is None:
                stored_doc.classification = Classification(status="no_text")

        texts: list[str] = [card_text(meta)]
        ids: list[str] = [point_id(meta.id, "card")]
        payloads: list[dict[str, Any]] = []
        base = {
            "kind": "chunk",
            "innovation_id": meta.id,
            "title": meta.title,
            "categories": [c.value for c in meta.categories],
            "primary_category": meta.primary_category.value,
            "verification": meta.verification,
        }
        for doc in documents:
            for i, chunk in enumerate(chunk_blocks(doc.blocks)):
                texts.append(chunk_text(meta.title, chunk.section, doc.doc_type, chunk.text))
                ids.append(point_id(meta.id, str(doc.path), str(i)))
                payloads.append({
                    **base,
                    "role": role_of[doc.path],
                    "doc_type": doc.doc_type,
                    "source_file": doc.path.name,
                    "document_id": stored_by_path[doc.path].id,
                    "document_url": stored_by_path[doc.path].download_url,
                    "content_type": stored_by_path[doc.path].content_type,
                    "section": chunk.section,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "tag_ids": list(dict.fromkeys(d.tag_id for d in stored_by_path[doc.path].tags)),
                    "subtag_ids": [d.subtag_id for d in stored_by_path[doc.path].tags if d.subtag_id is not None],
                    "chunk_index": i,
                    "text": chunk.text,
                })

        file_names = [d.path.name for d in documents]
        payloads.insert(0, meta_to_card_payload(meta, files=file_names, chunk_count=len(payloads)))
        payloads[0]["import_baseline"] = import_baseline if import_baseline is not None else (
            previous.import_baseline if previous else {}
        )
        payloads[0]["assessment_baseline"] = previous.assessment_baseline if previous else {}
        dense, sparse = await self.embedder.embed_passages(texts)
        points = [PointData(id=i, dense=d, sparse=s, payload=p) for i, d, s, p in zip(ids, dense, sparse, payloads)]
        stored = list(stored_by_path.values())
        staged = []
        try:
            for path, document in zip((p for p in expanded if p.suffix.lower() in SUPPORTED_SUFFIXES), stored):
                staged.append(document)
                await to_thread.run_sync(self.documents.upload, path, document)
        except BaseException:
            await self._cleanup(staged)
            raise
        # Field exclusion protects HTTP responses; object keys remain private persisted metadata.
        points[0].payload["documents"] = [
            {**d.model_dump(), "object_key": d.object_key} for d in stored
        ]
        # Qdrant's existing delete/upsert is not transactional. On partial publication failure,
        # retain staged objects since the new card may already reference them.
        await self.store.replace_innovation(meta.id, points)
        if previous:
            await self._cleanup(previous.documents)
        logger.info("Ingested %s: %d chunks from %d files (%d skipped)",
                    meta.id, len(points) - 1, len(file_names), len(skipped))
        indexed_summary = summary.name if summary is not None and any(d.path == summary for d in documents) else None
        return IngestResult(innovation_id=meta.id, chunks=len(points) - 1, files=file_names, skipped_files=skipped,
                            documents=stored, summary_file=indexed_summary)

    async def update(self, innovation_id: str, update: InnovationUpdate) -> InnovationSummary:
        """Edit the card and keep the indexed documents. The card is re-embedded; chunks are
        re-embedded only when the title changes, because their embedded header carries it."""
        async with self._write_lock:
            previous = await self.get(innovation_id)
            meta = self._with_discovery_fields(previous, update)
            return await self._update(previous, meta, previous.import_baseline)

    @staticmethod
    def _with_discovery_fields(previous: InnovationSummary, update: InnovationUpdate) -> InnovationMeta:
        fields = {"area", "region", "verification", "assessment", "checked_at"} - update.model_fields_set
        data = {**update.model_dump(), **previous.model_dump(include=fields)}
        data["id"] = previous.id
        return InnovationMeta.model_validate(data)

    async def _update(self, previous: InnovationSummary, meta: InnovationMeta, baseline: dict,
                      assessment_baseline: dict | None = None) -> InnovationSummary:
        payload = meta_to_card_payload(meta, files=previous.files, chunk_count=previous.chunk_count)
        payload["documents"] = [{**d.model_dump(), "object_key": d.object_key} for d in previous.documents]
        payload["import_baseline"] = baseline
        payload["assessment_baseline"] = previous.assessment_baseline if assessment_baseline is None else assessment_baseline
        fields = {"title": meta.title, "categories": [c.value for c in meta.categories],
                  "primary_category": meta.primary_category.value, "verification": meta.verification}
        text = card_text(meta)
        if text == card_text(previous):
            await self.store.set_card_fields(meta.id, payload)
            if meta.verification != previous.verification:
                await self.store.set_chunk_fields(meta.id, fields)
        else:
            chunks = await self.store.chunks(meta.id) if meta.title != previous.title else []
            texts = [text] + [
                chunk_text(meta.title, p.get("section"), p["doc_type"], p["text"]) for _, p in chunks
            ]
            dense, sparse = await self.embedder.embed_passages(texts)
            payloads = [payload] + [{**p, **fields} for _, p in chunks]
            ids = [point_id(meta.id, "card")] + [i for i, _ in chunks]
            await self.store.upsert([PointData(id=i, dense=d, sparse=s, payload=p)
                                     for i, d, s, p in zip(ids, dense, sparse, payloads)])
            if not chunks and previous.chunk_count:
                await self.store.set_chunk_fields(meta.id, fields)
        return await self.get(meta.id)

    async def refresh(self, meta: InnovationMeta, workdir: Path) -> str:
        """Three-way merge: refresh fields still matching the previous import."""
        incoming = meta.model_dump(mode="json", exclude={"id", "checked_at", "imported_at"})
        async with self._write_lock:
            previous = await self.store.get_innovation(meta.id)
            if previous is None:
                await self._ingest(meta, [], workdir, import_baseline=incoming)
                return "created"
            current = previous.model_dump(mode="json", include=set(incoming))
            baseline = previous.import_baseline
            merged = {}
            for key, value in incoming.items():
                if key in {"card", "assessment"}:
                    old = baseline.get(key, {})
                    defaults = (InnovationCard() if key == "card" else InnovationAssessment()).model_dump(mode="json")
                    merged[key] = {
                        field: new if current[key][field] == old.get(field, defaults[field]) else current[key][field]
                        for field, new in value.items()
                    }
                else:
                    merged[key] = value if current[key] == baseline.get(key) else current[key]
            # Keep editorial verification as a unit when someone changed its evidence or stage.
            review = ("verification", "maturity", "area", "assessment")
            if (baseline and any(current[key] != baseline.get(key) for key in review)
                    or not baseline and previous.verification == "potwierdzona"):
                merged.update({key: current[key] for key in review})
            elif not baseline and previous.verification == "kandydat":
                merged["verification"] = current["verification"]
            updated = InnovationMeta(id=meta.id, **merged, imported_at=previous.imported_at, checked_at=meta.checked_at)
            changed = current != updated.model_dump(mode="json", include=set(incoming))
            if changed or baseline != incoming or updated.checked_at != previous.checked_at:
                await self._update(previous, updated, incoming)
            return "updated" if changed else "unchanged"

    async def apply_assessment(self, innovation_id: str, proposed: InnovationAssessment,
                               maturity: Maturity | None) -> InnovationSummary:
        """Three-way merge of an automatic assessment: a field is replaced only while it is empty or
        still equals the previous automatic proposal, so editorial and source-confirmed notes survive."""
        async with self._write_lock:
            previous = await self.get(innovation_id)
            defaults = InnovationAssessment().model_dump(mode="json")
            current = previous.assessment.model_dump(mode="json")
            old = previous.assessment_baseline.get("assessment", defaults)
            new = proposed.model_dump(mode="json")
            merged = {field: value if current[field] in (defaults[field], old.get(field, defaults[field])) else current[field]
                      for field, value in new.items()}
            merged.update(criteria_version=new["criteria_version"], assessed_at=new["assessed_at"])
            # A kept editorial or source note without a score takes the automatic score; its text and basis stay.
            for field in ("implementation", "novelty", "transfer", "credibility"):
                if merged[field] and merged[field].get("score") is None and (new.get(field) or {}).get("score"):
                    merged[field] = {**merged[field], "score": new[field]["score"]}
            data = previous.model_dump(include=set(InnovationMeta.model_fields))
            data["assessment"] = merged
            old_maturity = previous.assessment_baseline.get("maturity")
            # Confirmed cards keep their documented stage; candidates take the estimate unless an editor set one.
            if maturity and previous.verification == "kandydat" and (previous.maturity or None) in (None, old_maturity):
                data["maturity"] = maturity
            meta = InnovationMeta.model_validate(data)
            baseline = {"assessment": new, "maturity": maturity.value if maturity else None}
            return await self._update(previous, meta, previous.import_baseline, assessment_baseline=baseline)

    async def update_categories(self, innovation_id: str, update: CategoriesUpdate) -> InnovationSummary:
        async with self._write_lock:
            await self.get(innovation_id)
            await self.store.set_categories(innovation_id, update.categories, update.primary_category)
            return await self.get(innovation_id)

    async def _cleanup(self, documents: list[StoredDocument]) -> None:
        if not documents:
            return
        try:
            await to_thread.run_sync(self.documents.delete, documents)
        except Exception:
            logger.exception("Document cleanup failed; unreferenced objects may remain in S3")

    async def delete(self, innovation_id: str) -> None:
        async with self._write_lock:
            previous = await self.get(innovation_id)
            await self.store.delete_innovation(innovation_id)
            await self._cleanup(previous.documents)

    # ---------- reads ----------

    async def get(self, innovation_id: str) -> InnovationSummary:
        found = await self.store.get_innovation(innovation_id)
        if found is None:
            raise InnovationNotFound(innovation_id)
        return found

    async def list_innovations(self, category: Category | None = None) -> list[InnovationSummary]:
        """Every card, including unreviewed submissions (admin listing)."""
        return await self.store.list_innovations(category, include_submitted=True)

    async def catalog(self, *, query: str, category: Category | None, area: InnovationArea | None,
                      region: str | None, maturity: Maturity | None, confirmed_only: bool,
                      min_credibility: int | None, offset: int, limit: int) -> CatalogPage:
        # shortcut: substring search scans matching cards; add indexed text search when the catalog passes ~10k cards.
        items = await self.store.list_innovations(category, confirmed_only=confirmed_only)
        regions = sorted({item.region for item in items if item.region})
        terms = query.casefold().split()

        def score(item: InnovationSummary, criterion: str) -> int:
            note = getattr(item.assessment, criterion)
            return note.score or 0 if note else 0

        matches = []
        for item in items:
            if (area and item.area != area) or (region and item.region != region) or (maturity and item.maturity != maturity):
                continue
            if min_credibility and score(item, "credibility") < min_credibility:
                continue
            text = " ".join([item.title, item.institution or "", item.assessment.summary,
                             *item.card.model_dump().values()]).casefold()
            if all(term in text for term in terms):
                matches.append(item)
        # Strongest evidence first: confirmed use, then credibility, then deployment level.
        matches.sort(key=lambda item: (item.verification != "potwierdzona", -score(item, "credibility"),
                                       -score(item, "implementation"), item.title))
        return CatalogPage(items=matches[offset:offset + limit], total=len(matches), regions=regions)

    async def retrieve(
            self,
            query: str,
            *,
            categories: list[Category] | None = None,
            pool: int = 10,
            confirmed_only: bool = False,
    ) -> list[RetrievedInnovation]:
        """Two-stage retrieval.

        1. Which innovations fit: weighted reciprocal-rank fusion of the card ranking (dense),
           the summary ranking (dense + BM25) and, at half weight, the full-material ranking.
        2. Evidence: for each selected innovation, its best passages from full materials
           (one filtered query per innovation); the summary is the fallback when it has none.
        """
        dense, sparse = await self.embedder.embed_query(query)
        depth = self.settings.retrieval_prefetch
        cards, card_terms, summary_chunks, full_chunks = await asyncio.gather(
            self.store.search_cards(dense, limit=depth, categories=categories, confirmed_only=confirmed_only),
            self.store.search_cards(sparse, limit=depth, categories=categories, confirmed_only=confirmed_only),
            self.store.search_chunks(dense, sparse, limit=depth, prefetch=depth, categories=categories,
                                     role="summary", confirmed_only=confirmed_only),
            self.store.search_chunks(dense, sparse, limit=depth, prefetch=depth, categories=categories,
                                     role="full", confirmed_only=confirmed_only),
        )
        rankings = {
            "card": [i for i, _ in cards],
            "card_terms": [i for i, _ in card_terms],
            "summary": _first_per_innovation(summary_chunks),
            "full": _first_per_innovation(full_chunks),
        }
        fused: dict[str, float] = {}
        for name, ranking in rankings.items():
            for rank, innovation_id in enumerate(ranking):
                fused[innovation_id] = fused.get(innovation_id, 0.0) + _RANKING_WEIGHTS[name] / (_RRF_K + rank + 1)
        order = sorted(fused, key=fused.get, reverse=True)[:pool]
        metas = await self.store.get_innovations(order)
        order = [i for i in order if i in metas and (not confirmed_only or metas[i].verification == "potwierdzona")]

        evidence = await asyncio.gather(*(self._evidence(i, dense, sparse) for i in order))
        return [
            RetrievedInnovation(
                innovation=InnovationMeta(**metas[i].model_dump(include=set(InnovationMeta.model_fields))),
                retrieval_score=fused[i],
                summary_document=next((d for d in metas[i].documents if d.role == "summary"), None),
                evidence=[evidence_from_payload(h.payload, metas[i].documents) for h in hits],
            )
            for i, hits in zip(order, evidence)
        ]

    async def _evidence(self, innovation_id: str, dense, sparse) -> list[models.ScoredPoint]:
        n = self.settings.evidence_per_innovation
        for role in ("full", "summary"):
            hits = await self.store.search_chunks(
                dense, sparse, limit=n, prefetch=self.settings.retrieval_prefetch,
                role=role, innovation_ids=[innovation_id],
            )
            if hits:
                return hits
        return []


def _first_per_innovation(points: list[models.ScoredPoint]) -> list[str]:
    """Innovation ids in order of their best chunk."""
    return list(dict.fromkeys(p.payload["innovation_id"] for p in points))


_service: KnowledgeService | None = None
_lock = asyncio.Lock()


async def get_knowledge_service() -> KnowledgeService:
    """Lazily build the process-wide service on first use (no work at import time).
    Raises KnowledgeUnavailable when Qdrant is unconfigured or unreachable; a later call retries."""
    global _service
    if _service is None:
        async with _lock:
            if _service is None:
                _service = await KnowledgeService.create(load_knowledge_settings())
    return _service


async def warm_up() -> None:
    """Build the service and check Qdrant and the embedding API ahead of the first request. No-op without QDRANT_URL."""
    if not load_knowledge_settings().qdrant_url:
        return
    try:
        service = await get_knowledge_service()
        await service.embedder.embed_query("rozgrzewka")
        logger.info("Knowledge base ready (collection %s)", service.settings.qdrant_collection)
    except Exception:
        logger.exception("Knowledge warm-up failed; requests will retry")
