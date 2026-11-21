"""Turn-local evidence adapter. Only the knowledge module owns clients and embeddings."""
import asyncio
import json
import logging
from typing import Literal

from google.genai import types
from pydantic import Field, ValidationError

from app.modules.knowledge import (
    Category, InnovationNotFound, KnowledgeUnavailable, get_knowledge_service,
)
from .schemas import Contract, InnovationMatch, SourceMetadata, Text


logger = logging.getLogger(__name__)


class Search(Contract):
    query: str = Field(min_length=1, max_length=4000)
    categories: list[Category] | None = Field(default=None, max_length=10)


class Get(Contract):
    innovation_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)


class Selection(Contract):
    suitable: bool = Field(description="True only if this innovation positively fits the current user constraints. False for a rejected comparison alternative.")
    innovation_id: str
    evidence_field: Literal["solution", "problem", "novelty", "target_users", "evidence"] = Field(description="Choose the real curated card field supporting this comparison. Code quotes its actual contents; do not transcribe or paraphrase it. User resources do not establish feasibility.")
    fit_reason: Text = Field(description="Polish reason grounded in retrieved evidence. User budget does not establish the innovation price: never claim affordability without a price in the evidence.")
    limitations: list[Text] = Field(min_length=1, max_length=10)


class Select(Contract):
    matches: list[Selection] = Field(max_length=5)


TOOLS = [types.Tool(function_declarations=[
    types.FunctionDeclaration(name=name, description=description, parameters_json_schema=model.model_json_schema())
    for name, description, model in [
        ("search_innovations", "Search innovations (also to find similar existing solutions and avoid duplicated work). Include the problem, solution, users and constraints from the conversation in query. Filter sectors (categories) only if certain.", Search),
        ("get_innovation", "Reload a real innovation by its ID for evidence-based comparison.", Get),
        ("select_innovations", "Select only suitable recommendations from candidates retrieved this turn; exclude unsuitable comparison alternatives. This is an internal validation step, not user approval. Explain supported fit and unknowns in Polish. Empty matches means no suitable candidate. Score is ranking, not fit.", Select),
    ]
])]


