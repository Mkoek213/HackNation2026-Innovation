# Jev: purpose and usage boundaries

Status: conceptual reference; the implemented decision-model adapter is described in [FASTINO.md](FASTINO.md). Jev access and project performance remain unverified. Source reviewed on 2026-10-03: [TypeSafe announcement, 2026-09-15](https://typesafe.ai/blog/introducing-system-one-models-and-jev). This note explains the concept, not an API contract or a verified benchmark.

## What it is

Jev is TypeSafe's first publicly announced System One model. Here, “System One” names the vendor's model approach for fast, structured decisions; it is not a general standard or a complete autonomous agent.

Instead of generating arbitrary prose token by token, Jev returns values from a predefined typed output space, accompanied by probabilities and confidence information. The vendor describes parallel output sampling and training called Reinforcement Learning for Calibrated Decisions (RLCD).

Conceptual flow: application supplies textual context and predefined decision questions → model evaluates possible outputs → application receives structured decisions and probabilities → application applies its own workflow rules or asks a human to review.

For example, given a synthetic description of isolated older residents, the application could ask which predefined need category fits, whether more context is needed, and which of a supplied shortlist of innovation records appears relevant. These are illustrative questions, not executable SDK syntax.

## When to use it

Consider Jev when the application already knows the possible answers and needs a semantic judgment that ordinary rules cannot adequately express.

| Task in this project | Potential role | Necessary boundary |
| --- | --- | --- |
| Categorize questions and described needs | Select from defined social-need categories | Allow uncertainty and correction |
| Recommend a responsible organization | Score organizations supplied by the application | Verify responsibilities; do not infer an organization directory |
| Assess possible duplicates | Judge candidate pairs retrieved beforehand | Similar needs are not necessarily the same report |
| Rank innovations | Assess fit against supplied descriptions and context | Retrieval must supply actual records and evidence |
| Decide whether clarification is needed | Assess missing or ambiguous context | Application controls the clarification flow |
| Flag an unresolved question for staff review | Support triage | No unvalidated autonomous emergency decisions |

Do not use an AI decision where a deterministic condition suffices: publication permissions, required fields, active grant dates, and role access belong in application rules.

## Nine placement opportunities for agents

This checklist captures the user's requested usage guidance. These are candidate placements, not nine required components or verified performance claims. When designing a workflow, consider Jev for the structured decisions surrounding LLM generation; propose a placement only where the actual task needs it.

| Placement | What Jev decides | Where to put it |
| --- | --- | --- |
| Model routing | Which available LLM or processing path suits the request | Before invoking a generation model; useful when multiple paths actually exist |
| Guardrails | Whether input or retrieved content shows security risks, such as prompt injection | Before passing content to an LLM; supports detection alongside application security controls |
| Tool-call gating | Which permission category a proposed agent action belongs to | Before tool execution; application rules enforce permissions and required user authorization |
| Inbox triage | Topic, priority, spam, archive, or review category | At intake for emails or an administrator's unresolved-question queue |
| Reranking | How relevant each retrieved passage or innovation is to the query | After retrieval and before assembling the answer's evidence packet |
| LLM evaluation | A bounded score for an output against a supplied rubric and evidence | In offline evaluations or a justified post-generation check; a model score is not ground truth |
| Bulk labeling | Categories or attributes for many independent records | In batch processing of historical queries or dataset rows; validate quality, throughput, and cost |
| Real-time decisions | A bounded action or state judgment in a latency-sensitive loop | Where measured latency requirements justify it; trading is a general example, outside this project's scope |
| Confidence gating | Whether to act, clarify, invoke an LLM fallback, or request human review | At semantic decision boundaries, with thresholds validated for each action |

For this MVP, prioritize reranking and confidence gating, with topic labeling and unresolved-query triage supporting administrator insight. Model routing matters only if multiple generation paths are selected. Guardrails, tool gating, and LLM evaluation are possible supporting uses; assess them against concrete requirements rather than adding calls everywhere.

Use an LLM for text generation and Jev for suitable decisions around it. Keep deterministic validation, access control, and workflow enforcement in application code. When proposing Jev, name the input state, bounded question, downstream action, uncertainty path, and check that would establish its value.

## How it relates to RAG

RAG retrieves relevant source material and uses it to ground a response. Jev can participate in a RAG workflow, for example by judging relevance of retrieved candidates. It does not supply the knowledge repository, search index, source provenance, or free-form explanation.

The selected search-first combination is: user question/situation → retrieval of information and innovation candidates → Jev assesses relevance and next action → LLM or templates present a grounded answer and source/project cards. Evaluate this design against representative questions; vendor claims do not establish project performance.

Text extraction and narrative generation may require a different model. Jev's declared typed output design should not be confused with arbitrary string generation.

## What its guarantees do and do not mean

The vendor claims outputs match the predefined schema. A valid category or record identifier can still be the wrong choice. Its “no hallucinations” wording therefore does not establish that classifications, routing, or recommendations are factually correct.

The vendor reports low latency, low cost, and calibrated probabilities. Those are vendor results; we have not measured them for Polish social needs, our corpus, or deployment location. Confidence must be checked against labeled cases before setting automation thresholds. The announcement also notes a maximum choice cardinality of 255, which may matter for large candidate sets; verify current limits in API documentation before implementation.

## Adoption check

1. Confirm early-access credentials and current API capabilities. Access is not established in this repository.
2. Compare with a simpler baseline on the same representative Polish cases: correct matches, unrelated cases, ambiguity, and missing information.
3. Measure decision quality, latency, cost, and whether confidence meaningfully separates correct and incorrect judgments.
4. Check provider data handling and availability against the selected deployment needs.
5. Keep an explicit failure path: timeout or uncertainty leads to an understandable retry or staff review, rather than a silently accepted decision.

## Selected project usage

The user selected Jev as the primary decision engine during chat, with a conventional LLM agent as the fallback for insufficient confidence. Jev selects actions and candidates; an LLM or templates provide conversational text. Retrieval supplies the evidence used by both models. If a decision depends on a prior answer, the application calls the next stage with updated state.

According to the [API introduction](https://docs.typesafe.ai/introduction), Choice selects an option, Score assesses a rubric, and Noul returns a truth probability. Questions in a single call are evaluated independently against the same state. Only Choice and Score include a separate confidence field.

The [confidence documentation](https://docs.typesafe.ai/confidence) defines confidence as a statistic derived from the output distribution. It is not the same as a measured probability that an action is correct. Set thresholds separately for intent, clarification, and relevance, based on representative validation questions. Routing and procedure selection are secondary workflows if included.

Selected flow: Jev decision → if sufficiently confident, perform the permitted workflow step → otherwise LLM agent reviews the same task and evidence. The LLM does not automatically become authoritative merely because Jev was uncertain. If the LLM cannot resolve the case, request missing context and then assign administrator review when uncertainty persists. The core product answers questions and finds information; no report submission is required. Users may request further help despite a project match. Any optional report/application still requires user confirmation before submission. Neither model can invent a formal procedure or override application validation and authorization.

Before implementation, verify Jev access and Polish-language performance. The fallback LLM provider is not selected.

## Usefulness in the current search-first MVP

See [PDF RAG workflow](RAG-WORKFLOW.md) for concrete placement in the ingestion/query pipeline. Jev has no required role in PDF ingestion; its main purpose is query-time decisions and relevance assessment.

The most relevant uses are candidate relevance judgments and choosing between answering, necessary clarification, and an evidence-gap path. Topic labeling can support administrator analytics.

Proposed footprint: one pre-retrieval decision stage and one post-retrieval assessment stage, batching independent questions. Jev does not create arbitrary search strings; compose them in code or with the text LLM when rewriting is needed. Weak topic classification should not exclude otherwise relevant records through hard filtering.

Jev is not required for RAG to function. Its project value must be measured against the same retrieval/answer pipeline using conventional LLM decisions. Preserve the user's Jev selection while testing whether it actually improves fit, latency, cost, or clarity. No project benchmark has been run.
