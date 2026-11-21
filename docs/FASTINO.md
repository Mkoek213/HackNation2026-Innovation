# Fastino GLiDE backend interface

The shared asynchronous client lives in `backend/app/integrations/fastino.py` and
can be imported by either backend entry point. It is an internal Python interface;
there is no provider-specific FastAPI route. It does not retrieve documents, generate text,
choose business thresholds, or invoke an LLM fallback. It is used by document ingestion and both persisted conversation paths for topic tagging;
answer generation and retrieval remain independent.

## Setup and lifetime

Copy the root `.env.example` to `.env` and set `FASTINO_API_KEY` with your own
key. From `backend/`, run `uv sync --locked`. Compose supplies the environment;
direct local scripts can use `uv run --env-file ../.env`. Application modules
do not load files themselves. Creating a client or starting
Radar without a key succeeds; requesting inference raises `FastinoError` with
`kind="configuration"`. The key is read when the client is constructed.

Use one client per application lifespan and close it during shutdown. An async
context manager is convenient for scripts. Do not close a shared client while
requests are running, and do not share it between different event loops.

```python
import asyncio

from app.integrations.fastino import (
    ChoiceQuestion, FastinoClient, NoulQuestion, ScoreQuestion,
)


async def main():
    async with FastinoClient() as client:
        result = await client.decide(
            state={
                "question": "Czy są innowacje dla szkół z Podkarpacia?",
                "candidate": "Synthetic innovation: regular neighborhood visits.",
            },
            questions={
                "relevant": NoulQuestion(
                    instructions="Does the candidate address the described need?",
                ),
                "next_action": ChoiceQuestion(
                    instructions="Which next step is supported by the supplied context?",
                    criteria={
                        "assess_candidate": "Assess the supplied innovation further",
                        "clarify": "Ask for materially missing context",
                    },
                ),
                "fit": ScoreQuestion(
                    instructions="Assess the candidate's fit to the expressed need.",
                    criteria=["No fit", "Partial fit", "Strong fit"],
                ),
            },
        )
        print(result.model_dump())


asyncio.run(main())
```

This makes a real, billable request when run with a key. The example has not been
run against Fastino. Its criteria are illustrative, not approved pipeline rules.

## Constructor arguments

`FastinoClient(...)` accepts keyword-only arguments:

| Argument | Default | Meaning |
| --- | --- | --- |
| `api_key: str \| None` | `None` | Use this key, or read `FASTINO_API_KEY` when omitted |
| `read_timeout: float` | `300` | HTTP read timeout in seconds |
| `connect_timeout: float` | `10` | HTTP connection timeout in seconds |
| `total_deadline: float` | `330` | Total inference budget, including attempts and retry delays |
| `max_retries: int` | `2` | Additional attempts after the initial request |

Timeouts must be finite and positive; retries must be a non-negative integer.
The total deadline can interrupt an attempt before its read timeout. HTTPX's write
and pool timeouts use the `read_timeout` value too. Adjust the budget to the
pipeline's latency requirements. The provider recommends at least 300 seconds for
read timeouts; this is guidance, not measured project latency.

## `await client.decide(state, questions)`

| Argument | Accepted values |
| --- | --- |
| `state` | Non-empty text, a non-empty JSON object, or a non-empty JSON array |
| `questions` | Non-empty dictionary of non-blank names to typed questions |

The client accepts the question constructors below; equivalent dictionaries with
an explicit `type` discriminator are validated at runtime too. Results use the
same question names. All questions see the same state and are independent. If a
question needs another question's answer, make a second call with updated state.
Several independent states require separate calls; callers control concurrency.

Every question requires a non-blank `instructions: str`.

| Constructor | `criteria` argument | Result |
| --- | --- | --- |
| `NoulQuestion` | Optional `NoulCriteria(true="...", false="...")`; defaults to Yes/No | `NoulAnswer.noul`: probability of true |
| `ChoiceQuestion` | Dictionary of 2–255 option names to string descriptions | `ChoiceAnswer.choice`: selected option name |
| `ScoreQuestion` | Ordered list of 2–255 string descriptions, lowest level first | `ScoreAnswer.score`: selected zero-based level index |

Each constructor sets its own `type` (`noul`, `choice`, or `score`). Extra question
arguments are rejected. Score dictionaries and arbitrary JSON criteria supported
by some upstream schemas are deliberately excluded from this initial interface:
string descriptions and an ordered list avoid ambiguous scale numbering.

