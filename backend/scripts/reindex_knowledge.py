"""Copy the knowledge base into a new Qdrant collection with freshly computed vectors.

A collection is bound to one embedding model and size, so changing EMBEDDING_MODEL or
EMBEDDING_DIMENSIONS needs a new QDRANT_COLLECTION. Point payloads keep the chunk text
verbatim, so this rebuilds the embedded texts from them (the same card and chunk texts the
ingest path embeds) without re-reading the source documents from S3. Point IDs and payloads,
including document references, are copied unchanged; the source collection is not modified.

Usage, in the backend container (settings come from the root `.env`):

    docker compose exec backend python scripts/reindex_knowledge.py radar_innovations_dev

or from `backend/` on the host with only QDRANT_*, GEMINI_API_KEY and EMBEDDING_* exported.

The target is QDRANT_COLLECTION. Re-running replaces each innovation in the target again.
"""
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.modules.knowledge.schemas import InnovationMeta  # noqa: E402
from app.modules.knowledge.service import KnowledgeService, card_text, chunk_text  # noqa: E402
from app.modules.knowledge.settings import load_knowledge_settings  # noqa: E402
from app.modules.knowledge.store import PointData, card_payload_to_summary  # noqa: E402


def embedded_text(payload: dict) -> str:
    if payload["kind"] == "card":
        summary = card_payload_to_summary(payload)
        return card_text(InnovationMeta(**summary.model_dump(include=set(InnovationMeta.model_fields))))
    return chunk_text(payload["title"], payload.get("section"), payload["doc_type"], payload["text"])


async def main(source: str) -> None:
    settings = load_knowledge_settings()
    if source == settings.qdrant_collection:
        sys.exit(f"Source and target are both {source!r}; set QDRANT_COLLECTION to a new collection.")
    service = await KnowledgeService.create(settings)
    client = service.store.client
    try:
        if not await client.collection_exists(source):
            sys.exit(f"Source collection {source!r} does not exist.")
        by_innovation: dict[str, list] = defaultdict(list)
        offset = None
        while True:
            records, offset = await client.scroll(source, limit=256, offset=offset, with_payload=True)
            for record in records:
                by_innovation[record.payload["innovation_id"]].append(record)
            if offset is None:
                break
        for innovation_id, records in by_innovation.items():
            dense, sparse = await service.embedder.embed_passages([embedded_text(r.payload) for r in records])
            points = [PointData(id=str(r.id), dense=d, sparse=s, payload=r.payload)
                      for r, d, s in zip(records, dense, sparse)]
            await service.store.replace_innovation(innovation_id, points)
            print(f"{innovation_id}: {len(points)} points")
        print(f"Reindexed {len(by_innovation)} innovations from {source!r} into {settings.qdrant_collection!r}.")
    finally:
        await service.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1]))
