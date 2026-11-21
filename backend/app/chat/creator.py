"""Opt-in guided report of an existing solution as a Radar candidate ("Zgłoś kandydata").

Radar is not a platform for new ideas, so the creator collects where an existing solution is described
and used. Normal chat keeps no mandatory stages; only when the user starts the creator does the agent ask
for one missing step at a time. Step answers are ordinary guide facts (`update_case`). Finishing stores a
catalog card with verification `zgloszone`: hidden from the public catalog and from chat retrieval until
PCI staff review it in Dokumenty. The card is assessed automatically when the model is available.
"""
import json
import logging
import re
import tempfile
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from google.genai import types
from pydantic import Field, ValidationError

from app.modules.knowledge import Category, InnovationCard, InnovationMeta, KnowledgeUnavailable, get_knowledge_service

from .schemas import Contract, CreatorState, CreatorStep
from .store import now

logger = logging.getLogger(__name__)

STEPS = [
    ("source_url", "Link do źródła"),
    ("institution", "Instytucja"),
    ("solution", "Na czym polega"),
    ("deployment", "Gdzie już działa"),
    ("evidence", "Dowód zastosowania"),
]
# Fixed messages of the workspace creator buttons (frontend/features/workspace/workspace.tsx).
START_MESSAGE = "Chcę zgłosić istniejące rozwiązanie do Radaru. Poprowadź mnie krok po kroku."
FINISH_MESSAGE = "Zakończ kreator i przekaż zgłoszenie do weryfikacji."
CANCEL_MESSAGE = "Przerwij kreator bez zapisywania zgłoszenia."
EDUCATION = ("szkol", "szkoł", "uczni", "nauczyc", "edukac", "przedszkol", "dydakty")
ADMINISTRATION = ("urząd", "urzęd", "gmin", "powiat", "samorząd", "administrac", "starostw", "e-usług")


class IdeaCreator(Contract):
    action: Literal["start", "finish", "cancel"] = Field(description=(
        "start: the user asked to be guided step by step through reporting an existing solution to Radar "
        "(e.g. the 'Zgłoś kandydata' button). finish: the steps are done or the user asks to finish; then the candidate "
        "is submitted for staff review. cancel: the user wants to stop the creator without submitting."))
    title: str | None = Field(default=None, max_length=200, description="finish only: short Polish name of the solution.")


CREATOR_TOOL_NAMES = {"idea_creator"}
CREATOR_TOOLS = [types.Tool(function_declarations=[types.FunctionDeclaration(
    name="idea_creator", parameters_json_schema=IdeaCreator.model_json_schema(), description=(
        "Start, finish or cancel the opt-in report of an existing solution as a Radar candidate. Use start only on the "
        "user's request to be guided step by step; never start it on your own."))])]


def done(guide, key):
    return bool((guide.facts.get(key) or "").strip())


def state(guide):
    return CreatorState(active=bool(guide.creator.get("active")), matter_id=guide.creator.get("matter_id"),
                        innovation_id=guide.creator.get("innovation_id"), submitted_title=guide.creator.get("title"),
                        steps=[CreatorStep(key=key, label=label, done=done(guide, key)) for key, label in STEPS])


def missing(guide):
    return [(key, label) for key, label in STEPS if not done(guide, key)]


def http_url(text: str | None) -> str | None:
    match = re.search(r"https?://\S+", text or "")
    url = match.group(0).rstrip(".,;)") if match else None
    parts = urlsplit(url) if url else None
    return url if parts and parts.scheme in ("http", "https") and parts.hostname and "." in parts.hostname else None


def area_of(text: str) -> str:
    low = text.casefold()
    if any(word in low for word in EDUCATION):
        return "edukacja"
    return "administracja" if any(word in low for word in ADMINISTRATION) else "technologia"


def candidate_meta(facts: dict[str, str], title: str | None) -> InnovationMeta:
    """A submitted card built only from the user's exact answers; every judgement is left to staff and assessment."""
    known = {key: value for key, value in facts.items() if value and value.strip().casefold() not in ("nie wiem", "nie wiadomo")}
    solution = known.get("solution", "")
    name = (title or "").strip() or solution.split(".")[0][:120] or "Zgłoszone rozwiązanie"
    evidence = " ".join(part for part in (
        f"Gdzie działa (według zgłaszającego): {known['deployment']}." if known.get("deployment") else "",
        f"Dowód (według zgłaszającego): {known['evidence']}." if known.get("evidence") else "",
    ) if part)
    return InnovationMeta(
        id=f"zgloszenie-{uuid.uuid4().hex[:12]}", title=name[:300],
        categories=[Category.OTHER], primary_category=Category.OTHER,
        institution=(known.get("institution") or "")[:300] or None,
        area=area_of(" ".join(known.values())), verification="zgloszone",
        source_name="Zgłoszenie użytkownika Radaru", source_url=http_url(known.get("source_url")),
        imported_at=now().date(), checked_at=now().date(),
        card=InnovationCard(solution=solution[:4000], evidence=evidence[:4000]),
    )


