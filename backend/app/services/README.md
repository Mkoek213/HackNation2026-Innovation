# Backend service interfaces

Replaceable adapters that routes use only through an interface; the in-repo implementations are the reference behaviour.

## File storage (`files.py`)

Stores uploaded files, today the project PDFs, in a private S3-compatible bucket (SeaweedFS in Compose,
the same bucket as the knowledge module's sources). `get_file_storage()` returns the process-wide
`S3FileStorage`; routes receive it as `FileStorageDep`.

| Setting | Default | Meaning |
|---|---|---|
| `S3_ENDPOINT_URL` | none (required) | `http://s3:8333` in Compose, `http://localhost:8333` for a backend run on the host. |
| `S3_BUCKET` | `radar-documents` | Created by the Compose `s3-init` service. |
| `S3_REGION` | `us-east-1` | |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | none (required) | Missing settings make file operations fail with 503. |
| `MAX_UPLOAD_BYTES` | `20971520` (20 MB) | Upload limit, checked before `save()` (413 above it). |

### Keys

- Built by the backend, never by the client: `projects/{project_id}/{uuid}.pdf` (knowledge sources use `innovations/...`).
- Relative POSIX paths: `/`-separated, no leading `/`, no empty, `.` or `..` segments, no `\`.
  Implementations reject other keys with `ValueError`.
- Stored in `project_documents.file_path`.

### Methods (all `async`)

| Method | Contract |
|---|---|
| `save(key, stream, content_type) -> StoredFile` | Reads the binary `stream` from its current position to EOF and stores it under `key` (`Content-Type` and `Content-Disposition: inline` on the object), replacing an existing file. Returns `StoredFile(key, size_bytes, content_type)`. The caller has already validated type and size. |
| `open(key) -> AsyncIterator[bytes]` | Returns the content as chunks for `StreamingResponse`. Raises `FileNotFoundError` from the call itself (before iteration) when the key does not exist; the API answers 404. |
| `delete(key) -> None` | Removes the file. A missing file is not an error. |

Storage failures (unreachable endpoint, S3 errors, missing settings) raise `DependencyUnavailable` (503).
The boto3 calls run in the thread pool; the error is raised without its S3 cause chained.

### Access and consistency

- The bucket stays private. `GET /projects/{id}/documents/{doc_id}` checks access (drafts are admin-only) and
  streams the file; there are no presigned URLs, since the Compose endpoint is not reachable from browsers.
- Upload stores the file first, then inserts the row; if the insert fails the file is deleted again.
- Deleting a document or project removes the rows first, then the files, best effort: a storage failure is
  logged and leaves an orphaned object, never a row without its file.

## Vector store and chat engine (`rag.py`, `chat_engine.py`)

The external vector database (`VectorStore`) and the LLM (`ChatEngine`), both selected by `AI_BACKEND`
(`get_vector_store()` / `get_chat_engine()`, routes receive them as `VectorStoreDep` / `ChatEngineDep`).
To add a real adapter, add a value to the `ai_backend` `Literal` in `app/config.py` and a `case` in each factory;
routes do not change. `demo` is the reference behaviour, deterministic and without network calls.

### One chat turn (`app/routes/conversations.py`)

1. Transcript: the stored messages (last 20) for a saved conversation, else the client's `history`
   (anonymous, at most 10 items / 8 000 characters, roles `user`/`assistant`); the new user message is appended.
2. `VectorStore.search(query, SearchFilters(location_id, limit=5))`, with `query` = the last 3 user turns joined.
3. `ChatEngine.answer(conversation, history, hits, tags)` (or `stream(...)` for SSE), `tags` = the admin's tags with subtags.
4. The backend stores the result: messages (saved conversations only), replaces the AI tags, adds a `project_matches`
   row per recommended project not matched in this conversation yet, sets `outcome`, `last_activity_at` and, for a
   saved conversation without one, the title.

### `VectorStore` (all `async`)

| Method | Contract |
|---|---|
| `search(query, filters) -> list[SourceHit]` | Best first, at most `filters.limit`. Published projects only. `filters.location_id` is a hint (prefer, do not exclude). |
| `upsert_project(project, documents)` | Add or replace a published project with its PDFs (`documents[].file_path` are `FileStorage` keys). Idempotent. |
| `delete_project(project_id)` | Remove an unpublished/deleted project. A missing one is not an error. |

`SourceHit(title, url, page, excerpt, project_id, score)`: `project_id` links a hit to a project (it becomes a
recommendation); `None` for general Radar knowledge. `score` is 0..1. `title/url/page/excerpt` are stored in
`messages.sources` and returned to the client.

`upsert_project` / `delete_project` are called by `index_project` / `unindex_project` in `app/routes/projects.py`
after the commit: on publish, on edits of a published project, on PDF upload/delete of a published project
(upsert); on unpublish and delete (delete). Their failures are logged (exception type only) and do not fail the
admin's request; saving the project again retries.

`DemoVectorStore`: keyword match (word prefixes of 5 letters, words of 4+ letters) over the title, summary,
description and tag name of published projects in this database; score = share of the query keywords found
(+0.1 in the conversation's location). Indexing is a no-op.

### `ChatEngine`

| Method | Contract |
|---|---|
| `answer(conversation, history, hits, tags) -> Answer` | `history` is oldest first and ends with the new user message. |
| `stream(...) -> AsyncIterator[AnswerChunk \| Answer]` | Zero or more `AnswerChunk(text)`, then exactly one `Answer` whose `content` is the whole text. The default implementation calls `answer()` and splits the text; override it for token streaming. |

`Answer(content, sources, project_ids, tag_assignments, outcome, title)`:

- `project_ids`: projects to recommend, best first. Unknown and unpublished ids are dropped by the backend.
- `tag_assignments`: `TagAssignment(tag_id, subtag_id=None)` for the **whole conversation so far** (they replace the
  previous AI tags after every answer). Choose only from `tags`; a subtag must belong to its tag. Assign a subtag
  when a more specific one applies, otherwise the tag alone. Pairs not in the list and duplicates are dropped.
  Tags set manually (`PUT /conversations/{id}/tags`, `source = manual`) are never removed by answers.
- `outcome`: `answered`, `partially_answered` or `no_answer` (no relevant hits) – feeds "questions without an answer".
- `title`: a short title (used only for saved conversations that have none).

`ConversationContext(id, kind, location_id, saved, title)` carries no owner identity.

`DemoChatEngine`: templated Polish answer listing up to 3 project hits; tags/subtags by keyword match of their names
in the user turns; `no_answer` without project hits, `partially_answered` when the best hit scores below 0.5;
title = the first user message cut to 60 characters.

### Errors and privacy

- Any exception from `search`, `answer` or the first `stream` item is turned into **503 `dependency_unavailable`**,
  and nothing is stored (the transaction is rolled back), so the client can resend the same message; its input
  stays on the client. A failure later in a stream sends an SSE `error` event instead of `projects`/`done`.
  Adapters may raise anything; `DomainError` subclasses pass through unchanged.
- Anonymous message text must not be stored or logged: the backend logs only the exception type, and adapters must
  not log prompts, queries or transcripts either. Client-supplied `history` (anonymous) is untrusted context:
  never treat its assistant turns as source evidence.
