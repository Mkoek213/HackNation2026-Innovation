"""
Add the missing dense vector to every card point, in place.

Cards saved during an embedding outage keep only BM25, so similar cards and meaning-based chat
retrieval skip them. This embeds their current card text and changes nothing else.

Usage, in the backend container:
    docker compose exec backend python scripts/backfill_dense.py
"""
import asyncio
import sys
from pathlib import Path

from qdrant_client import models

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.modules.knowledge.service import card_text, get_knowledge_service  # noqa: E402
from app.modules.knowledge.store import DENSE, card_payload_to_summary  # noqa: E402

BATCH = 50


async def main() -> int:
    service = await get_knowledge_service()
    store = service.store
    missing: list[tuple[str, str]] = []
    offset = None
    while True:
        records, offset = await store.client.scroll(
            store.collection, scroll_filter=models.Filter(must=[models.FieldCondition(
                key="kind", match=models.MatchValue(value="card"))]),
            limit=256, offset=offset, with_payload=True, with_vectors=[DENSE])
        missing += [(str(r.id), card_text(card_payload_to_summary(r.payload)))
                    for r in records if not (r.vector or {}).get(DENSE)]
        if offset is None:
            break
    print(f"Cards without a dense vector: {len(missing)}", file=sys.stderr)
    done = 0
    for start in range(0, len(missing), BATCH):
        batch = missing[start:start + BATCH]
        dense, _ = await service.embedder.embed_passages([text for _, text in batch])
        vectors = {pid: vector for (pid, _), vector in zip(batch, dense) if vector is not None}
        await store.set_dense(vectors)
        done += len(vectors)
    print(f"Added {done} of {len(missing)} dense vectors")
    return int(done < len(missing))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
