# Knowledge resources

## Scope

Source-backed knowledge about innovations from schools, universities, local governments and other public institutions.

Own knowledge ingestion, updates, provenance and retrieval. Keep innovation descriptions, source provenance (`source_name`, `source_url`, `imported_at`) and demonstrated outcomes distinguishable.

## Integration Interface

The public entry is `app.modules.knowledge`; its `__all__` lists everything other modules may use:
`router`, `Category` (sector), `CATEGORY_LABELS`, `CATEGORY_CRITERIA`, `InnovationMeta`, `InnovationCard`,
`Evidence`, `RetrievedInnovation`, `KnowledgeService`, `get_knowledge_service`, `KnowledgeUnavailable`,
`InnovationNotFound`. Matchmaking calls `await (await get_knowledge_service()).retrieve(query, categories=..., pool=...)`
and receives innovations with fused retrieval scores and evidence excerpts (file, section, PDF pages). Retrieval makes
no relevance judgment; that belongs to matchmaking.

Storage is Qdrant. The service is
built lazily on the first request; import and startup need no configuration. Without `QDRANT_URL`, or when Qdrant is
unreachable, knowledge operations return 503 and `/health` still works.

| Operation | Access | Behavior |
| --- | --- | --- |
| `GET /api/v1/knowledge/categories` | public | Sector slugs with Polish labels (`taxonomy.py`) |
| `GET /api/v1/knowledge/innovations?category=` | public | Innovation cards with categories, files, chunk count |
| `GET /api/v1/knowledge/innovations/{id}` | public | One card; 404 if missing |
| `POST /api/v1/knowledge/innovations/draft` | admin session or `X-Admin-Token` | Multipart `files` only (PDF/DOCX/ZIP). Reads the text, asks GLiDE for the sectors and the chat model for a Polish title and card. If `FASTINO_API_KEY` is unset, the chat model also proposes those categories. Stores nothing and does not need Qdrant |
| `PUT /api/v1/knowledge/innovations/{id}` | `X-Admin-Token` | Multipart: `meta` (InnovationMeta JSON without `id`), optional `summary` (one short PDF/DOCX overview) and `files` (full materials: PDF/DOCX/ZIP). Extracts text with page numbers, chunks by section, embeds (Gemini `gemini-embedding-2` + BM25), stores documents in S3 with their role and replaces the innovation in Qdrant. Returns indexed and skipped files and `summary_file` |
| `PATCH /api/v1/knowledge/innovations/{id}` | `X-Admin-Token` | JSON InnovationMeta without `id`. Replaces the title, categories, links and card, keeping the indexed documents. Re-embeds the card, and the chunks only when the title changes |
| `PATCH /api/v1/knowledge/innovations/{id}/categories` | `X-Admin-Token` | Updates categories on the card and all chunks, no re-embedding |
| `DELETE /api/v1/knowledge/innovations/{id}` | `X-Admin-Token` | Removes the card and its chunks |
| `GET /api/v1/knowledge/taxonomy` | public | Polish labels of sectors, innovation types, institution types and maturity stages |

Write protection is a shared secret (`RADAR_ADMIN_TOKEN`); writes are disabled while it is unset. It is demo-grade, not
real authorization. Categories are the `Category` enum (multi-label; `primary_category` is always included).

Configuration (environment, read on first use): `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`
(per person on the shared cluster), `RADAR_ADMIN_TOKEN`, `GEMINI_API_KEY`, `EMBEDDING_MODEL` (default `gemini-embedding-2`),
`EMBEDDING_DIMENSIONS` (default 1536), `RETRIEVAL_PREFETCH`, `EVIDENCE_PER_INNOVATION`, `KNOWLEDGE_MAX_UPLOAD_MB`.
Dense vectors come from the Gemini API with the same key as the chat agent; without it knowledge operations return 503.
BM25 sparse vectors are computed in process, so no model is downloaded or bundled.
A collection is bound to one embedding model and size.
After changing either, point `QDRANT_COLLECTION` at a new collection and copy the knowledge base into it with
`scripts/reindex_knowledge.py <old collection>` (it re-embeds the stored texts; source documents in S3 are not re-read).

### Summary and full materials

Each innovation has a curated card (`meta.card`), one short **summary** document and its **full** materials.
Every stored document and every chunk carries `role: "summary" | "full"` (chunks indexed earlier count as full).

`retrieve()` works in two stages:

1. **Which innovations fit.** Weighted reciprocal-rank fusion of three rankings: cards (dense, weight 1),
   summary chunks (dense + BM25, weight 1) and full-material chunks (dense + BM25, weight 0.5). Card and summary
   are short and comparable across innovations, so long reports cannot win by volume; full materials still add
   recall for terms that appear only there.