Each rendered state-plus-question prompt must fit the provider's 40,000-token
context window. The client does not tokenize or silently truncate input; the
provider enforces its context limit. It does not stream or support GLiNER models,
training jobs, or fine-tuned GLiDE IDs.

## Return value

`DecisionResult` contains:

| Field | Meaning |
| --- | --- |
| `model` | Provider-reported engine name, including versioned names such as `glide_ro27`; informational only |
| `answers` | Named typed Noul, Choice, or Score answers |
| `usage.input_tokens` | Provider-reported input tokens across internal passes |
| `usage.output_tokens` | Provider-reported output tokens |

Live compatibility check (2026-11-21): the client accepted a `glide_ro27` response for
a synthetic Polish education question. This checks the wire contract, not topic-label quality.

All answers have `type` and `confidence` in `[0, 1]`. Noul additionally has `noul`.
Choice has `choice` and `probabilities` keyed by option name. Score has `score`,
`expected_level`, `probabilities`, and `legend`; its maps use string indexes such
as `"0"`. `expected_level` is the probability-weighted level, distinct from the
winning integer `score`.

Noul confidence is `abs(2 * noul - 1)`; Choice/Score confidence is the probability
margin between the top two outcomes. Confidence is not a validated probability
that the business action is correct. A confident Noul can favor false. Callers
must inspect the result as well as confidence and validate their own thresholds.
The client preserves probabilities without renormalizing them.

The client checks response types, required fields, numeric ranges,
question names, supplied option/level membership, Score legend, probability sums
(tolerance 0.001), and that the selected option is a most probable outcome. Additive
provider fields are preserved. `token_usage` appears in some documentation examples
but is not a required OpenAPI field; use the two `usage` fields instead.

## Errors, retries, and cancellation

Invalid caller inputs raise Pydantic `ValidationError`; invalid constructor budgets
raise `ValueError`. Integration failures raise `FastinoError`:

| `kind` | Meaning |
| --- | --- |
| `configuration` | Missing API key when inference is requested |
| `deadline` | Total budget expired during an attempt or retry delay |
| `timeout` | HTTP timeout exhausted the attempt budget |
| `transport` | Connection/transport failure exhausted the attempt budget |
| `http` | Unsuccessful provider status; inspect `status_code` |
| `response` | Invalid JSON, schema, or question/result correspondence |

Retryable HTTP statuses are `425`, `429`, and `503`. Transport failures also share
the bounded retry budget. `Retry-After` accepts seconds or an HTTP date; otherwise
backoff starts at one second and doubles; a `425` without a header waits 60 seconds
for cold-start warming. Repeated POSTs may incur additional
provider work or billing; no idempotency guarantee is assumed. Permanent HTTP
errors and invalid responses are not retried. Errors contain no API key, input
state, or raw provider body. The module does not log payloads.

Caller cancellation propagates as `asyncio.CancelledError`; it is not swallowed
or retried. Application code chooses whether an integration error means retry,
fallback, or a user-visible failure. Closing the client uses `await client.aclose()`.

## Upstream endpoint and wire arguments

`POST https://api.fastino.ai/v1/systemone` uses `X-API-Key: <key>` and JSON:

```json
{
  "model": "fastino/GLiDE",
  "state": {"message": "Synthetic situation"},
  "questions": {
    "needs_context": {
      "type": "noul",
      "instructions": "Is more context needed?",
      "criteria": {"true": "Yes", "false": "No"}
    }
  }
}
```

The adapter sends only these three top-level fields. The provider's optional
observability/routing fields are not exposed. It fixes the model to the documented
`fastino/GLiDE` ID. An OpenAI chat-completions client is not the GLiDE contract.

