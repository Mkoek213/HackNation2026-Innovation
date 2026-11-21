"""Qdrant storage: one collection, two point kinds.

- kind="card":  one per innovation; payload = full InnovationMeta (+ files, chunk_count).
                Its vectors embed the curated card text -- the main matching target.
- kind="chunk": document fragments; payload carries innovation_id + categories (denormalized
                for filtering), text, section, doc_type and page span for citations.

Search runs twice: dense over cards (which innovation fits) and dense + BM25 with RRF over
chunks (evidence, exact terms). The service groups chunks by innovation and fuses both
rankings, so an innovation with many long reports does not outrank a better-fitting one
just by having more text.
"""
import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from .schemas import DocumentRole, InnovationMeta, InnovationSummary
from .taxonomy import Category

DENSE = "dense"
SPARSE = "bm25"
_NS = uuid.UUID("6f1f8a3e-2a51-4b0e-9a57-6e0c6a1f0b11")


def point_id(*parts: str) -> str:
    return str(uuid.uuid5(_NS, ":".join(parts)))


@dataclass
class PointData:
    id: str
    dense: list[float] | None
    sparse: models.SparseVector
    payload: dict[str, Any]


def make_client(url: str, api_key: str | None = None) -> AsyncQdrantClient:
    if url == ":memory:":
        return AsyncQdrantClient(location=":memory:")
    if url.startswith(("http://", "https://")):
        return AsyncQdrantClient(url=url, api_key=api_key)
    return AsyncQdrantClient(path=url)  # embedded, persisted to a directory