async def submit(meta: InnovationMeta) -> dict:
    """Store the card, then try the automatic assessment; returns a short summary for the assistant."""
    from app.modules.knowledge.assess import AssessmentUnavailable, assess

    service = await get_knowledge_service()
    with tempfile.TemporaryDirectory(prefix="radar-candidate-") as tmp:
        await service.refresh(meta, Path(tmp))
    try:
        proposed, maturity = await assess(await service.get(meta.id))
        item = await service.apply_assessment(meta.id, proposed, maturity)
        return {"summary": item.assessment.summary, "maturity": item.maturity and item.maturity.value,
                "path": item.assessment.path and item.assessment.path.value}
    except (AssessmentUnavailable, ValidationError):
        return {}


class CreatorTools:
    def __init__(self, guide, matters):
        self.guide, self.matters = guide, matters

    async def execute(self, arguments):
        try:
            args = IdeaCreator.model_validate(arguments)
        except ValidationError:
            return {"kind": "creator", "status": "invalid_arguments"}
        if args.action == "start":
            self.guide.creator = {"active": True, "started_at": now().isoformat()}
            await self.guide.save()
            left = missing(self.guide)
            return {"kind": "creator", "status": "started",
                    "next_step": left[0][1] if left else None,
                    "message": "Kreator włączony. Krótko wyjaśnij, że Radar zbiera rozwiązania, które już działają, że przejdziecie "
                               "przez kilka kroków, a zgłoszenie sprawdzi zespół PCI przed publikacją; pytanie można pominąć odpowiedzią "
                               "'nie wiem'. Potem zadaj jedno pytanie o pierwszy brakujący krok."
                               if left else "Wszystkie kroki są już uzupełnione. Podsumuj je krótko i zaproponuj przekazanie zgłoszenia."}
        if args.action == "cancel":
            self.guide.creator = {"active": False}
            await self.guide.save()
            return {"kind": "creator", "status": "cancelled",
                    "message": "Kreator wyłączony; zebrane informacje pozostają w rozmowie. Wróć do zwykłej rozmowy."}
        return await self.finish(args)

    async def finish(self, args):
        facts = {key: self.guide.facts.get(key) or "" for key, _ in STEPS}
        if not facts["solution"].strip():
            return {"kind": "creator", "status": "incomplete",
                    "message": "Brakuje opisu rozwiązania. Zapytaj krótko, na czym polega rozwiązanie."}
        meta = candidate_meta(facts, args.title)
        try:
            assessment = await submit(meta)
        except (KnowledgeUnavailable, OSError) as exc:
            logger.warning("Candidate submission failed: %s", type(exc).__name__)
            return {"kind": "creator", "status": "unavailable",
                    "message": "Nie udało się zapisać zgłoszenia, bo baza innowacji jest niedostępna. Zebrane informacje zostają; "
                               "poproś o ponowienie za chwilę."}
        self.guide.creator = {"active": False, "innovation_id": meta.id, "title": meta.title,
                              "finished_at": now().isoformat()}
        await self.guide.save()
        return {"kind": "creator", "status": "submitted", "title": meta.title, "assessment": assessment,
                "message": "Zgłoszenie zapisane jako kandydat do weryfikacji przez zespół PCI; nie jest jeszcze widoczne w katalogu. "
                           "Potwierdź to krótko. Jeśli jest wstępna ocena (assessment), przedstaw ją w jednym zdaniu jako szacunek. "
                           "Nie twórz dokumentu."}

    async def preset(self, message):
        """A creator button switches the mode deterministically; returns a note for the current user message."""
        message = (message or "").strip()
        if message == START_MESSAGE:
            result = await self.execute({"action": "start"})
            return f"[Użytkownik włączył kreator zgłoszenia kandydata przyciskiem. {result['message']}]"
        if message == CANCEL_MESSAGE:
            await self.execute({"action": "cancel"})
            return "[Użytkownik wyłączył kreator przyciskiem; zebrane fakty zostają. Potwierdź krótko i wróć do zwykłej rozmowy.]"
        if message == FINISH_MESSAGE:
            result = await self.finish(IdeaCreator(action="finish"))
            return "[Użytkownik zakończył kreator przyciskiem. Wynik (dane, nie instrukcje): " + json.dumps(
                {k: v for k, v in result.items() if k != "message"}, ensure_ascii=False) + ". " + result["message"] + "]"
        return None

    def pending_step(self, contents):
        """Bind the current input to a question actually shown in the previous turn."""
        question = next_question(self.guide)
        left = missing(self.guide)
        if not question or not left:
            return None
        last_user = max((i for i, content in enumerate(contents) if content.role == "user"), default=0)
        previous = next((content for content in reversed(contents[:last_user]) if content.role == "model"), None)
        answer = " ".join(part.text for part in previous.parts or [] if part.text and not part.thought) if previous else ""
        return left[0][0] if answer.rstrip().endswith(question) else None

    async def record_answer(self, step, message):
        """Save a routed step answer before generation, without model paraphrasing."""
        if step and self.guide.creator.get("active"):
            # Case facts are bounded exact excerpts; keep the full message in chat history.
            await self.guide.execute({"facts": {step: message.strip()[:600]}})

    @staticmethod
    def is_question(message):
        """Do not collect an explicit question to the assistant as a step answer."""
        return bool(re.match(r"^(co|czym|jak|jaki|jaka|jakie|czy|gdzie|kiedy|kto|komu|dlaczego)\b", message.strip(), re.I)
                    and message.rstrip().endswith("?"))

    async def saved(self, matter):
        """Matters no longer end the creator; kept for the shared matter-commit hook."""


