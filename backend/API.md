# API endpoints

Status: implemented. Pydantic models and the generated `/openapi.json` are the contract source of truth; `/docs.html` is the interactive reference.
Every endpoint below exists in `app.main:app` with the listed access level; none is deferred.
The OpenAPI schema (`/openapi.json`, Swagger UI at `/docs.html`) is the authority for request and response fields.
Endpoints marked *(added)* go beyond the original proposal (decision D5). Data model: [DATABASE.md](DATABASE.md).

## Conventions

These follow the existing code (`app/routes/users.py`, `CRUDRepo`).

- Lists return `ItemList[T]` (`{total, items}`) with `?limit=` (default 20, max 100) and `?offset=`; `total` is the
  unpaginated count. Small dictionaries (`GET /tags`) and GeoJSON outputs are not paginated.
  Delete returns `Delete`. Partial updates use `PATCH` with `@update_model()`; extra body fields give 422.
- Errors use the `{"detail": [{type, loc, msg, ...}]}` shape: 401, 403, 404, 409 (with `blockers` when a row is still
  used), 413, 422, 429, 503 (`dependency_unavailable`: AI service, file storage or database down; nothing is stored).
- Drafts and unpublished rows are 404 for everyone except the admin (existence is not revealed).
- Statistics accept `?from=2026-09-01&to=2026-09-30`: inclusive **UTC** days, default the last 30 days including today,
  `to < from` or more than 366 days → 422. Every statistics response carries `period: {from, to}`, and every per-day
  `series` has one zero-filled entry per day of the period.
- Login: `POST /auth/login` issues the JWT per `AUTH_TOKEN_LOCATION`: an HttpOnly cookie (unsafe methods then need the
  `X-CSRF-Token` header copied from the `csrf_token` cookie), a Bearer token in the body, or both.
- Rate limits per client IP: global `RATE_LIMIT` (120/minute, also `POST /visits`), chat answers `CHAT_RATE_LIMIT`
  (30/minute), `LOGIN_RATE_LIMIT` and `REGISTER_RATE_LIMIT` (5/minute).

| Access | Meaning |
|---|---|
| public | No login (decision D4). Endpoints that track a visitor (`VisitorDep`) set the anonymous `visitor_id` cookie if missing. |
| user | Logged in (`CurrentUserDep`): saved conversations and ideas |
| owner | Owns the resource (by `user_id` or, for anonymous conversations, the `visitor_id` cookie), or admin |
| admin | `CurrentAdminDep`; a regular user gets 403, an anonymous caller 401 |

## Auth and users

| Method | Path | Access | Description |
|---|---|---|---|
| POST | `/auth/login` | public | `{username, password}` |
| POST | `/auth/logout` | public | Clears the cookies |
| POST | `/auth/register` | public | `{username, email, password}` → 201 `UserModel`, role `user`; 409 on a duplicate username/email (email case-insensitive); any extra field such as `role` → 422; does not log in |
| GET | `/users/me` | user | |
| PATCH | `/users/me` | user | Own username, e-mail or password; non-admins cannot change `role` |
| GET, POST | `/users` | admin | Paginated list (20 by default); create |
| GET, PATCH, DELETE | `/users/{user_id}` | admin | Deleting a user deletes their conversations and ideas |

## Operator (PCI) staff and PDF helper

| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/operator/staff` | user | Admin accounts with e-mail plus optional `RADAR_CONTACT_EMAIL` for handoff autocomplete |
| POST | `/operator/pdf` | user | `{title, content}` Markdown → PDF download |

The public contact form is described in [Contact form](#contact-form).

## Locations and map (OpenStreetMap)

| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/locations` | public | `?kind=municipality&parent_id=&q=` – paginated list for pickers, ordered by name, no geometry. `q` is a name fragment (case-insensitive) or a TERYT prefix. |
| GET | `/locations/{location_id}` | public | Includes centroid and `osm_relation_id` |
| GET | `/locations/geojson` | public | `?kind=county&parent_id=` → GeoJSON `FeatureCollection`. Each feature: `geometry` = boundary (the centroid `Point` when no boundary is stored), `properties` = `{id, name, teryt_code, kind}`. |
| GET | `/projects/geojson` | public | Published projects as `Point` features (project coordinates, else the location centroid), `properties` = `{id, title, tag_id, subtag_id}`. `?tag_id=&subtag_id=` filters. Tagged `Projects` in OpenAPI. |