class RetrievalTools:
    def __init__(self, factory=get_knowledge_service, timeout=15):
        self.factory, self.timeout = factory, timeout
        self.candidates = {}
        self.evidence = {}
        self.matches = []
        self.selection_validated = False
        self.selection_required = False
        # Search results must be validated before recommending; reloading a known ID (comparison,
        # adaptation plan) must not force a selection step.
        self.searched = False
        self.search_status = None

    def packet(self, meta, score=None, evidence=()):
        sources = [SourceMetadata(id=meta.id, title=meta.title, url=meta.source_url)]
        for item in evidence:
            if item.source_file:
                sources.append(SourceMetadata(id=meta.id,
                    title=meta.title, source_file=item.source_file, page_start=item.page_start,
                    page_end=item.page_end))
        self.candidates[meta.id] = (meta, score, sources)
        self.evidence[meta.id] = list(evidence)
        return {"innovation": meta.model_dump(mode="json"), "retrieval_score": score,
                "evidence": [e.model_dump(mode="json") for e in evidence],
                "cost_caveat": "Budżet użytkownika nie jest ceną innowacji. Koszt i licencję pozostaw do sprawdzenia, jeśli nie ma ich w odczytanych źródłach."}

    async def execute(self, name, arguments):
        try:
            if name == "select_innovations":
                self.selection_required = True
                args = Select.model_validate(arguments)
                if any(m.innovation_id not in self.candidates for m in args.matches):
                    return {"status": "invalid_reference", "message": "Najpierw odczytaj get_innovation dla tych ID w bieżącej turze, potem powtórz select_innovations.", "available_ids": list(self.candidates)}
                if any(m.suitable and not getattr(self.candidates[m.innovation_id][0].card, m.evidence_field).strip() for m in args.matches):
                    return {"status": "unsupported_fit", "message": "Wybrane pole karty jest puste. Wybierz niepuste źródłowe pole albo pomiń kandydata."}
                matches = []
                for m in args.matches:
                    if not m.suitable:
                        continue
                    meta, score, sources = self.candidates[m.innovation_id]
                    if meta.verification != "potwierdzona":
                        return {"status": "unsupported_fit", "message": "Kandydat bez potwierdzenia działania nie może zostać rekomendowany."}
                    actual = getattr(meta.card, m.evidence_field)
                    matches.append(InnovationMatch(id=meta.id, title=meta.title, source_url=meta.source_url,
                        video_url=meta.video_url, retrieval_score=score, fit_reason="Podstawa propozycji (fragment dokumentacji): " + actual[:1200] + ("…" if len(actual) > 1200 else ""),
                        limitations=list(dict.fromkeys([*m.limitations,
                            "Warunki licencji lub transferu, koszt wdrożenia i skuteczność w nowej organizacji wymagają osobnego potwierdzenia."])), sources=sources, solution=meta.card.solution,
                        evidence=self.evidence.get(meta.id, [])))
                self.matches = matches
                self.selection_validated = True
                return {"status": "selected", "matches": [{"id": m.id, "title": m.title} for m in matches]}
            args = Search.model_validate(arguments) if name == "search_innovations" else Get.model_validate(arguments) if name == "get_innovation" else None
            if args is None:
                return {"status": "invalid_tool"}
            async with asyncio.timeout(self.timeout):
                service = await self.factory()
                if name == "search_innovations":
                    hits = await service.retrieve(args.query, categories=args.categories, pool=5, confirmed_only=True)
                    self.search_status = "ok" if hits else "empty"
                    self.searched = self.searched or bool(hits)
                    return {"status": "ok" if hits else "empty", "candidates": [
                        self.packet(h.innovation, h.retrieval_score, h.evidence) for h in hits]}
                meta = await service.get(args.innovation_id)
                # Use the public retrieval boundary to reread indexed source passages too.
                hits = await service.retrieve(meta.title, pool=5)
                evidence = [e for h in hits if h.innovation.id == meta.id for e in h.evidence]
                return {"status": "ok", "candidate": self.packet(meta, evidence=evidence)}
        except ValidationError:
            return {"status": "invalid_arguments"}
        except InnovationNotFound:
            return {"status": "not_found"}
        except (KnowledgeUnavailable, TimeoutError) as exc:
            if name == "search_innovations":
                self.search_status = "unavailable"
            logger.warning("Innovation retrieval unavailable: tool=%s error=%s", name, type(exc).__name__)
            return {"status": "unavailable", "message": "Nie udało się odczytać bazy innowacji. Możemy dalej opisywać innowację bez porównania z bazą."}
        except Exception as exc:
            if name == "search_innovations":
                self.search_status = "unavailable"
            logger.warning("Innovation tool failed: tool=%s error=%s", name, type(exc).__name__)
            # Invalid arguments and dependency failures never expose raw packets/errors.
            return {"status": "invalid_arguments"} if name == "select_innovations" else {"status": "unavailable"}


def bounded_result(result, max_bytes):
    """Trim source text in memory, label omissions, preserve real metadata/IDs."""
    def size():
        return len(json.dumps(result, ensure_ascii=False).encode())
    if size() <= max_bytes:
        return result
    result["truncated"] = True
    candidates = result.get("candidates", []) or ([result["candidate"]] if "candidate" in result else [])
    for limit in (1000, 500, 250, 100, 0):
        for candidate in candidates:
            for evidence in candidate.get("evidence", []):
                evidence["text"] = evidence["text"][:limit]
            card = candidate.get("innovation", {}).get("card", {})
            for key in card:
                card[key] = card[key][:max(limit, 250)]
        if size() <= max_bytes:
            return result
    while len(candidates) > 1 and size() > max_bytes:
        candidates.pop()
        result["omitted_candidates"] = True
    if size() <= max_bytes:
        return result
    return {"status": "evidence_budget_exceeded", "message": "Brak miejsca na źródła; nie rekomenduj bez dowodów."}


def consumed_result(result):
    """Prior tool text is discarded once Gemini has consumed it; keep references."""
    candidates = result.get("candidates", []) or ([result["candidate"]] if "candidate" in result else [])
    return {"status": result.get("status"), "consumed": True,
            "references": [{"id": c["innovation"]["id"], "title": c["innovation"]["title"]} for c in candidates]}
