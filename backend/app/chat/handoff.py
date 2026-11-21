"""Build a reviewable email from current facts, advice and canonical latest drafts.

No generation, external delivery or raw transcript forwarding. Authorization belongs
at the workspace route; deterministic account-thread IDs never grant ownership.
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.models import ChatOperation, Message, User, UserRole
from app.services.mail import mail_delivery_available
from app.schemas.workspace import HandoffAttachment, StaffContact
from app.models.chat import ChatArtifact, ChatGuide
from app.models.matter import Matter
from .guide import CONTEXT, FIELDS, NOTE_LABELS
from .workspace import thread_conversation_id


async def staff_contacts(db) -> list[StaffContact]:
    rows = (await db.scalars(
        select(User).where(User.role == UserRole.admin, User.email.is_not(None)).order_by(User.username),
    )).all()
    seen: set[str] = set()
    items: list[StaffContact] = []
    configured = (settings.radar_contact_email or "").strip().lower()
    if configured:
        items.append(StaffContact(name="PCI (kontakt główny)", email=configured))
        seen.add(configured)
    for row in rows:
        email = (row.email or "").strip().lower()
        if not email or email in seen:
            continue
        items.append(StaffContact(name=row.username, email=email))
        seen.add(email)
    return items


async def prepare_handoff(db, thread, recipient, user_id=None):
    if await db.scalar(select(ChatOperation.id).where(
        ChatOperation.conversation_id == thread.id, ChatOperation.status == "processing",
    )):
        raise HTTPException(409, "Poczekaj na zakończenie odpowiedzi przed przygotowaniem wiadomości.")
    cid = str(thread_conversation_id(thread.id))
    guide = await db.get(ChatGuide, cid)
    data = guide.data if guide else {}
    facts, notes = data.get("facts") or {}, data.get("notes") or {}
    blocks = ["PODSUMOWANIE SPRAWY", "Materiał do konsultacji przygotowany z pomocą asystenta AI. Sprawdź fakty, propozycje i niewiadome przed udostępnieniem. To nie jest oficjalne zgłoszenie."]
    lines = [f"{label}: {facts[name]}" for name, (label, _) in FIELDS.items() if facts.get(name)]
    if lines:
        blocks.append("MOJA SYTUACJA\n" + "\n".join(lines))
    if facts.get(CONTEXT[0]):
        blocks.append(f"KONTEKST ZE ŹRÓDEŁ\n{facts[CONTEXT[0]]}")
    for name, label in NOTE_LABELS.items():
        if notes.get(name):
            blocks.append(f"{label.upper()}\n{notes[name]}")
    started = datetime.fromisoformat(data["case_started_at"]) if data.get("case_started_at") else None
    query = select(ChatOperation).where(
        ChatOperation.conversation_id == thread.id, ChatOperation.status == "completed",
    )
    if started:
        # The workspace assistant message is saved after case collection finishes,
        # so the current case's first operation is retained despite its earlier start.
        query = query.join(Message, Message.id == ChatOperation.assistant_message_id).where(Message.created_at >= started)
    completed = (await db.scalars(query.order_by(ChatOperation.id.desc()).limit(100))).all()
    if not lines and completed:
        blocks.append("MÓJ OPIS SPRAWY\n" + completed[0].content)
    if completed and not any(notes.values()) and completed[0].result:
        blocks.append("OSTATNIA ODPOWIEDŹ ASYSTENTA AI\n" + completed[0].result["answer"])
    matches = next((o.result.get("innovations") for o in completed if o.result and o.result.get("innovations")), [])
    if matches:
        blocks.append("ROZWAŻANE INNOWACJE\n" + "\n\n".join(
            "\n".join(filter(None, [m["title"], m.get("fit_reason"),
                "Ograniczenia: " + "; ".join(m["limitations"]) if m.get("limitations") else None,
                m.get("source_url")])) for m in matches))
    source_rows = [s for o in completed if o.result for s in o.result.get("sources", [])]
    # Read actual current rows, never old operation snapshots (manual changes survive).
    artifacts = (await db.scalars(select(ChatArtifact).where(
        ChatArtifact.conversation_id == cid,
    ).order_by(ChatArtifact.updated_at, ChatArtifact.id))).all()
    for artifact in artifacts:
        if started and artifact.created_at.replace(tzinfo=started.tzinfo) < started:
            continue
        blocks.append(f"DOKUMENT ROBOCZY: {artifact.title}\n{artifact.content_markdown}")
        source_rows += artifact.sources or []
    # Workspace drafts are now user-owned matters; include their canonical current
    # content only when linked to this thread and created within this case.
    matter_query = select(Matter).where(Matter.user_id == thread.user_id, Matter.conversation_id == thread.id)
    if started:
        matter_query = matter_query.where(Matter.created_at >= started)
    for matter in (await db.scalars(matter_query.order_by(Matter.updated_at, Matter.id))).all():
        blocks.append(f"DOKUMENT ROBOCZY: {matter.title}\n{matter.content_markdown}")
    if not notes.get("open_questions"):
        blocks.append("PYTANIE DO PCI\nProszę o wskazanie możliwych kolejnych kroków i informacji, które warto uzupełnić.")
    sources = { (s.get("id"), s.get("url"), s.get("page_start")): s for s in source_rows }
    if sources:
        blocks.append("ŹRÓDŁA\n" + "\n\n".join("\n".join(filter(None, [s.get("title"),
            "Rok / data: " + s["publication_date"] if s.get("publication_date") else None,
            "Obszar: " + s["geography"] if s.get("geography") else None,
            "Strony: " + str(s["page_start"]) + ("-" + str(s["page_end"]) if s.get("page_end") else "") if s.get("page_start") else None,
            s.get("source_file"), s.get("url")])) for s in sources.values()))
    subject = "Radar innowacji - " + (facts.get("idea") or facts.get("problem") or thread.title or "prośba o konsultację")
    staff = await staff_contacts(db)
    default_recipient = (recipient or "").strip() or (staff[0].email if staff else "")
    attachments = [HandoffAttachment(id=a.id, kind="artifact", title=a.title) for a in artifacts
                   if not started or a.created_at.replace(tzinfo=started.tzinfo) >= started]
    owner_matters = (await db.scalars(select(Matter).where(Matter.user_id == thread.user_id)
                    .order_by(Matter.updated_at.desc()).limit(50))).all()
    attachments += [HandoffAttachment(id=str(m.id), kind="matter", title=m.title) for m in owner_matters]
    return {"staff": staff, "attachments": attachments,
            "mail_delivery": "server" if mail_delivery_available() else "client", "recipient": default_recipient, "subject": " ".join(subject.split())[:200],
            "body": "Dzień dobry,\n\nproszę o konsultację opisanej w załączonym podsumowaniu sprawy i wskazanie możliwych kolejnych kroków.\n\nZ poważaniem\n[Imię / nazwa instytucji do uzupełnienia]",
            "packet": "\n\n".join(blocks)}


async def resolve_attachment(db, user_id: int, thread_id: int, artifact_id: str | None, matter_id: int | None):
    """Return (title, markdown) for the selected attachment, or (None, None)."""
    if artifact_id:
        cid = str(thread_conversation_id(thread_id))
        artifact = await db.scalar(select(ChatArtifact).where(
            ChatArtifact.id == artifact_id, ChatArtifact.conversation_id == cid,
        ))
        if artifact is None:
            raise HTTPException(404, "Nie znaleziono wybranego dokumentu roboczego.")
        return artifact.title, artifact.content_markdown
    if matter_id is not None:
        matter = await db.scalar(select(Matter).where(Matter.id == matter_id, Matter.user_id == user_id))
        if matter is None:
            raise HTTPException(404, "Nie znaleziono wybranej sprawy.")
        return matter.title, matter.content_markdown
    return None, None


def append_matters_to_body(body: str, matters: list[Matter]) -> str:
    if not matters:
        return body
    block = "MOJE SPRAWY\n" + "\n\n".join(f"### {m.title}\n{m.content_markdown}" for m in matters)
    return f"{body.rstrip()}\n\n{block}\n"