GeoJSON responses use `Content-Type: application/json` (not `application/geo+json`); Leaflet and MapLibre accept it.

Frontend usage (react-leaflet):

```tsx
<MapContainer center={[50.06, 19.94]} zoom={8}>
  <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
             attribution="&copy; OpenStreetMap contributors" />
  <GeoJSON data={municipalities} />   {/* GET /locations/geojson?kind=municipality */}
  <GeoJSON data={projects} />         {/* GET /projects/geojson */}
</MapContainer>
```

`GET /projects/{id}/participants?format=geojson` and `GET /stats/locations?format=geojson` return the same features
with the statistic in `properties`, for choropleth colouring.

## Tags and subtags

| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/tags` | public | All tags with nested subtags, ordered by name, not paginated: `{total, items: [{id, name, description, subtags: [{id, tag_id, name, description}]}]}` |
| POST | `/tags` | admin | `{name, description?}` → 201; 409 on duplicate name (exact match, names are stripped) |
| PATCH | `/tags/{tag_id}` | admin | |
| DELETE | `/tags/{tag_id}` | admin | 409 if it still has subtags or is used by projects or conversations |
| POST | `/tags/{tag_id}/subtags` | admin | `{name, description?}` → 201; 409 on a duplicate name within the tag |
| PATCH | `/subtags/{subtag_id}` | admin | `{name?, description?}`; a subtag cannot move to another tag |
| DELETE | `/subtags/{subtag_id}` | admin | 409 if used by projects or conversations |

## Conversations

| Method | Path | Access | Description |
|---|---|---|---|
| POST | `/conversations` | public | `{message, kind?: "search", location_id?}` → 201 `{conversation, answer}`. Creates the conversation and returns the first answer. |
| GET | `/conversations` | user | Own saved conversations, `?tag_id=&subtag_id=&q=&status=`, most recently active first; `q` searches the title and message text |
| GET | `/conversations/{conversation_id}` | owner | With tags, messages (empty for anonymous) and matched projects |
| PATCH | `/conversations/{conversation_id}` | owner + user | `{title?, status?, location_id?}`; a title on an anonymous conversation → 422 |
| DELETE | `/conversations/{conversation_id}` | owner + user | |
| POST | `/conversations/{conversation_id}/messages` | owner | `{content, history?}` → `{message_id, content, sources[], projects[], tags[], outcome}`; `projects` items are matches (`id` = match id) with the project card nested |
| POST | `/conversations/{conversation_id}/messages/stream` | owner | The same as Server-Sent Events: `token`…, `projects`, `done`; `error` on a mid-stream failure. Errors before the first event are JSON. |
| PUT | `/conversations/{conversation_id}/tags` | owner + user | `[{tag_id, subtag_id?}]` – replace the manual tags (correction); AI tags are recomputed on each answer, manual ones are kept |
| POST | `/project-matches/{match_id}/open` | owner | The visitor opened a project card recommended in the chat (idempotent). Tagged `Projects`. |
| POST | `/chat` | public | Legacy `{message}` → `{answer, innovations}` from the knowledge base (`app/modules/knowledge`), kept for the current frontend proxy; stores nothing |

"owner + user" means login is required (decision D4); for an anonymous conversation a logged-in visitor with the matching
`visitor_id` cookie passes.

Anonymous conversations (D4): message content is never stored. The client keeps the transcript and sends
`history: [{role, content}]` (at most 10 messages and 8 000 characters in total, roles `user`/`assistant`; above → 422)
with each message. Only a content-free conversation row (no title, no messages) with tags, matched projects, outcome and
location is kept for statistics. Conversations started while logged in are saved with their messages and get a title;
their `history` field is ignored (the last 20 stored messages are used). Logging in later does not save an anonymous
conversation.

On each answer the backend:
1. Searches the vector store (`VectorStore`, external service; demo: keyword match over published projects).
2. Asks the chat engine (`ChatEngine`) for the answer, choosing tags/subtags from the admin's list only.
3. Saves the messages (saved conversations only), replaces the AI tags, adds one `project_matches` row per project per
   conversation, and sets `outcome`, `last_activity_at` and the title. Unknown tag pairs and unpublished projects
   returned by the engine are dropped. An AI failure → 503 with nothing stored.

The interfaces and the `AI_BACKEND` setting are documented in [app/services/README.md](app/services/README.md).

## Projects

| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/projects` | public | Published, newest first, `?tag_id=&subtag_id=&location_id=&q=`; `location_id` includes the units inside it; the admin also sees drafts and can filter `?status=` |
| GET | `/projects/{project_id}` | public | `ProjectDetail`: description, links, `documents[]` with `url`, `participants_total` |
| POST | `/projects` | admin | Create (always `draft`) → `ProjectDetail` |
| PATCH | `/projects/{project_id}` | admin | Edit; `{"status": "published"}` publishes and indexes it in the vector store, `draft` unindexes it |
| DELETE | `/projects/{project_id}` | admin | Also deletes the stored PDFs; 409 once the project was shown in the chat (unpublish instead) |
| POST | `/projects/{project_id}/documents` | admin | Multipart `{title, file}`: `application/pdf` with a `%PDF-` signature (else 422), at most `MAX_UPLOAD_BYTES` (else 413 `file_too_large`) |
| GET | `/projects/{project_id}/documents/{document_id}` | public | Streams the PDF, `Content-Disposition: inline` with a UTF-8 filename; 307 when the storage returns a URL |
| DELETE | `/projects/{project_id}/documents/{document_id}` | admin | |
| GET | `/projects/{project_id}/participants` | public | `{total, by_location: [{location_id, name, teryt_code, kind, count}]}`; the unknown origin is a row with null location fields, sorted last. `?level=county` sums gminas into powiats, `?format=geojson` for the map (known locations only). |
| PUT | `/projects/{project_id}/participants` | admin | `[{location_id, participants_count}]` – replace; returns the new summary (not a `BatchResult`); duplicate location → 422, unknown → 404 |

