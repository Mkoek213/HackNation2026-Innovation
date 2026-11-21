"""
Seeds synthetic demo data so the frontend and the statistics have something to show.
Idempotent: a second run creates no duplicates. Run from backend/ or inside the
container, after `alembic upgrade head`:

    python scripts/seed_demo.py [path/to/demo.json]
    docker compose exec backend python scripts/seed_demo.py

Defaults to data/demo/demo.json. In order, it:

- upserts the Podkarpackie locations (data/locations_podkarpackie.geojson);
- creates the missing tags, subtags, demo users, published projects with their
  participants and a generated PDF card, ideas, tester sign-ups and reviews, and the
  tester pool (volunteer profiles with roles, interests and topic tags);
- once, generates a deterministic 60-day history of anonymous and registered
  conversations (tags, project matches, messages of saved ones) and site visits.

Rows are matched by natural keys (tag name, username, project title, ...), so existing
rows, including admin edits, are left alone. The PDF upload needs the S3 storage
(`S3_*` settings, present in Compose); without it the documents are skipped.
Tester applications require the T16 volunteer pool, an existing admin and a reachable,
non-empty knowledge catalog; unavailable prerequisites are reported and can be retried.
Demo users log in with DEMO_USER_PASSWORD (default below); all data is synthetic.
"""
import asyncio
import datetime as dt
import html
import io
import json
import os
import random
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import pymupdf  # noqa: E402
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse  # noqa: E402
from sqlalchemy import exists, or_, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.config import settings  # noqa: E402
from app.database.database import sessionmanager  # noqa: E402
from app.exceptions import DependencyUnavailable  # noqa: E402
from app.models import (  # noqa: E402
    ApplicationSource,
    ApplicationStatus,
    Conversation,
    ConversationOutcome,
    ConversationTag,
    IdeaStatus,
    Location,
    Message,
    MessageRole,
    Project,
    ProjectDocument,
    ProjectMatch,
    ProjectParticipant,
    ProjectStatus,
    Subtag,
    Tag,
    TagSource,
    TesterApplication,
    User,
    UserRole,
    Visit,
)
from app.models.volunteer import VolunteerProfile, VolunteerTag  # noqa: E402
from app.modules.knowledge import Category, KnowledgeUnavailable, get_knowledge_service  # noqa: E402
from app.modules.tester_tags import TesterRole  # noqa: E402
from app.repos.idea_repo import IdeaRepo  # noqa: E402
from app.repos.location_repo import LocationRepo  # noqa: E402
from app.repos.project_repo import (  # noqa: E402
    PDF_CONTENT_TYPE,
    ProjectDocumentRepo,
    ProjectParticipantRepo,
    ProjectRepo,
)
from app.repos.stats_repo import VisitRepo  # noqa: E402
from app.repos.tag_repo import SubtagRepo, TagRepo  # noqa: E402
from app.repos.tester_repo import ReviewRepo, TestSignupRepo  # noqa: E402
from app.repos.user_repo import UserRepo  # noqa: E402
from app.schemas.idea import IdeaCreate  # noqa: E402
from app.schemas.location import LocationImport  # noqa: E402
from app.schemas.project import ParticipantInput, ProjectCreate  # noqa: E402
from app.schemas.stats import VisitCreate  # noqa: E402
from app.schemas.tag import SubtagCreate, TagCreate  # noqa: E402
from app.schemas.tagging import Classification, LabelDecision  # noqa: E402
from app.schemas.tester import ReviewInput, TestSignupCreate  # noqa: E402
from app.schemas.user import UserCreate  # noqa: E402
from app.services.files import FileStorage, get_file_storage  # noqa: E402
from app.utils.crud_repo import CRUDRepo  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FILE = BACKEND_DIR / "data" / "demo" / "demo.json"
LOCATIONS_FILE = BACKEND_DIR / "data" / "locations_podkarpackie.geojson"