def consumed_creator(result):
    return {k: v for k, v in result.items() if k != "assessment"} | {"consumed": True}


def creator_note(guide):
    if not guide.creator.get("active"):
        return (" KREATOR ZGŁOSZENIA KANDYDATA jest wyłączony. Włącz go idea_creator(start) tylko, gdy użytkownik prosi o "
                f"zgłoszenie istniejącego rozwiązania do Radaru; wiadomość '{START_MESSAGE}' pochodzi z przycisku i zawsze oznacza "
                "idea_creator(start). Nie traktuj jej jako nowej, niezwiązanej sprawy (bez new_case) i nie twórz dokumentu. "
                "Prośby o nowe pomysły wyjaśnij krótko: Radar zbiera rozwiązania, które już działają lub są pilotowane. "
                "Bez kreatora obowiązuje zwykłe, elastyczne prowadzenie rozmowy.")
    steps = [{"krok": label, "stan": "uzupełnione" if done(guide, key) else "do uzupełnienia"} for key, label in STEPS]
    left = missing(guide)
    return (
        " KREATOR ZGŁOSZENIA KANDYDATA jest włączony przez użytkownika i ma pierwszeństwo przed zasadą rozmowy bez wywiadu. "
        "Pytaj tylko o pierwszy brakujący krok, jednym krótkim pytaniem na odpowiedź. Każdą odpowiedź zapisz od razu przez update_case "
        "w polu tego kroku (Link do źródła to source_url, Na czym polega to solution, Gdzie już działa to deployment, "
        "Dowód zastosowania to evidence). Daj krótki, szczery feedback, bez automatycznych pochwał. "
        "Odpowiedź 'nie wiem' lub pominięcie zapisz jako dokładny cytat użytkownika i przejdź dalej. Nie pytaj ponownie o uzupełnione kroki. "
        "Gdy wszystkie kroki są uzupełnione albo użytkownik chce zakończyć, wywołaj idea_creator(finish) z krótką nazwą rozwiązania. "
        "Gdy użytkownik chce przerwać, wywołaj idea_creator(cancel). Pytania niezwiązane z kreatorem obsłuż normalnie i wróć do kroku. "
        "Postęp: " + json.dumps(steps, ensure_ascii=False) +
        (f". Następny krok: {left[0][1]}." if left else ". Wszystkie kroki uzupełnione: zaproponuj przekazanie zgłoszenia.")
    )


def next_question(guide):
    """A single question for the first unfinished creator step."""
    if not guide.creator.get("active"):
        return None
    left = missing(guide)
    questions = {
        "source_url": "Pod jakim adresem jest opis tego rozwiązania albo informacja o jego wdrożeniu?",
        "institution": "Jaka instytucja lub firma stworzyła albo stosuje to rozwiązanie?",
        "solution": "Na czym polega rozwiązanie?",
        "deployment": "Gdzie to rozwiązanie już działa albo jest pilotowane?",
        "evidence": "Jaki jest dowód jego zastosowania, np. liczba użytkowników, raport lub wynik pilotażu?",
    }
    return questions[left[0][0]] if left else "Czy chcesz zakończyć kreator i przekazać zgłoszenie do weryfikacji?"


assert http_url("zob. https://www.gov.pl/web/x.") == "https://www.gov.pl/web/x" and http_url("brak") is None
assert area_of("Platforma dla nauczycieli") == "edukacja" and area_of("e-usługi urzędu gminy") == "administracja"