Validation: tag/subtag/location must exist (404), the subtag must belong to the tag (422), latitude and longitude are
given together (422), `website_url`/`video_url` are http(s) URLs. Files live in a private S3 bucket
([app/services/files.py](app/services/files.py)).

## Ideas

| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/ideas` | public | Published ideas, newest first, `?tag_id=&stage=`; `?status=` (default `published`) lets the admin list `submitted`/`rejected` ideas, other statuses from a non-admin → 403 |
| GET | `/ideas/mine` | user | Own ideas in every status, `?status=` |
| GET | `/ideas/{idea_id}` | public | *(added)* Published ideas; the author and the admin also see unpublished ones, otherwise 404 |
| POST | `/ideas` | user | `{title, essence, target_group, stage, tag_id?, location_id?}` → `submitted`; unknown tag/location → 422 |
| PATCH | `/ideas/{idea_id}` | owner | The author edits the content while `submitted` (otherwise 409) and cannot set `status` (403); the admin edits anything and sets `status` (`published` / `rejected`) |
| DELETE | `/ideas/{idea_id}` | owner | In any status |

## Statistics

Counting rules: a person is the logged-in user, otherwise the anonymous visitor (`coalesce('u' || user_id, 'v' ||
visitor_id)`), so the same browser before and after login counts as two people. A conversation counts once per tag,
no matter how many follow-up messages or tag/subtag rows it has. Admins are not counted as registered users.

| Method | Path | Access | Description |
|---|---|---|---|
| POST | `/visits` | public | `{path}` (must start with `/`; the query string and fragment are dropped) → 201 `{id, path, created_at}`; the frontend calls it on each page view, and for anonymous catalog events with the path `/_radar/<kind>/<value>` (never the typed search text) |
| GET | `/stats/site` | admin | `{visits, unique_visitors, conversations, registered_users, series[{date, visits, unique_visitors, conversations}], catalog[{kind, value, label, views, people}]}`; `registered_users` is all-time; `catalog` counts catalog events (card opens `karta`, chosen filters by name), which are kept out of page views |
| GET | `/stats/workspace` | admin | The logged-in chat on `/`: `{threads, unique_users, operations, processing, completed, failed, outcomes{matched, no_match, unavailable}, series[{date, threads, operations, matched, no_match, unavailable}]}`. Threads count by `conversations.created_at` where `workspace` is true; questions (one per `chat_operations` row) count by `chat_operations.created_at`. Outcomes come from `chat_operations.result.outcome` (`unavailable` rows have status `failed`); the tag `no_answer` count uses `conversations.outcome`, which workspace threads now also set. |
| GET | `/stats/innovations` | admin | Paginated ranking of knowledge-base innovations shown in the workspace chat, items `{innovation_id, title, unique_searchers, times_shown, opened}`, ordered by `unique_searchers`, `times_shown`, `opened`; counted by `innovation_matches.created_at`; `total` is the number of innovations shown at least once |
| GET | `/stats/tags` | admin | `{total, items}` of every tag (zeros for unused) with nested subtags, each `{conversations, unique_people, no_answer}`, most searched first; counted by `conversations.created_at` |
| GET | `/stats/tags/timeline` | admin | Every tag over the previous period and the selected one: `{period, previous_period, window_days, step_days, dates[{date, current}], total, items}`, items `{tag_id, name, unique_people, previous_people, change, change_pct, conversations, no_answer, points}`. `points[i]` is the number of distinct people asking about the tag in the `window_days` days ending on `dates[i]` (7-day windows, daily points, for periods up to 92 days; otherwise 28-day windows every 7th day, counted back from each period's end). The totals match `/stats/tags` and `/stats/trends`. Most searched first. |
| GET | `/stats/tags/{tag_id}` | admin | One tag: the same counts, per-day series, subtag breakdown, `top_projects` (10 most recommended in its conversations) |
| GET | `/stats/trends` | admin | Per tag and subtag (`{tag_id, tag_name, subtag_id, subtag_name, current, previous, change, change_pct}`): distinct people now vs the previous period of the same length, `change`, `change_pct` (null when the previous count is 0), biggest absolute change first; rows without activity in both periods are left out. `?location_id=` includes the units inside it. Also returns `previous_period` and `location_id`. |
| GET | `/stats/projects` | admin | Paginated ranking of every project (drafts too), items `{project_id, title, status, unique_searchers, times_shown, opened}`, ordered by `unique_searchers`, `times_shown`, `opened`; counted by `project_matches.created_at` |
| GET | `/stats/projects/{project_id}` | admin | `{project_id, title, status, times_shown, unique_searchers, opened, participants_total, series}`; participants are all-time |
| GET | `/stats/locations` | admin | `{total, items: [{location_id, name, teryt_code, kind, conversations, unique_people, participants}], unknown}` for locations with data (`?level=county`); `?format=geojson` gives features with boundary or centroid, `period` and `unknown` as foreign members. Participants are all-time and include drafts. |

## Operations

| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/healthcheck` | public | `{"status": "ok"}` when the database answers, else 503; used by the Docker `HEALTHCHECK` |