2. **Evidence.** For each selected innovation, one filtered query returns its best passages from full materials;
   the summary is used when an innovation has no full materials.

Each `RetrievedInnovation` has `summary_document` (the overview to open first) and `evidence` with
`role`, `document_url` and, for PDFs, `page_url` (`document_url#page=N`, opens the cited page in browser PDF viewers).
Chat answers carry `innovations[].evidence[].page_url`; the workspace's direct retrieval answer also carries
`innovations[].summary_url`. The frontend does not render either link yet.
The service answers only from documents uploaded here.

Example upload:

```bash
curl -X PUT "$API/api/v1/knowledge/innovations/czujnik-powietrza" -H "X-Admin-Token: $RADAR_ADMIN_TOKEN" \
  --form-string 'meta={"title":"Czujnik jakości powietrza dla szkół","primary_category":"jakosc-zycia","categories":["jakosc-zycia","ict"],"institution":"Politechnika Rzeszowska","card":{"solution":"..."}}' \
  -F summary=@ulotka.pdf -F files=@opis-patentowy.pdf
```

Use `--form-string` for `meta`: with `-F`, curl treats `;` inside the JSON as a field-parameter separator.
To upload many innovations, describe them in `backend/data/seed/<source>.json` (`meta`, optional `summary`, `files`,
`exclude`), usually generated by `backend/scripts/import_*.py`, and run `backend/scripts/upload_innovations.py`
against a running backend; it uses the same endpoint. Records without files are indexed from their card only.

## Deferred work and validation

Deferred: OCR for scanned PDFs, report/guidance documents not tied to an innovation, patent sources,
and a frontend editor. Trends are administrator-only; public knowledge operations must not expose private query text.

Database, identity, permissions and module business operations are outside this module.

From `backend/`, start the shared app with
`uv run --env-file ../.env uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.
Validate module changes with static review and manual API verification.

## Stored source documents

Compose starts SeaweedFS on localhost port 8333 with a persistent `s3-data` volume.
The `s3-init` service creates the private `S3_BUCKET` before the backend starts.
Defaults are local development credentials; configure them in `.env` before sharing a deployment.

The upload endpoint retains every PDF/DOCX, including files inside ZIPs, scans without text,
and PDF/DOCX twins. ZIP containers are not retained. Existing `files` and `skipped_files` describe
indexing; the new `documents` array describes downloadable source files independently.
Each entry has `id`, `filename`, `content_type`, `size_bytes`, and a relative `download_url`.
Object keys are stored privately in the Qdrant card payload and excluded from HTTP responses.

`GET /api/v1/knowledge/innovations/{innovation_id}/documents/{document_id}` is public:
PDF responses are inline; DOCX responses are attachments. The backend streams from the private bucket.
No admin token is required to download. Missing documents return 404; unavailable storage returns 503.
Use the backend origin with the returned relative URL. Frontend rendering/chat selection is separate work.

Configure `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, and
`S3_SECRET_ACCESS_KEY`. Compose supplies the internal endpoint `http://s3:8333` automatically.
For a backend running on your host, use `S3_ENDPOINT_URL=http://localhost:8333` and the same credentials.
Unconfigured storage does not prevent startup, reads, or card-only uploads; document uploads require S3.
Older cards default to `documents=[]` and require re-upload to recover source files.

Uploads are bounded per file by `KNOWLEDGE_MAX_UPLOAD_MB`; archive expansion uses the same
aggregate byte limit, at most 1000 entries and five ZIP levels. Unsafe archive paths are ignored.
Replacements stage unique objects, publish Qdrant metadata, then clean up old objects. Deletion cleans up
associated objects. Cleanup failures are logged and may leave unreferenced objects.
Writes are serialized within one backend process. Qdrant's existing delete/upsert operation remains
nontransactional: a partial publication failure retains staged objects to avoid deleting referenced files.
There is no distributed transaction, historical version store, or background cleanup worker in this PoC.

## Chat consumer contract

Chat tools call the public `get_knowledge_service`, `retrieve` and `get` exports.
Chat retains original innovation IDs, card metadata and source-file/page provenance;
retrieved passages remain turn-local. Chat selects fit separately from retrieval ranking,
validates references before publishing matches, and handles empty results separately
from `KnowledgeUnavailable` and `InnovationNotFound`. It creates no second Qdrant client
or ingestion path. Retrieval quality on the imported Radar corpus has not been measured.
