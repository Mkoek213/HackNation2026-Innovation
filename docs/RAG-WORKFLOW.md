# PDF knowledge ingestion and conversational retrieval

Design notes for ingestion and retrieval; the implemented pipeline lives in `backend/app/modules/knowledge/` and `backend/app/chat/`. Numerical settings below are initial tuning proposals, not measured optima.

## Minimum architecture

### Concise architecture plan

1. **Web UI:** conversational search with inline source citations and innovation cards, natural-language access to knowledge, and conversation history. Admin views cover queries, trends, unresolved questions, and knowledge editing. Demo entry selects user/admin without login; use synthetic conversation data.
2. **One backend:** owns conversation state, retrieval, Jev decisions, LLM calls, citation rendering, and analytics. AI credentials stay server-side. No autonomous multi-agent workflow is required.
3. **Knowledge ingestion:** import PDFs → extract text/OCR as needed → preserve headings and page references → create source chunks and verified innovation cards → generate embeddings → publish an indexed version. Reprocess changed sources without replacing working knowledge on failure.
4. **Storage:** proposed PostgreSQL + pgvector stores documents, chunks, cards, conversations, evidence references, and query outcomes. File/object storage retains original PDFs. Combine semantic and lexical retrieval; providers and embedding model remain undecided.
5. **Question pipeline:** message + thread context → Jev intent/clarification decision → optional LLM query reformulation → hybrid retrieval → Jev relevance assessment → select source evidence → answer/clarify/evidence-gap decision → LLM answer with citations. Dependent Jev decisions run sequentially; uncertain decisions invoke the LLM fallback with the same evidence. Persistent gaps offer admin escalation.
6. **Admin insight:** one thread counts as one expanded query. Aggregate topics, time, voluntarily supplied location, and unresolved needs. AI interpretations link to supporting query groups; knowledge publication updates subsequent retrieval. Feedback is optional and answer-level.
7. **Build and validate:** ingestion and source provenance first; retrieval and cited answers second; Jev decisions/fallback third; admin insight and knowledge updates fourth. Evaluate Polish questions for source retrieval, innovation fit, citation support, no-answer behavior, latency, and cost. Compare Jev with an LLM-decision baseline.

Core responsibility split: **retrieval finds evidence; Jev makes bounded judgments; the LLM generates text; application code enforces workflow rules.** PDF parsing happens during ingestion, not per question. Formal applications and idea submission remain lower-priority extensions. Detailed workflow follows below.

Recommended candidate: one application backend, a PDF ingestion command/job, PostgreSQL with pgvector for shared records and vector search, and file/object storage for original PDFs. Use a PDF extractor such as PyMuPDF, an embedding model validated on Polish material, Jev for bounded decisions, and a text LLM for query reformulation and source-grounded answers. Providers and deployment remain undecided.