## Implemented authenticated chat workspace

The root frontend uses these endpoints, separately from the existing demo-oriented
`/conversations` contract. Every workspace operation requires login and strict user
ownership (including when the caller is an administrator). Cookie mutations require
CSRF. Workspace rows are excluded from every legacy conversation read/write path.
All workspace responses are `Cache-Control: no-store`.

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/auth/session` | Verify the cookie session; return `{user, csrf_cookie, csrf_header}`; refresh expired CSRF without extending JWT |
| POST | `/workspace/conversations` | Create an empty owned thread (201) |
| GET | `/workspace/conversations` | Active owned threads, `limit` (1–100) / `offset`; activity descending then ID descending; `{id,title,last_activity_at,pending}[]` |
| GET | `/workspace/conversations/{id}` | Thread plus ordered `operations` |
| PATCH | `/workspace/conversations/{id}` | `{title}`; trimmed nonempty title up to 200 characters |
| DELETE | `/workspace/conversations/{id}` | Archive internally; return `{archived:id}`; future reads and writes return 404 |
| POST | `/workspace/conversations/{id}/messages` | `{key:UUID,content}`; trimmed nonempty message up to 4000 characters; durable `OperationModel` |
| POST | `/workspace/conversations/{id}/innovations/{innovation_id}/open` | Mark an innovation shown in this thread as opened → `{opened: innovation_id}`; 404 when it was not shown here. The frontend calls it when the source dialog opens. |

A completed turn also records each shown innovation once per thread in `innovation_matches`
and sets the thread `outcome` (`matched` → `answered`, `no_match` → `no_answer`; the latest
completed turn wins). Unavailable turns change neither.

An operation has `id`, `key`, `content`, stable `user_message_id`, nullable
`assistant_message_id`, `status` (`processing`, `completed`, `failed`), and nullable
`result` (`answer`, `innovations`, `outcome`). Outcomes are `matched`, `no_match`, or
`unavailable`. Only completed operations have assistant messages. Unavailable
retrieval is a persisted failure, never a successful demo answer. Ownership and
archive failures return 404; conflicting keys or concurrent sends return 409.

Repeated key + content returns the current operation without another retrieval.
Retrying the last failed operation reuses its user message and operation ID. A key
cannot be reused with different content. New submission admission is serialized by
a short database write lock on the owner row; a partial unique index additionally
limits processing to one operation per thread. Only one pending operation per
account is admitted, including across tabs. Retrieval runs after admission commits.
A processing lease expires after 720 seconds when history/detail or a later send
checks it; a stale worker cannot finish a newer attempt. Contextual agent turns have
a 600-second deadline inside a 630-second workspace timeout; legacy retrieval has
a 90-second budget. Recover a lost response with GET detail rather than blindly resending.

Context uses the latest ten persisted operations, their completed turns and shown
candidate references. The last three completed user messages are included in a
query capped at 8000 characters. Polish first/second/third references and named
candidates select a previously shown innovation within that window. This resolves
references and returns stored source descriptions; it is not a general dialogue or
comparison model. Scores remain retrieval metadata and are not confidence.

New ingested evidence has an exact document ID, public backend document URL, MIME
type, filename, excerpt and optional page range. Links are resolved against the
current stored-document IDs. Legacy chunks without IDs and replaced documents
retain their text but have no guessed link. The detail modal can separately list
current source documents, including scans without indexed excerpts.

## Implemented Fastino topic labeling

New persisted conversation turns (including `/workspace/conversations/{id}/messages`)
and knowledge document ingestion use shared admin-defined tags/subtags with Fastino GLiDE.
Conversation models expose optional `classification` evidence; workspace detail also exposes
`tags`. Knowledge `StoredDocument` responses expose `tags`, `classification`, and
`content_sha256`. Existing response fields remain compatible. Missing configuration and
provider failure are recorded without failing an otherwise successful answer or ingestion.
See [tagging behavior and configuration](../docs/FASTINO.md#topic-tagging). The existing statistics routes
can aggregate conversation assignments; this does not add document coverage statistics or
an admin dashboard.
## Other routers

The knowledge base module (`app/modules/knowledge`) is mounted under `/api/v1/knowledge`
with its own `X-Admin-Token` write protection; see its [README](app/modules/knowledge/README.md).
`GET /api/v1/knowledge/taxonomy` returns Polish labels of all classification axes (sectors, innovation types,
institution types, deployment levels, audiences, development paths), the five assessment criteria with their meaning
and the current `criteria_version`; `GET /api/v1/knowledge/categories` returns the sectors only.

`GET /api/v1/knowledge/catalog` returns `{items, total, regions, refreshed_at}` and accepts `q`, `category`,
`area`, `audience`, `region`, `maturity`, `confirmed_only`, `min_credibility` (1-5), `offset` and `limit`.
`audience` keeps cards whose assessment recommends that FAQ target group; `refreshed_at` is the latest source check of any public card.
`GET /api/v1/knowledge/innovations/{id}/similar?limit=4` returns the closest public cards by the card's dense vector, to spot similar solutions and duplicated work; it is empty for a card without a dense vector.
It returns candidates and confirmed records, strongest evidence first (confirmed, then credibility, then deployment level).
`q` also matches the Polish assessment summary. The existing unpaginated list still serves administration. Cards expose `area`, `region`, `verification`, `checked_at` and `assessment`.
Confirmed use requires a supported stage and an implementation criterion with an HTTP(S) source.
TRL requires the technology area and its own justification.

Admin-only `POST /api/v1/knowledge/innovations/{id}/assess` scores the card against the five FAQ criteria
(`app/modules/knowledge/assess.py`): credibility by fixed rules, the other criteria, `summary`, `recipients`, `path`,
`measures` and `next_step` as Gemini estimates with basis `szacunek` and a quote checked against the card text.
A field is replaced only while it is empty or still equals the previous automatic proposal, so staff edits and
source-confirmed notes survive. Candidates also take the estimated `maturity`. When Gemini is unavailable only the
rule-based credibility is stored, every other note stays, and the route returns 429 (quota or overload) or 503.
`backend/scripts/assess_innovations.py` runs it for every card not yet on the current `criteria_version`.

Admin-only `PUT /api/v1/knowledge/innovations/{id}/refresh` accepts card metadata as JSON
and returns `{status: "created" | "updated" | "unchanged"}`. It preserves attachments and editorial changes.


## Adaptive workspace summary and contact

`GET /workspace/conversations/{thread_id}/handoff` returns
`{recipient, subject, body, packet, staff[], attachments[], mail_delivery}` for the authenticated
owner of an active workspace thread. `staff` lists admin e-mails (and `RADAR_CONTACT_EMAIL`);
`attachments` lists conversation artifacts and the user's matters for PDF attach;
`mail_delivery` is `server` when SMTP is configured, otherwise `client`. Anonymous requests
return 401; a different owner, archived thread or non-workspace ID returns 404; an active
message operation returns 409. Responses use `Cache-Control: no-store`.

`POST /workspace/conversations/{thread_id}/handoff/send` sends the reviewed draft via SMTP
with the required owner-reviewed summary `packet` rendered as `podsumowanie-radar.pdf`.
The JSON input is `{recipient, subject, body, packet, artifact_id?, matter_id?, include_matters?}`.
A selected artifact or matter is appended to that PDF; matter inlining into the email body
remains opt-in. Recipient must be a valid email, subject a single line, and packet nonblank
(up to 250,000 characters; PDF up to 80 pages, otherwise 413). Invalid input returns 422.
Ownership, CSRF, pending-turn and no-store guards apply. Rendering and SMTP run outside
the event loop. Success (`{sent: true}`) means the configured SMTP server accepted the
message; inbox delivery is not tracked. Missing SMTP or delivery failure returns 503,
so the user can download the PDF and use `mailto:` with a manual attachment.

`GET /workspace/conversations/{thread_id}/artifacts/{artifact_id}/pdf` downloads a PDF of a
canonical artifact in that thread.

Workspace `Result.sources` carries optional source metadata (including statistical
year/geography); `innovations[].evidence` retains actual retrieved excerpts.
Earlier saved operation results remain compatible through default empty source lists.

## Matters

"Moje sprawy": the logged-in user's own ideas, application inputs ("wsad do wniosku") and notes, kept as
Markdown with a revision counter (`app/routes/matters.py`). Every endpoint requires a login (401 otherwise),
returns 404 for another user's matter (existence is not revealed), and sends `Cache-Control: no-store`.
`type` is `idea_card | application_draft | adaptation_plan | note`; `status` is `draft | ready | sent`
(proposal; `sent` is reserved for the e-mail export).

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/matters` | `ItemList` of summaries (no content), most recently updated first, `?limit=&offset=` |
| POST | `/matters` | `{title, type, content_markdown?, status?}` → 201 `MatterModel`. Empty content starts from the type's standard section template (empty for `note`) |
| GET | `/matters/{id}` | `MatterModel` with `content_markdown` |
| PATCH | `/matters/{id}` | `{expected_revision, title?, status?, content_markdown?}` (at least one change). Compare-and-swap: a stale `expected_revision` returns **409 with the current `MatterModel` as the body** and writes nothing |
| DELETE | `/matters/{id}` | Hard delete, returns `Delete` |
| GET | `/matters/{id}/pdf` | PDF download of `title` + `content_markdown` |
| POST | `/matters/{id}/thread` | `{conversation_id}`: the linked workspace thread when it is active and owned, otherwise a new thread titled after the matter, which becomes linked |

