# Module development

The backend is one FastAPI application, `app.main`, organized by resource rather than by module. Its HTTP contract is described in
[backend/API.md](../backend/API.md) and its data model in [backend/DATABASE.md](../backend/DATABASE.md).

## Frontend modules

| Polish label | Frontend route / feature |
| --- | --- |
| Strona główna (no tab; the radar mark links here) | [route](../frontend/app/page.tsx) / [feature](../frontend/features/home/index.ts) |
| Rozmowa | [route](../frontend/app/rozmowa/page.tsx) / [feature](../frontend/features/workspace/index.ts) |
| Moje sprawy | [route](../frontend/app/matters/page.tsx) / [feature](../frontend/features/matters/index.ts) |
| Baza innowacji (`/knowledge` redirects here) | [route](../frontend/app/knowledge/innovations/page.tsx) / [feature](../frontend/features/knowledge/index.ts) |
| Analityka (admins only) | [route](../frontend/app/administration/analytics/page.tsx) / [feature](../frontend/features/administration/index.ts) |
| Dokumenty (admins only) | [route](../frontend/app/administration/documents/page.tsx) / [feature](../frontend/features/administration/index.ts) |
| Kontakt (everyone, also signed out) | [route](../frontend/app/contact/page.tsx) / [feature](../frontend/features/contact/index.ts) |

Each feature owns `frontend/features/<id>/` and thin `frontend/app/<route>/page.tsx` routes import from its `index.ts`.
Import other features only through public entry points. New top-bar tabs need user approval and an entry in
[components/site-header.tsx](../frontend/components/site-header.tsx).

Shared frontend files include the site header, root layout/CSS, and the API helper. Coordinate shared
interface changes with affected modules and update contracts, documentation, and relevant validation together.

## Implementing one module

1. Read the [challenge](CHALLENGE.md) and the relevant sections of [backend/API.md](../backend/API.md). Define observable
   module behavior, required source evidence, inputs/outputs, invariants, and failure cases.
2. Replace `ModulePage` inside `frontend/features/<id>/`; keep the route thin and export the component from `index.ts`.
   Preserve Polish copy, semantic structure, keyboard access, and responsive behavior.
3. Backend operations live in `backend/app/routes/<resource>.py` with models, schemas, and a `CRUDRepo` per table
   (see `backend/app/routes/users.py`). Follow the conventions section of API.md.
4. Add frontend contract types and calls inside the feature area. Check `/docs.html` and `/openapi.json` against those callers.
5. Validate actual behavior and errors with manual API verification
   and the frontend checks in the [development guide](DEVELOPMENT.md).

## HTTP contracts

Pydantic request/response models and the generated `/openapi.json` of `app.main` are the HTTP contract source of truth;
`/docs.html` provides the interactive reference. The [helper](../frontend/lib/api/client.ts) handles JSON GET requests;
add other methods when actual operations require them. TypeScript generics do not perform runtime schema validation.

`apiGet` uses `NEXT_PUBLIC_API_BASE_URL`, omits credentials, bypasses caching, and accepts an optional `AbortSignal`.
Non-success HTTP responses throw `ApiError` with kind `http` and a numeric status. Connection/CORS failures use `network`
without a status. Invalid JSON uses `response`. Caller cancellation propagates its original rejection. Owners choose
retry and accessible error presentation without exposing raw server payloads. Endpoints that rely on the login or
`visitor_id` cookies need credentialed requests, which the current helper does not send.

### Chat artifacts

The shared chat (not a module) stores innovation cards, submission drafts and deployment plans as latest-only Markdown with a revision counter.
Read them with `GET /chat/conversations/{id}/artifacts[/{artifact_id}]` and edit them with `PATCH` and `expected_revision`; a stale revision returns 409 with the current artifact.
They are owned by the anonymous chat browser identity and are not submitted anywhere.
Browsers reach them through the same-origin `/api/chat/...` proxy.
The contract is the `Artifact`/`ArtifactPatch` schemas in `backend/app/chat/schemas.py` and the generated `/openapi.json`.

## Product boundaries

Read the [challenge](CHALLENGE.md), [Jev guide](JEV.md) and [RAG workflow](RAG-WORKFLOW.md). Preserve source
provenance on every innovation card. Store creators only when they are named in a public source or consent in the chat.
Trends and statistics about Radar usage are administrator-only.

See [development setup](DEVELOPMENT.md) for startup and browser checks.


## Administration analytics

`frontend/features/administration/` owns the admin routes, each its own header tab shown only to admins:
`/administration/analytics` (Analityka) and
`/administration/documents` (Dokumenty: a "Nowa innowacja" tab that uploads documents, autofills the card and creates the innovation, and an "Edytuj istniejącą" tab that edits a card through `PATCH /api/v1/knowledge/innovations/{id}` or replaces its documents through `PUT`). `/administration` redirects to
Dokumenty. Non-admins get a login or forbidden message and no admin request is made.
Analityka reads `GET /stats/site`, `/stats/workspace`, `/stats/tags`, `/stats/trends`,
`/stats/tags/timeline` and the first page of `/stats/innovations` for one inclusive UTC period
(default: last 30 days). "Tematy w czasie" draws one inline SVG line chart per topic from the
timeline (no chart library); the tag and trend tables stay available in collapsed disclosures.
The BFF allowlists `GET` only under `stats/site`, `stats/workspace`, `stats/innovations`,
`stats/trends`, `stats/tags[/{id}|/timeline]` and `stats/projects[/{id}]`; other methods return 405. The FastAPI admin
dependency remains the authorization boundary.

The data behind it is produced by the rest of the frontend:

- `components/visit-tracker.tsx` (mounted in the root layout) sends `POST /visits` once per
  pathname, through `recordVisit` in the workspace API client. It adds the CSRF header for
  logged-in sessions and ignores failures. The BFF allows only `POST` on `visits`.
- The chat calls `POST /workspace/conversations/{id}/innovations/{innovation_id}/open` when an
  innovation's source dialog opens; shown innovations themselves are recorded by the backend.

## Contact form

`/contact` (feature `frontend/features/contact/`) is the last top-bar tab for everyone, also before sign-in. It posts through `publicPost` from the workspace entry point, which works without a session and
retries once with a refreshed CSRF token for a logged-in cookie session. The form validates on submit with Polish
messages, shows a focused error summary linking to each field, maps backend 422 fields to the same messages, and
moves focus to the confirmation heading after sending. Logged-in users get their account e-mail prefilled.
See [Contact form](../backend/API.md#contact-form) for the endpoint.