Use the same database for knowledge, conversations, and query insight. A separate vector service, agent framework, message broker, and knowledge graph are unnecessary for the first prototype. pgvector supports exact similarity search; start there and introduce approximate indexes only when measured corpus size and latency warrant it. PostgreSQL supports ranked full-text retrieval. Sources: [pgvector](https://github.com/pgvector/pgvector), [PostgreSQL text search](https://www.postgresql.org/docs/current/textsearch-intro.html).

User-facing access is conversational: intent selects report lookup, innovation matching, details/comparison, or escalation. There is no separate searchable user catalog. Internal innovation cards and indexes remain necessary retrieval data.

Users do not need prior knowledge of innovations. Clarify only when it materially improves the answer, reuse conversation context, and provide useful partial information when available. If the full need remains unmet, offer a user-reviewed question/context handoff through the app or staff email. Staff can respond; email delivery/reply integration is a later implementation choice, not an existing capability. See the SMTP handoff in [local development](DEVELOPMENT.md#summary-e-mail-optional-smtp).

## A. Prepare the knowledge corpus before serving questions

1. Register each source: original PDF, title, issuer, public source URL, document type, publication date when known, file hash, version, and import status. Preserve originals so users can open source pages.
2. Extract text with page/block provenance. Check multi-column reading order, headings, repeated headers/footers, broken words, lists, and tables. OCR only pages requiring it (scans or unusable text); visually inspect representative output. PyMuPDF documents extraction-order limitations and page OCR using Tesseract: [text extraction](https://pymupdf.readthedocs.io/en/latest/recipes-text.html), [OCR](https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html).
3. Split into sections and meaningful chunks, preserving headings and page spans. Initial target: roughly 500–800 tokens per chunk with limited overlap (about 50–100 tokens), adjusted to actual layouts. Never merge the end of one innovation with the beginning of another. Keep table headers, units, geographic scope, and time periods with their values; unresolved table extraction goes to review rather than becoming unsupported numerical evidence.
4. Produce innovation cards from their source sections: name, addressed needs, target groups, approach, known implementation requirements, documented results, and source spans. An LLM may draft these records; a curator verifies them. Each card represents one innovation, even when a catalog contains many. Missing costs, results, or availability remain unknown. Reports remain searchable evidence; not every report becomes an innovation card.
5. Embed original chunks and verified innovation-card search text. An embedding is a numerical representation used for similarity retrieval; it is not an answer or a compressed authoritative summary. Store the embedding model/version and use the same compatible embedding space for query vectors. Keep original text alongside vectors.
6. Add lexical retrieval over titles/text for names, acronyms, and exact terms. A simple PostgreSQL text-search configuration can be an initial baseline; it does not solve Polish inflection. Validate Polish retrieval and do not silently use an English stemmer. Merge semantic and lexical rankings by rank, not by adding incompatible raw scores.
7. Validate representative questions, then publish a complete indexed version. On edits, prepare updated chunks/cards and embeddings before switching the active version. Failed imports retain the previous published version; old versions must not mix with new evidence in retrieval. Do not rebuild unchanged documents or process PDFs during every user question.

### Minimum knowledge records

| Record | Essential fields |
| --- | --- |
| Document | ID, title, URL/file location, issuer/type, known dates, hash, active version |
| Chunk | ID, document/version, section path, page span, original text, embedding/model, lexical representation, optional innovation link |
| Innovation | ID, verified card fields, source spans, searchable text/vector, publication state |

Store physical PDF page numbers and printed labels separately when they differ. Citations must map to the original source, not a generated summary. A local PDF citation needs a usable file/viewer route; a public URL may support opening a page, but verify viewer behavior.

## B. Process a user question

Possible next actions: `retrieve`, `clarify`, `answer`, `offer_staff_help`, `prepare_handoff`, or `handle_boundary`. Classify intent separately from the permitted next action; follow-ups reuse thread context and can combine report and innovation retrieval.

1. Load the thread, recent turns, selected innovation IDs, and previously supplied constraints. An optional concise thread summary is secondary to source evidence. Resolve references such as “that project” from conversation state.
2. Jev makes bounded intent/clarification/topic judgments. If uncertain, the LLM resolves meaning or asks a necessary clarification. A broad question can proceed directly to search; uncertain topic labels must not hard-filter out relevant evidence.
3. Construct a standalone search query. Use the original question when sufficient; use a small LLM reformulation for contextual follow-ups. Preserve explicit names, numbers, locations, and constraints. Jev does not generate this free-form query string.
4. Embed the query and perform hybrid retrieval over active published chunks and innovation cards. Search report chunks directly for factual/report questions; do not force all questions through an innovation shortlist. For discovery, cards identify candidates and original chunks substantiate details. Initial working pool: around 15–25 deduplicated candidates, adjusted to evidence size and budget.
5. Jev scores supplied candidates on focused criteria: relevance to the question, fit to the target population, and compatibility with explicit constraints. Ask separate questions for separate judgments. Retrieval similarity, relevance score, and model confidence are distinct signals. Include a no-suitable-candidate path.
6. Assemble a bounded evidence packet: selected original passages, document metadata, page references, relevant cards, and nearby context when necessary. Initial target: about 5–8 substantive passages, diversified across innovations/sources for a comparison. This is not a fixed universal limit: missing necessary context requires targeted expansion, not truncating evidence arbitrarily.
7. Jev chooses answer/clarify/insufficient evidence using the packet. This decision may require a subsequent call after scores are known; independent questions within one call do not consume each other's outputs. Low confidence invokes the LLM agent with the same question and evidence. Allow a bounded targeted re-search where a missing aspect is identifiable; otherwise state the limitation or offer administrator escalation.
8. The text LLM writes a concise Polish answer using the evidence packet, with inline source IDs and innovation IDs. Explain fit and limitations. Distinguish an adoptable innovation from a currently available local service. Never use general model memory as authority for absent eligibility, costs, availability, or report statistics.
9. Application verifies referenced source/project IDs exist in the packet and renders linked citations and cards. ID validation does not prove factual support; check claim-to-source support on the evaluation set. Treat retrieved text as evidence, not executable instructions. Unsupported claims must be removed or explicitly left unresolved.
10. Store messages, selected evidence/version IDs, outcomes, model/fallback path, and latency/cost where measurable. Update the same expanded thread query once for analytics. Optional helpfulness/like belongs to a specific answer. Opening a project or clicking a source alone does not prove resolution.

## C. Concrete interaction example

User: “What solutions help older people who rarely leave home?”

Retrieve innovation cards on social contact and relevant report passages. Jev judges substantive fit and the system presents a short source-backed shortlist, without requiring a municipality.

Follow-up: “Which could a small NGO implement without its own premises?”

Reformulate with the previous need and the new constraints; search implementation sections and judge candidates again. If a source does not specify premises requirements, say so rather than concluding premises are unnecessary. This remains one expanded query thread for admin statistics.

## D. Jev's actual value

Use Jev for intent, clarification decisions, candidate assessment, and next-action selection. It does not parse PDFs, generate embeddings, search the database, write arbitrary query strings, or produce the final explanatory text. Its Choice/Score questions return structured decisions; Noul returns a probability. Questions in a call are independent: [TypeSafe introduction](https://docs.typesafe.ai/introduction).

Confidence summarizes the output distribution, not independently verified truth. Choose thresholds by decision type using representative Polish cases: [TypeSafe confidence](https://docs.typesafe.ai/confidence). A highly confident decision cannot fill a missing source. Avoid a single mandatory threshold for the entire system.

Start with the selected Jev-assisted design and compare against the same retrieval/generation path using conventional LLM decisions. Retain added complexity only when relevance, unnecessary clarification, supported-answer quality, total latency, or cost improves. No such comparison has been run yet.

## E. Implementation order and checks

1. Inspect representative actual PDFs; implement extraction and page-backed chunks. Verify reading order and several tables/scanned pages where present.
2. Store and index the corpus; verify known information can be retrieved, including a proper name and a Polish paraphrase.
3. Implement evidence-based answers and source-page navigation before adding decision automation.
4. Add Jev decisions/ranking and requested LLM fallback; compare on the same questions.
5. Connect chat history, admin knowledge updates, query insights, and optional feedback.

Prepare a small manually reviewed evaluation set (initial proposal: 20–30 questions): report facts, innovation discovery, exact-name lookup, comparison, follow-up constraints, irrelevant questions, no evidence, contradictory/outdated sources, and unknown availability. Check retrieval of the correct source pages separately from answer quality, citation support, and innovation fit. No actual PDF extraction, provider access check, deployment, benchmark, or product implementation has been performed.