`content_markdown` is at most 20000 characters and `title` 1–200 characters (stripped); violations give 422.
The workspace agent edits the same rows through the same compare-and-swap, so a manual edit is never silently
overwritten.

**Read contract for PDF/e-mail export (Dev 4):** `GET /matters/{id}` returns at least `id`, `title`, `type`,
`status`, `revision`, `content_markdown` and `updated_at`. These fields are stable.

## Contact form

Public contact form for questions to PCI staff without starting a chat (`app/routes/contact.py`).
Both endpoints send `Cache-Control: no-store`.

| Method | Path | Access | Behavior |
| --- | --- | --- | --- |
| POST | `/contact` | public | `{name, email, message, consent: true}` → 201 `{id, created_at}`. Links the message to the logged-in user, if any (a cookie session still needs CSRF). Rate limited by `CONTACT_RATE_LIMIT` (default `5/minute`) per IP |
| GET | `/contact` | admin | `ItemList` of messages (`id, name, email, message, user_id, delivered, created_at`), newest first, `?limit=&offset=` |

`name` is one line of 2-120 characters, `message` 10-5000 characters (both stripped), and `consent` must be `true`;
violations give 422 with the field in `loc`.
The message is always stored first.
When SMTP (`SMTP_*`) and `RADAR_CONTACT_EMAIL` are configured it is also e-mailed there with `Reply-To` set to the sender,
and `delivered` becomes `true`.
A delivery failure is logged and does not fail the request; the response never reveals the delivery outcome.
The frontend BFF allows only `POST` on `contact`; the admin list is available through the backend API only.