DEMO_PASSWORD = os.environ.get("DEMO_USER_PASSWORD", "demo-haslo-2026")
HISTORY_DAYS = 60
ANONYMOUS_VISITORS = 150
#: Fixed seed and namespace: the generated history is the same on every machine.
RANDOM_SEED = 20261003
DEMO_NAMESPACE = uuid.UUID("5b0c3c1e-6d2a-4c55-9a51-0d3e6f1c2026")
#: Municipalities (TERYT) of anonymous conversations, Rzeszów most often.
VISITOR_TERYT = ["1863011"] * 5 + [
    "1861011", "1862011", "1864011", "1817011", "1805011", "1811011", "1803011", "1804011",
]
PAGES = ["/", "/rozmowa", "/knowledge/innovations", "/tester", "/matters", "/contact"]
DOCUMENT_NOTE = (
    "Opis pochodzi z oficjalnej listy projektów Interreg 2021-2027 (interreg.gov.pl). "
    "Lokalizacja na mapie, liczby uczestników, recenzje i statystyki są danymi demonstracyjnymi."
)


def visitor_id(name: str) -> uuid.UUID:
    return uuid.uuid5(DEMO_NAMESPACE, name)


async def find(repo: CRUDRepo, **filters) -> Any:
    """The row matching all column ``filters`` (a natural key), or None."""
    rows = await repo.get_multiple(**filters)
    return rows[0] if rows else None


def read_locations(path: Path) -> list[LocationImport]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = []
    for feature in data["features"]:
        geometry = feature.get("geometry")
        boundary = geometry if geometry and geometry.get("type") in ("Polygon", "MultiPolygon") else None
        items.append(LocationImport(**feature["properties"], boundary=boundary))
    return items


SECTIONS = [("solution", "Na czym polega rozwiązanie?"), ("problem", "Jaki problem rozwiązuje?"),
            ("target_group", "Partnerzy i odbiorcy"), ("who_can_use", "Kto może wdrożyć?"),
            ("does_it_work", "Stan i rezultaty"), ("authors", "Instytucja")]


def project_description(p: dict[str, Any]) -> str:
    return "\n\n".join([f"## {title}\n{p[key]}" for key, title in SECTIONS if p.get(key)]
                       + [f"## Źródło\n[Lista projektów Interreg 2021-2027]({p['website_url']})\n\n_{DOCUMENT_NOTE}_"])


def project_card_pdf(p: dict[str, Any]) -> bytes:
    """A one-page PDF card of the project (Polish text, embedded font)."""
    e = html.escape
    sections = [(title, p[key]) for key, title in SECTIONS if p.get(key)]
    body = "".join(f"<h3>{e(title)}</h3><p>{e(text)}</p>" for title, text in sections)
    page_html = (
        f"<h2>Karta innowacji: {e(p['title'])}</h2><p><i>{e(p['summary'])}</i></p>{body}"
        f"<p style='font-size:9px'>Źródło: {e(p['website_url'])}<br>{e(DOCUMENT_NOTE)}</p>"
    )
    doc = pymupdf.open()
    doc.set_metadata({"title": f"Karta innowacji: {p['title']}", "subject": "Materiał demonstracyjny"})
    doc.new_page().insert_htmlbox(pymupdf.Rect(50, 50, 545, 800), page_html)
    return doc.tobytes(garbage=3, deflate=True)