Official references: [inference and migration](https://docs.fastino.ai/inference/systemone),
[primitives](https://docs.fastino.ai/concepts/decision-models), and
[OpenAPI](https://docs.fastino.ai/openapi.json). No live inference or Polish decision-quality evaluation
was performed during this implementation. No module tests were added, per the
user's explicit instruction.

## Current integration status

The temporary diagnostic chat integration was removed at the user's request.
`POST /chat` uses knowledge retrieval and its existing demo fallback; it does not
call GLiDE or require `FASTINO_API_KEY`. The shared client remains unchanged and
available for future pipeline integration. Compose still passes the root `.env`
to the backend; fill in the key when a caller actually uses the client.

## Topic tagging

`app/services/tagging.py` batches one Noul question per administrator-defined tag and
subtag. Definitions come from SQL `tags` / `subtags` (create them through the existing
admin endpoints). There is no generated taxonomy and no implicit mapping from the
separate curated sector `Category` enum. Both documents and conversations use the same
SQL tag IDs; curated innovation categories continue to drive existing retrieval filters.

With `FASTINO_API_KEY` configured, new document uploads, the legacy `/conversations` turns and idle workspace conversations call GLiDE.
The client is closed after each bounded classification call (20-second deadline, 15-second read timeout, no retries by default).
No new dependencies are needed.

Workspace conversations are never tagged while a reply is produced: GLiDE latency ranges from about one second to its timeout (measured 2026-10-04), and it used to delay answers by up to 15 seconds.
`app/services/conversation_tagging.py` tags a workspace conversation once it has been idle for `TAGGING_IDLE_SECONDS` (default 300) and its tags do not cover its last activity (`conversations.tagged_at < last_activity_at`, migration `0020`).
Each sweep takes up to 20 due conversations, four decisions in parallel, with a 5-second read timeout and one retry.
A failed decision leaves the conversation due, so the next sweep retries it.
Locally an in-process loop runs the sweep every `TAGGING_SWEEP_SECONDS` (default 60).
Cloud Run sets it to 0 and Cloud Scheduler calls `POST /internal/tagging/sweep` with `X-Admin-Token` every 5 minutes, since Cloud Run allocates CPU only during requests.

- Each label requires `TAGGING_MIN_PROBABILITY` (default 0.8) and
  `TAGGING_MIN_CONFIDENCE` (default 0.6). These are provisional gates, not measured quality
  guarantees. Positive subtags require an accepted parent. Store the subtag pair instead
  of an additional redundant parent-only assignment.
- Store decision probability, confidence, label name snapshot, model, prompt version,
  UTC time, status and truncation flag. Never persist provider input or raw response in
  classification metadata. Conversation classification uses user turns only; anonymous
  transcript content remains unpersisted.
- Completed decisions replace AI labels, preserving manual labels. Uncertain decisions
  add accepted labels while retaining existing ones for review. Provider failures preserve
  existing labels and record a safe error kind. No tags means `empty_taxonomy`; missing
  extracted text means `no_text`. There is no LLM fallback for labeling.
- The explicitly selected legacy `DemoChatEngine` adds its existing keyword assignments without removing earlier labels
  when the key is missing; classification metadata says `unavailable/configuration`.
  The real frontend workspace and documents never fall back to keyword labeling.
- Conversation evidence is stored in `conversations.classification` (migration `0010`),
  and assignments stay in `conversation_tags`. Workspace detail exposes tags and evidence.
  Concurrent sweeps lock the conversation row and skip it when another sweep already covered the same activity.
- Documents carry `tags`, `classification` and a SHA-256 content fingerprint in their
  persisted Qdrant card metadata. Chunks inherit `tag_ids` / `subtag_ids`. Re-uploaded
  identical bytes preserve manual labels and, on classification failure, previous AI labels;
  changed bytes never inherit labels just because filenames match. Unindexed format twins
  and scans have `no_text` and receive no new AI labels.
- Inputs exceeding 24,000 characters use a bounded head/middle/tail sample. Truncation is
  recorded. Full long-document coverage needs a later hierarchical classification design.

Conversations are tagged by the idle sweep (`conversations.tagged_at`). Documents are tagged on upload; existing documents require
re-uploading. This change does not run a historical backfill or build a dashboard. Analytics
should count distinct conversation IDs per tag, and distinct document IDs per tag, rather
than messages or chunks. Keep document coverage and expressed conversation needs separate.
Qdrant labels are snapshots rather than SQL foreign keys; taxonomy deletion does not purge
historical document labels.

Validation uses mocked Fastino inference, SQLite route persistence and in-memory Qdrant;
live Polish classification quality still needs a reviewed evaluation corpus.

No live Fastino inference has been evaluated on Radar data.

Merge integration (2026-10-03): upstream inserted visits as `0008` and moved the workspace
migration to `0009`. Topic classification is now `0010`, following workspace `0009`.
The validation record above describes the pre-merge revision numbering. No tests or
migration execution were run after this integration, per the user's instruction.