class QdrantStore:
    def __init__(self, client: AsyncQdrantClient, collection: str, dense_dim: int):
        self.client = client
        self.collection = collection
        self.dense_dim = dense_dim

    async def ensure_collection(self) -> None:
        if not await self.client.collection_exists(self.collection):
            await self.client.create_collection(
                self.collection,
                vectors_config={DENSE: models.VectorParams(size=self.dense_dim, distance=models.Distance.COSINE)},
                sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
            )
        else:
            info = await self.client.get_collection(self.collection)
            vectors = info.config.params.vectors
            existing = vectors[DENSE].size if isinstance(vectors, dict) else None
            if existing != self.dense_dim:
                raise RuntimeError(
                    f"Collection {self.collection!r} has dense size {existing}, embedding model produces "
                    f"{self.dense_dim}. Changing EMBEDDING_MODEL or EMBEDDING_DIMENSIONS requires a new "
                    "QDRANT_COLLECTION (scripts/reindex_knowledge.py copies the knowledge base into it)."
                )
        for field in ("kind", "innovation_id", "categories", "doc_type", "role", "verification"):
            await self.client.create_payload_index(
                self.collection, field, field_schema=models.PayloadSchemaType.KEYWORD,
            )

    # ---------- writes ----------

    async def replace_innovation(self, innovation_id: str, points: list[PointData]) -> None:
        """Vectors are computed before this call, so a failed embedding never removes
        the published version; only the delete+upsert pair touches the index."""
        await self.client.delete(self.collection, points_selector=self._by_innovation(innovation_id), wait=True)
        await self.upsert(points)

    async def upsert(self, points: list[PointData]) -> None:
        """Writes points in place; a point with an existing ID is fully replaced."""
        batch = 128
        for i in range(0, len(points), batch):
            await self.client.upsert(
                self.collection,
                points=[
                    models.PointStruct(id=p.id, vector={SPARSE: p.sparse, **({DENSE: p.dense} if p.dense is not None else {})},
                                       payload=p.payload)
                    for p in points[i:i + batch]
                ],
                wait=True,
            )

    async def set_categories(self, innovation_id: str, categories: list[Category], primary: Category) -> None:
        await self.client.set_payload(
            self.collection,
            payload={"categories": [c.value for c in categories], "primary_category": primary.value},
            points=self._by_innovation(innovation_id),
            wait=True,
        )

    async def set_chunk_fields(self, innovation_id: str, fields: dict[str, Any]) -> None:
        """Updates denormalized card fields on every chunk without touching vectors."""
        await self.client.set_payload(
            self.collection,
            payload=fields,
            points=models.Filter(must=[_match("kind", "chunk"), _match("innovation_id", innovation_id)]),
            wait=True,
        )

    async def set_card_fields(self, innovation_id: str, fields: dict[str, Any]) -> None:
        await self.client.set_payload(self.collection, payload=fields,
                                      points=[point_id(innovation_id, "card")], wait=True)

    async def delete_innovation(self, innovation_id: str) -> None:
        await self.client.delete(self.collection, points_selector=self._by_innovation(innovation_id), wait=True)

    # ---------- reads ----------

    async def get_innovation(self, innovation_id: str) -> InnovationSummary | None:
        found = await self.get_innovations([innovation_id])
        return found.get(innovation_id)

    async def get_innovations(self, ids: list[str]) -> dict[str, InnovationSummary]:
        if not ids:
            return {}
        records, _ = await self.client.scroll(
            self.collection,
            scroll_filter=models.Filter(must=[
                _match("kind", "card"),
                models.FieldCondition(key="innovation_id", match=models.MatchAny(any=ids)),
            ]),
            limit=len(ids),
            with_payload=True,
        )
        return {r.payload["innovation_id"]: card_payload_to_summary(r.payload) for r in records}

    async def chunks(self, innovation_id: str) -> list[tuple[str, dict[str, Any]]]:
        """IDs and payloads of every chunk of one innovation, without vectors."""
        flt = models.Filter(must=[_match("kind", "chunk"), _match("innovation_id", innovation_id)])
        out: list[tuple[str, dict[str, Any]]] = []
        offset = None
        while True:
            records, offset = await self.client.scroll(
                self.collection, scroll_filter=flt, limit=256, offset=offset, with_payload=True,
            )
            out.extend((str(r.id), r.payload) for r in records)
            if offset is None:
                break
        return out

    async def list_innovations(self, category: Category | None = None, *,
                               confirmed_only: bool = False) -> list[InnovationSummary]:
        must = [_match("kind", "card")]
        if category is not None:
            must.append(_match("categories", category.value))
        if confirmed_only:
            must.append(_match("verification", "potwierdzona"))
        out: list[InnovationSummary] = []
        offset = None
        while True:
            records, offset = await self.client.scroll(
                self.collection, scroll_filter=models.Filter(must=must), limit=256, offset=offset, with_payload=True,
            )
            out.extend(card_payload_to_summary(r.payload) for r in records)
            if offset is None:
                break
        return sorted(out, key=lambda s: (s.title.casefold(), s.id))

    async def search_chunks(
            self,
            dense: list[float] | None,
            sparse: models.SparseVector,
            *,
            limit: int,
            prefetch: int,
            categories: list[Category] | None = None,
            role: DocumentRole | None = None,
            innovation_ids: list[str] | None = None,
            confirmed_only: bool = False,
    ) -> list[models.ScoredPoint]:
        """Flat hybrid retrieval over chunks (dense + BM25, RRF). Grouping by innovation is done
        by the caller: Qdrant's grouped fusion scores each group separately, which makes the
        group scores useless for ranking innovations against each other.
        `role` restricts to summary or full materials; chunks indexed before roles existed count as full."""
        flt = self._filter("chunk", categories, confirmed_only)
        if role == "summary":
            flt.must.append(_match("role", "summary"))
        elif role == "full":
            flt.must_not = [_match("role", "summary")]
        if innovation_ids is not None:
            flt.must.append(models.FieldCondition(key="innovation_id", match=models.MatchAny(any=innovation_ids)))
        if dense is None and not sparse.indices:
            return []
        ranking = (
            {"prefetch": self._prefetch(dense, sparse, prefetch, flt),
             "query": models.FusionQuery(fusion=models.Fusion.RRF)}
            if dense is not None and sparse.indices
            else {"query": dense if dense is not None else sparse, "using": DENSE if dense is not None else SPARSE}
        )
        result = await self.client.query_points(
            self.collection,
            **ranking,
            query_filter=flt,
            limit=limit,
            with_payload=True,
        )
        return result.points

    async def search_cards(
            self,
            vector: list[float] | models.SparseVector | None,
            *,
            limit: int,
            categories: list[Category] | None = None,
            confirmed_only: bool = False,
    ) -> list[tuple[str, float]]:
        """Retrieve short curated cards by dense similarity or exact terms."""
        if vector is None or (isinstance(vector, models.SparseVector) and not vector.indices):
            return []
        using = SPARSE if isinstance(vector, models.SparseVector) else DENSE
        result = await self.client.query_points(
            self.collection,
            query=vector,
            using=using,
            query_filter=self._filter("card", categories, confirmed_only),
            limit=limit,
            with_payload=["innovation_id"],
        )
        return [(p.payload["innovation_id"], p.score) for p in result.points]

    @staticmethod
    def _prefetch(dense, sparse, limit: int, flt: models.Filter) -> list[models.Prefetch]:
        return [
            models.Prefetch(query=dense, using=DENSE, limit=limit, filter=flt),
            models.Prefetch(query=sparse, using=SPARSE, limit=limit, filter=flt),
        ]

    @staticmethod
    def _filter(kind: str, categories: list[Category] | None, confirmed_only: bool = False) -> models.Filter:
        must: list[models.Condition] = [_match("kind", kind)]
        if confirmed_only:
            must.append(_match("verification", "potwierdzona"))
        if categories:
            must.append(models.FieldCondition(
                key="categories", match=models.MatchAny(any=[c.value for c in categories]),
            ))
        return models.Filter(must=must)

    @staticmethod
    def _by_innovation(innovation_id: str) -> models.FilterSelector:
        return models.FilterSelector(filter=models.Filter(must=[_match("innovation_id", innovation_id)]))


def _match(key: str, value: str) -> models.FieldCondition:
    return models.FieldCondition(key=key, match=models.MatchValue(value=value))


def meta_to_card_payload(meta: InnovationMeta, *, files: list[str], chunk_count: int) -> dict[str, Any]:
    data = meta.model_dump(mode="json")
    data["innovation_id"] = data.pop("id")
    return {"kind": "card", "doc_type": "card", **data, "files": files, "chunk_count": chunk_count}


def card_payload_to_summary(payload: dict[str, Any]) -> InnovationSummary:
    fields = set(InnovationSummary.model_fields) - {"id"}
    return InnovationSummary(id=payload["innovation_id"], **{k: v for k, v in payload.items() if k in fields})