class DemoSeeder:

    def __init__(self, db: AsyncSession, data: dict[str, Any], storage: FileStorage):
        self.db = db
        self.data = data
        self.storage = storage
        self.created: Counter[str] = Counter()
        self.notes: list[str] = []
        self.locations: dict[str, int] = {}
        self.tags: dict[str, Tag] = {}
        self.subtags: dict[str, Subtag] = {}
        self.users: dict[str, User] = {}
        self.projects: dict[str, Project] = {}

    def location_id(self, teryt_code: str | None) -> int | None:
        return self.locations[teryt_code] if teryt_code is not None else None

    async def run(self) -> None:
        await self.seed_locations()
        await self.seed_tags()
        await self.seed_users()
        await self.seed_projects()
        await self.seed_ideas()
        await self.seed_tester_activity()
        await self.seed_tester_pool()
        await self.seed_tester_applications()
        await self.seed_history()

    async def seed_locations(self) -> None:
        result = await LocationRepo(self.db).import_locations(read_locations(LOCATIONS_FILE))
        self.created["locations"] += result.created
        rows = (await self.db.execute(select(Location.teryt_code, Location.id))).all()
        self.locations = dict(rows)

    async def seed_tags(self) -> None:
        tag_repo, subtag_repo = TagRepo(self.db), SubtagRepo(self.db)
        for item in self.data["tags"]:
            tag = await find(tag_repo, name=item["name"])
            if tag is None:
                tag = await tag_repo.create_tag(TagCreate(name=item["name"], description=item["description"]))
                self.created["tags"] += 1
            self.tags[tag.name] = tag
            for sub in item["subtags"]:
                subtag = await find(subtag_repo, tag_id=tag.id, name=sub["name"])
                if subtag is None:
                    subtag = await subtag_repo.create_subtag(
                        tag.id, SubtagCreate(name=sub["name"], description=sub["description"]),
                    )
                    self.created["subtags"] += 1
                self.subtags[subtag.name] = subtag

    async def seed_users(self) -> None:
        repo = UserRepo(self.db)
        for item in self.data["users"]:
            user = await repo.get_by_username(item["username"])
            if user is None:
                user = await repo.create_user(UserCreate(
                    username=item["username"], email=item["email"], password=DEMO_PASSWORD, role=UserRole.user,
                ))
                self.created["users"] += 1
            self.users[user.username] = user

    async def seed_projects(self) -> None:
        repo = ProjectRepo(self.db)
        for item in self.data["projects"]:
            project = await find(repo, title=item["title"])
            if project is None:
                project = await repo.create_project(ProjectCreate(
                    title=item["title"],
                    summary=item["summary"],
                    description=project_description(item),
                    website_url=item["website_url"],
                    tag_id=self.tags[item["tag"]].id,
                    subtag_id=self.subtags[item["subtag"]].id,
                    location_id=self.location_id(item["teryt_code"]),
                ))
                project = await repo.update({"status": ProjectStatus.published}, id=project.id)
                self.created["projects"] += 1
            self.projects[project.title] = project

            if not await self._has(ProjectParticipant.project_id == project.id):
                await ProjectParticipantRepo(self.db).replace(project.id, [
                    ParticipantInput(location_id=self.location_id(code), participants_count=count)
                    for code, count in item["participants"]
                ])
                self.created["participant rows"] += len(item["participants"])

            if not await self._has(ProjectDocument.project_id == project.id):
                await self._upload_card(project, item)

    async def _upload_card(self, project: Project, item: dict[str, Any]) -> None:
        if "documents" in self.notes:
            return
        pdf = project_card_pdf(item)
        try:
            await ProjectDocumentRepo(self.db).upload(
                project.id, f"Karta innowacji: {project.title}", io.BytesIO(pdf), PDF_CONTENT_TYPE, len(pdf),
                self.storage, max_bytes=settings.max_upload_bytes,
            )
        except DependencyUnavailable as e:
            # Raised by the storage before any row is added.
            self.notes.append("documents")
            print(f"Skipped project PDFs: {e.msg} Configure S3_* and run the script again.")
            return
        self.created["documents"] += 1

    async def seed_ideas(self) -> None:
        repo = IdeaRepo(self.db)
        for item in self.data["ideas"]:
            author = self.users[item["author"]]
            if await find(repo, author_id=author.id, title=item["title"]) is not None:
                continue
            idea = await repo.create_idea(author, IdeaCreate(
                title=item["title"],
                essence=item["essence"],
                target_group=item["target_group"],
                stage=item["stage"],
                tag_id=self.tags[item["tag"]].id,
                location_id=self.location_id(item["teryt_code"]),
            ))
            if item["status"] != IdeaStatus.submitted:
                await repo.update({"status": IdeaStatus(item["status"])}, id=idea.id)
            self.created["ideas"] += 1

    async def seed_tester_activity(self) -> None:
        signups, reviews = TestSignupRepo(self.db), ReviewRepo(self.db)
        for item in self.data["signups"]:
            user, project = self.users[item["user"]], self.projects[item["project"]]
            if await signups.get_mine(project.id, user, quiet=True) is None:
                await signups.sign_up(project.id, user, TestSignupCreate(
                    location_id=self.location_id(item["teryt_code"]), message=item["message"],
                ))
                self.created["test sign-ups"] += 1
        for item in self.data["reviews"]:
            user, project = self.users[item["user"]], self.projects[item["project"]]
            if await find(reviews, project_id=project.id, user_id=user.id) is None:
                await reviews.put_mine(project.id, user, ReviewInput(rating=item["rating"], comment=item["comment"]))
                self.created["reviews"] += 1

    async def seed_tester_pool(self) -> None:
        """
        Volunteer profiles, added as ORM objects: VolunteerRepo.put_mine would call the
        tagging model and stamp the current time. The topic tags come from the data file
        and are recorded as a completed demo classification; join dates are backdated.
        """
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        for item in self.data["testers"]:
            user = self.users[item["user"]]
            if await self._has(VolunteerProfile.user_id == user.id):
                continue
            joined_at = now - dt.timedelta(days=item["joined_days_ago"])
            tags = [self.tags[name] for name in item["tags"]]
            classification = Classification(
                status="completed", model="demo-seed", classified_at=joined_at, decisions=[
                    LabelDecision(tag_id=t.id, name=t.name, probability=0.9, confidence=0.9, selected=True) for t in tags
                ],
            )
            self.db.add(VolunteerProfile(
                user_id=user.id,
                email=user.email,
                phone=item["phone"],
                description=item["description"],
                roles=[str(TesterRole(r)) for r in item["roles"]],
                interests=[str(Category(i)) for i in item["interests"]],
                classification=classification.model_dump(mode="json"),
                consented_at=joined_at,
                created_at=joined_at,
                updated_at=joined_at,
            ))
            # The profile must exist before its tags (foreign key).
            await self.db.flush()
            self.db.add_all([VolunteerTag(user_id=user.id, tag_id=t.id) for t in tags])
            self.created["testers"] += 1
        await self.db.commit()

    async def seed_tester_applications(self) -> None:
        """Apply seeded pool testers to existing knowledge innovations, preserving decisions."""
        profiles = list(await self.db.scalars(
            select(VolunteerProfile).where(VolunteerProfile.user_id.in_([u.id for u in self.users.values()]))
        ))
        if not profiles:
            print("Skipped tester applications: seed the volunteer pool first (T16), then rerun.")
            return
        admin_id = await self.db.scalar(select(User.id).where(User.role == UserRole.admin).order_by(User.id).limit(1))
        if admin_id is None:
            print("Skipped tester applications: start the backend with a bootstrap admin, then rerun.")
            return
        # Release the read transaction before contacting the knowledge service.
        await self.db.commit()
        try:
            service = await get_knowledge_service()
            innovations = sorted(await service.list_innovations(), key=lambda item: item.id)
        except (KnowledgeUnavailable, httpx.HTTPError, ResponseHandlingException, UnexpectedResponse):
            print("Skipped tester applications: knowledge base unavailable. Configure QDRANT_* and rerun.")
            return
        if not innovations:
            print("Skipped tester applications: upload knowledge innovations first, then rerun.")
            return
        existing = set((await self.db.execute(
            select(TesterApplication.user_id, TesterApplication.innovation_id)
            .where(TesterApplication.user_id.in_([p.user_id for p in profiles]))
        )).tuples().all())
        usernames = {user.id: user.username for user in self.users.values()}
        statuses = list(ApplicationStatus)
        now = dt.datetime.now(dt.UTC)
        for index, profile in enumerate(sorted(profiles, key=lambda p: usernames[p.user_id])):
            matching = [item for item in innovations if set(item.categories) & set(profile.interests)]
            # Demonstration applications are not evidence of an assessed match.
            candidates = matching or innovations
            for offset, innovation in enumerate(candidates[:3]):
                if (profile.user_id, innovation.id) in existing:
                    continue
                status = statuses[(index + offset) % len(statuses)]
                created_at = now - dt.timedelta(days=7 + index, hours=offset)
                self.db.add(TesterApplication(
                    user_id=profile.user_id, innovation_id=innovation.id,
                    status=status, source=ApplicationSource.tester,
                    message="Zgłoszenie demonstracyjne: chętnie sprawdzę rozwiązanie i przekażę uwagi z testowania.",
                    created_at=created_at,
                    decided_by=admin_id if status != ApplicationStatus.pending else None,
                    decided_at=created_at + dt.timedelta(days=2) if status != ApplicationStatus.pending else None,
                ))
                existing.add((profile.user_id, innovation.id))
                self.created["tester applications"] += 1
        await self.db.commit()

    async def _has(self, *conditions) -> bool:
        return bool(await self.db.scalar(select(exists().where(*conditions))))

    # ============ history ============

    async def seed_history(self) -> None:
        """
        Conversations and visits over the last HISTORY_DAYS days, generated once.
        The repos stamp new rows with the current time, so the backdated rows are added
        as ORM objects; visits go through VisitRepo.create with an explicit timestamp.
        """
        visitors = [visitor_id(f"visitor-{i}") for i in range(ANONYMOUS_VISITORS)]
        user_ids = [u.id for u in self.users.values()]
        if await self._has(or_(Visit.visitor_id.in_(visitors), Visit.user_id.in_(user_ids))) or await self._has(
            or_(Conversation.visitor_id.in_(visitors), Conversation.user_id.in_(user_ids))
        ):
            print("Demo history already present; skipped.")
            return

        rng = random.Random(RANDOM_SEED)
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        today = now.date()
        trends = {k: v for k, v in self.data["trends"].items() if not k.startswith("_")}
        tag_of_subtag = {s.name: next(t for t in self.tags.values() if t.id == s.tag_id) for s in self.subtags.values()}
        users = list(self.users.values())
        user_teryt = {u["username"]: u["teryt_code"] for u in self.data["users"]}
        visit_repo = VisitRepo(self.db)

        for day_index in range(HISTORY_DAYS):
            day = today - dt.timedelta(days=HISTORY_DAYS - 1 - day_index)
            recent = day_index >= HISTORY_DAYS // 2
            weekend = day.weekday() >= 5
            base = 4 + 3 * day_index / HISTORY_DAYS
            conversations = round(base * (0.6 if weekend else 1.0)) + rng.randint(0, 2)

            def moment() -> dt.datetime:
                start = dt.datetime.combine(day, dt.time(6, 0), dt.timezone.utc)
                return start + dt.timedelta(seconds=rng.randint(0, 16 * 3600))

            # Subtags weighted by the trend multiplier of their tag in this half of the history.
            subtag_names = [name for name in self.data["questions"] if name in self.subtags]
            weights = [trends.get(tag_of_subtag[name].name, [1.0, 1.0])[1 if recent else 0] for name in subtag_names]

            for _ in range(conversations):
                created_at = moment()
                if created_at > now:
                    continue
                subtag = self.subtags[rng.choices(subtag_names, weights)[0]]
                tag = tag_of_subtag[subtag.name]
                user = rng.choice(users) if rng.random() < 0.3 else None
                visitor = None if user else rng.choice(visitors)
                if user is not None:
                    teryt = user_teryt[user.username] if rng.random() < 0.7 else None
                else:
                    teryt = rng.choice(VISITOR_TERYT) if rng.random() < 0.7 else None
                await self._add_conversation(rng, created_at, tag, subtag, user, visitor, self.location_id(teryt))
                await visit_repo.create(
                    VisitCreate(path="/"), autocommit=False, created_at=created_at - dt.timedelta(seconds=30),
                    visitor_id=visitor or visitor_id(f"user-{user.username}"), user_id=user.id if user else None,
                )
                self.created["visits"] += 1

            # Browsing without a conversation.
            for _ in range(rng.randint(8, 18) if not weekend else rng.randint(4, 10)):
                start = moment()
                user = rng.choice(users) if rng.random() < 0.2 else None
                visitor = visitor_id(f"user-{user.username}") if user else rng.choice(visitors)
                for step, path in enumerate(rng.sample(PAGES, rng.randint(1, 3))):
                    created_at = start + dt.timedelta(minutes=step)
                    if created_at > now:
                        break
                    await visit_repo.create(
                        VisitCreate(path=path), autocommit=False, created_at=created_at,
                        visitor_id=visitor, user_id=user.id if user else None,
                    )
                    self.created["visits"] += 1

        await self.db.commit()

    async def _add_conversation(
            self,
            rng: random.Random,
            created_at: dt.datetime,
            tag: Tag,
            subtag: Subtag,
            user: User | None,
            visitor: uuid.UUID | None,
            location_id: int | None,
    ) -> None:
        question = rng.choice(self.data["questions"][subtag.name])
        same_subtag = [p for p in self.projects.values() if p.subtag_id == subtag.id]
        same_tag = [p for p in self.projects.values() if p.tag_id == tag.id and p not in same_subtag]
        candidates = same_subtag + same_tag
        roll = rng.random()
        if not candidates or roll < 0.12:
            outcome, matched = ConversationOutcome.no_answer, []
        elif roll < 0.3:
            outcome, matched = ConversationOutcome.partially_answered, candidates[:1]
        else:
            outcome, matched = ConversationOutcome.answered, candidates[:2]

        conversation = Conversation(
            user_id=user.id if user else None,
            visitor_id=visitor,
            title=question[:200] if user else None,
            outcome=outcome,
            location_id=location_id,
            created_at=created_at,
            last_activity_at=created_at + dt.timedelta(minutes=rng.randint(1, 15)),
        )
        conversation.tags.append(ConversationTag(
            tag_id=tag.id, subtag_id=subtag.id, source=TagSource.ai, created_at=created_at,
        ))
        if rng.random() < 0.15:
            other = rng.choice([t for t in self.tags.values() if t.id != tag.id])
            conversation.tags.append(ConversationTag(tag_id=other.id, source=TagSource.ai, created_at=created_at))
        answered_at = created_at + dt.timedelta(seconds=5)
        for project in matched:
            conversation.matches.append(ProjectMatch(
                project_id=project.id, opened=rng.random() < 0.4, created_at=answered_at,
            ))
        if user is not None:
            conversation.messages.append(Message(role=MessageRole.user, content=question, created_at=created_at))
            conversation.messages.append(Message(
                role=MessageRole.assistant, content=_answer(matched), created_at=answered_at,
                sources=[
                    {"title": p.title, "url": p.website_url, "page": None, "excerpt": p.summary} for p in matched
                ],
            ))
        self.db.add(conversation)
        self.created["conversations"] += 1


def _answer(projects: list[Project]) -> str:
    if not projects:
        return ("Nie znalazłem innowacji, która odpowiada na ten problem. Możesz opisać go dokładniej "
                "albo zgłosić własny pomysł w kreatorze pomysłów.")
    lines = "\n".join(f"- {p.title}: {p.summary}" for p in projects)
    return f"Te innowacje mogą pomóc:\n{lines}\n\nSzczegóły znajdziesz w kartach projektów."


async def seed(path: Path) -> DemoSeeder:
    data = json.loads(path.read_text(encoding="utf-8"))
    await sessionmanager.init_db()
    try:
        # SQLite has no migrations (see app.lifespan); create its tables here too.
        if sessionmanager.dialect_name == "sqlite":
            await sessionmanager.create_db()
        async with sessionmanager.session_maker() as db:
            seeder = DemoSeeder(db, data, get_file_storage())
            await seeder.run()
            return seeder
    finally:
        await sessionmanager.close()


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FILE
    seeder = asyncio.run(seed(path))
    created = ", ".join(f"{count} {name}" for name, count in seeder.created.items() if count) or "nothing"
    print(f"{path.name}: created {created}.")


if __name__ == "__main__":
    main()
