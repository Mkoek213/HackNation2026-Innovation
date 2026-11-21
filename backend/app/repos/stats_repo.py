"""
Admin statistics computed by queries over the application tables (no rollup tables).

Counting rules (DATABASE.md "Statistics"):

- A person is the logged-in user, otherwise the anonymous visitor (:func:`person_key`).
- A conversation counts once per tag (or subtag), however many follow-up messages it has.
- "Searched for a project" = distinct people of the conversations that recommended it.

Days are UTC calendar days (:class:`utc_date`), so the day buckets and the period filters
agree on SQLite and PostgreSQL.
"""
import datetime as dt
from typing import Any
from urllib.parse import unquote

from sqlalchemy import ColumnElement, Date, String, and_, case, cast, distinct, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import aliased
from sqlalchemy.sql.functions import FunctionElement

from app.exceptions import NotFoundError
from app.models import (
    ChatOperation,
    Conversation,
    InnovationMatch,
    ConversationOutcome,
    ConversationTag,
    Location,
    LocationKind,
    Project,
    ProjectMatch,
    ProjectParticipant,
    Subtag,
    Tag,
    User,
    UserRole,
    Visit,
)
from app.repos.project_repo import ParticipantsLevel
from app.schemas.geojson import Feature, point
from app.schemas.stats import (
    InnovationRank,
    InnovationRankList,
    LocationCounts,
    LocationStats,
    LocationStatsCollection,
    LocationStatsList,
    LocationStatsProperties,
    Period,
    ProjectDay,
    ProjectRank,
    ProjectRankList,
    ProjectStats,
    CatalogUse,
    SiteDay,
    SiteStats,
    SubtagStats,
    TagCounts,
    TagDay,
    TagDetailStats,
    TagStats,
    TagStatsList,
    TagTimeline,
    TagTimelineItem,
    TimelinePoint,
    TopProject,
    TrendItem,
    TrendList,
    VisitCreate,
    VisitModel,
    WorkspaceDay,
    WorkspaceOutcomes,
    WorkspaceStats,
)
from app.utils.auth import Actor
from app.utils.crud_repo import CRUDRepo

TOP_PROJECTS_LIMIT = 10
SHORT_TIMELINE_MAX_DAYS = 92


# ============ portable SQL building blocks ============


class utc_date(FunctionElement):
    """The UTC calendar day of a timestamp column, as a `date`."""
    type = Date()
    name = "utc_date"
    inherit_cache = True


@compiles(utc_date)
def _utc_date_default(element, compiler, **kw):
    # SQLite stores timestamps as UTC text (CURRENT_TIMESTAMP, or the value without its offset).
    return f"date({compiler.process(element.clauses, **kw)})"


@compiles(utc_date, "postgresql")
def _utc_date_postgresql(element, compiler, **kw):
    return f"CAST(({compiler.process(element.clauses, **kw)} AT TIME ZONE 'UTC') AS DATE)"


def person_key(user_id: ColumnElement, visitor_id: ColumnElement) -> ColumnElement[str]:
    """`coalesce('u' || user_id, 'v' || visitor_id)`: one key per person for `count(distinct ...)`.
    The prefixes are inline SQL literals, so the expression has no bound parameters."""
    return func.coalesce(
        literal_column("'u'", String) + cast(user_id, String),
        literal_column("'v'", String) + cast(visitor_id, String),
    )


CONVERSATION_PERSON = person_key(Conversation.user_id, Conversation.visitor_id)
VISIT_PERSON = person_key(Visit.user_id, Visit.visitor_id)
#: Catalog events reported as visits (`/_radar/<kind>/<value>`); kept out of page-view counts.
CATALOG_EVENTS = "/_radar/"
PAGE_VIEW = ~Visit.path.startswith(CATALOG_EVENTS)


def parse_catalog_event(path: str) -> tuple[str, str] | None:
    kind, _, value = unquote(path.removeprefix(CATALOG_EVENTS)).partition("/")
    return (kind, value) if path.startswith(CATALOG_EVENTS) and kind and value else None


assert parse_catalog_event("/_radar/region/podkarpackie%20x") == ("region", "podkarpackie x")
assert parse_catalog_event("/_radar/karta") is None and parse_catalog_event("/baza") is None


def in_period(column: ColumnElement, period: Period) -> ColumnElement[bool]:
    start, end = period.bounds()
    return and_(column >= start, column < end)


def within_location(column: ColumnElement, location_id: int) -> ColumnElement[bool]:
    """The location itself and the units inside it (county -> municipalities,
    voivodeship -> counties -> municipalities)."""
    child, grandchild = aliased(Location), aliased(Location)
    children = select(child.id).where(child.parent_id == location_id)
    grandchildren = (
        select(grandchild.id)
        .join(child, grandchild.parent_id == child.id)
        .where(child.parent_id == location_id)
    )
    return or_(column == location_id, column.in_(children), column.in_(grandchildren))


def _count_distinct(column: ColumnElement) -> ColumnElement[int]:
    return func.count(distinct(column))


def _change_pct(current: int, previous: int) -> float | None:
    return None if previous == 0 else round((current - previous) / previous * 100, 1)


# ============ visits ============


class VisitRepo(CRUDRepo[Visit, VisitModel]):

    async def record(self, visit: VisitCreate, actor: Actor) -> Visit:
        """Stores a page view of `actor` (visitor cookie, and the user when logged in)."""
        obj = await self.create(
            visit,
            visitor_id=actor.visitor_id,
            user_id=actor.user.id if actor.user is not None else None,
        )
        await self.db.refresh(obj, attribute_names=["created_at"])
        return obj


# ============ statistics ============


class StatsRepo:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ----- site -----

    async def site(self, period: Period) -> SiteStats:
        day = utc_date(Visit.created_at)
        visit_rows = (await self.db.execute(
            select(day, func.count(Visit.id), _count_distinct(VISIT_PERSON))
            .where(in_period(Visit.created_at, period), PAGE_VIEW)
            .group_by(day)
        )).all()
        visits_by_day = {d: (n, people) for d, n, people in visit_rows}

        conv_day = utc_date(Conversation.created_at)
        conv_by_day = dict((await self.db.execute(
            select(conv_day, func.count(Conversation.id))
            .where(in_period(Conversation.created_at, period))
            .group_by(conv_day)
        )).all())

        totals = (await self.db.execute(
            select(func.count(Visit.id), _count_distinct(VISIT_PERSON))
            .where(in_period(Visit.created_at, period), PAGE_VIEW)
        )).one()
        views = func.count(Visit.id)
        catalog_rows = (await self.db.execute(
            select(Visit.path, views, _count_distinct(VISIT_PERSON))
            .where(in_period(Visit.created_at, period), ~PAGE_VIEW)
            .group_by(Visit.path).order_by(views.desc(), Visit.path).limit(100)
        )).all()
        catalog = [CatalogUse(kind=event[0], value=event[1], views=n, people=people)
                   for path, n, people in catalog_rows if (event := parse_catalog_event(path))]
        registered = await self.db.scalar(select(func.count(User.id)).where(User.role == UserRole.user))

        return SiteStats(
            period=period,
            visits=totals[0],
            unique_visitors=totals[1],
            conversations=sum(conv_by_day.values()),
            registered_users=registered,
            catalog=catalog,
            series=[
                SiteDay(
                    date=d,
                    visits=visits_by_day.get(d, (0, 0))[0],
                    unique_visitors=visits_by_day.get(d, (0, 0))[1],
                    conversations=conv_by_day.get(d, 0),
                )
                for d in period.dates()
            ],
        )

    # ----- workspace -----

    async def workspace(self, period: Period) -> WorkspaceStats:
        """Threads of the logged-in chat started in the period, and the questions sent in it
        (`chat_operations.created_at`) by status and by stored `result.outcome`."""
        thread_day = utc_date(Conversation.created_at)
        thread_rows = (await self.db.execute(
            select(thread_day, func.count(Conversation.id))
            .where(Conversation.workspace.is_(True), in_period(Conversation.created_at, period))
            .group_by(thread_day)
        )).all()
        threads_by_day = dict(thread_rows)
        unique_users = await self.db.scalar(
            select(_count_distinct(Conversation.user_id))
            .where(Conversation.workspace.is_(True), in_period(Conversation.created_at, period))
        )

        op_day = utc_date(ChatOperation.created_at)
        outcome = ChatOperation.result["outcome"].as_string()
        statuses = ("processing", "completed", "failed")
        outcomes = ("matched", "no_match", "unavailable")
        op_rows = (await self.db.execute(
            select(
                op_day,
                func.count(ChatOperation.id),
                *(func.count(case((ChatOperation.status == s, ChatOperation.id))) for s in statuses),
                *(func.count(case((outcome == o, ChatOperation.id))) for o in outcomes),
            )
            .join(Conversation, ChatOperation.conversation_id == Conversation.id)
            .where(Conversation.workspace.is_(True), in_period(ChatOperation.created_at, period))
            .group_by(op_day)
        )).all()
        ops_by_day = {row[0]: tuple(row[1:]) for row in op_rows}
        empty = (0,) * (1 + len(statuses) + len(outcomes))
        totals = [sum(column) for column in zip(empty, *ops_by_day.values())]

        def outcome_counts(values: tuple | list) -> dict[str, int]:
            return dict(zip(outcomes, values[1 + len(statuses):]))

        return WorkspaceStats(
            period=period,
            threads=sum(threads_by_day.values()),
            unique_users=unique_users or 0,
            operations=totals[0],
            **dict(zip(statuses, totals[1:1 + len(statuses)])),
            outcomes=WorkspaceOutcomes(**outcome_counts(totals)),
            series=[
                WorkspaceDay(
                    date=d,
                    threads=threads_by_day.get(d, 0),
                    operations=ops_by_day.get(d, empty)[0],
                    **outcome_counts(ops_by_day.get(d, empty)),
                )
                for d in period.dates()
            ],
        )

    async def innovations(self, period: Period, *, limit: int | None = None, offset: int = 0) -> InnovationRankList:
        """Knowledge-base innovations shown in workspace threads in the period, ranked by distinct
        searchers, times shown, then opens. Only innovations shown at least once."""
        searchers = _count_distinct(Conversation.user_id)
        shown = func.count(InnovationMatch.id)
        opened = func.count(case((InnovationMatch.opened, InnovationMatch.id)))
        where = in_period(InnovationMatch.created_at, period)
        rows = (await self.db.execute(
            select(InnovationMatch.innovation_id, func.max(InnovationMatch.title), searchers, shown, opened)
            .join(Conversation, InnovationMatch.conversation_id == Conversation.id)
            .where(where)
            .group_by(InnovationMatch.innovation_id)
            .order_by(searchers.desc(), shown.desc(), opened.desc(), InnovationMatch.innovation_id)
            .offset(offset)
            .limit(limit)
        )).all()
        total = await self.db.scalar(select(_count_distinct(InnovationMatch.innovation_id)).where(where))
        return InnovationRankList(
            period=period,
            total=total or 0,
            items=[
                InnovationRank(innovation_id=iid, title=title, unique_searchers=people, times_shown=n, opened=o)
                for iid, title, people, n, o in rows
            ],
        )

    # ----- tags -----

    async def _tag_counts(self, group_by: ColumnElement, period: Period, *where: Any) -> dict[int, TagCounts]:
        """Conversation counts per `group_by` (tag or subtag id) of conversations started in the period."""
        no_answer = case((Conversation.outcome == ConversationOutcome.no_answer, Conversation.id))
        rows = (await self.db.execute(
            select(
                group_by,
                _count_distinct(Conversation.id),
                _count_distinct(CONVERSATION_PERSON),
                _count_distinct(no_answer),
            )
            .join(Conversation, ConversationTag.conversation_id == Conversation.id)
            .where(in_period(Conversation.created_at, period), *where)
            .group_by(group_by)
        )).all()
        return {
            key: TagCounts(conversations=conversations, unique_people=people, no_answer=unanswered)
            for key, conversations, people, unanswered in rows
        }

    @staticmethod
    def _rank_key(stats: TagCounts, name: str) -> tuple:
        return -stats.unique_people, -stats.conversations, name

    def _subtag_stats(self, subtags: list[Subtag], counts: dict[int, TagCounts]) -> list[SubtagStats]:
        items = [
            SubtagStats(subtag_id=s.id, name=s.name, **counts.get(s.id, TagCounts(
                conversations=0, unique_people=0, no_answer=0)).model_dump())
            for s in subtags
        ]
        return sorted(items, key=lambda s: self._rank_key(s, s.name))

    async def tags(self, period: Period) -> TagStatsList:
        """Every tag with its subtags, most searched first (unused ones with zeros)."""
        tag_counts = await self._tag_counts(ConversationTag.tag_id, period)
        subtag_counts = await self._tag_counts(
            ConversationTag.subtag_id, period, ConversationTag.subtag_id.is_not(None),
        )
        tags = (await self.db.scalars(select(Tag))).all()
        subtags = (await self.db.scalars(select(Subtag).order_by(Subtag.id))).all()
        empty = TagCounts(conversations=0, unique_people=0, no_answer=0)

        items = [
            TagStats(
                tag_id=tag.id,
                name=tag.name,
                subtags=self._subtag_stats([s for s in subtags if s.tag_id == tag.id], subtag_counts),
                **tag_counts.get(tag.id, empty).model_dump(),
            )
            for tag in tags
        ]
        items.sort(key=lambda t: self._rank_key(t, t.name))
        return TagStatsList(period=period, total=len(items), items=items)

    async def tag(self, tag_id: int, period: Period) -> TagDetailStats:
        """
        One tag: totals, per-day series, subtag breakdown and the most shown projects.
        :raises NotFoundError: missing tag.
        """
        tag = await self.db.get(Tag, tag_id)
        if tag is None:
            raise NotFoundError(resource="Tag", key={"id": tag_id}, loc=("path", "tag_id"))

        counts = (await self._tag_counts(ConversationTag.tag_id, period, ConversationTag.tag_id == tag_id)).get(
            tag_id, TagCounts(conversations=0, unique_people=0, no_answer=0),
        )
        subtag_counts = await self._tag_counts(
            ConversationTag.subtag_id, period,
            ConversationTag.tag_id == tag_id, ConversationTag.subtag_id.is_not(None),
        )
        subtags = (await self.db.scalars(select(Subtag).where(Subtag.tag_id == tag_id))).all()

        day = utc_date(Conversation.created_at)
        series = {d: (n, people) for d, n, people in (await self.db.execute(
            select(day, _count_distinct(Conversation.id), _count_distinct(CONVERSATION_PERSON))
            .join(ConversationTag, ConversationTag.conversation_id == Conversation.id)
            .where(ConversationTag.tag_id == tag_id, in_period(Conversation.created_at, period))
            .group_by(day)
        )).all()}

        tagged = select(ConversationTag.conversation_id).where(ConversationTag.tag_id == tag_id)
        times_shown = func.count(ProjectMatch.id)
        unique_searchers = _count_distinct(CONVERSATION_PERSON)
        top = (await self.db.execute(
            select(Project.id, Project.title, times_shown, unique_searchers)
            .select_from(ProjectMatch)
            .join(Conversation, ProjectMatch.conversation_id == Conversation.id)
            .join(Project, ProjectMatch.project_id == Project.id)
            .where(Conversation.id.in_(tagged), in_period(Conversation.created_at, period))
            .group_by(Project.id, Project.title)
            .order_by(times_shown.desc(), unique_searchers.desc(), Project.id)
            .limit(TOP_PROJECTS_LIMIT)
        )).all()

        return TagDetailStats(
            period=period,
            tag_id=tag.id,
            name=tag.name,
            **counts.model_dump(),
            subtags=self._subtag_stats(list(subtags), subtag_counts),
            series=[
                TagDay(date=d, conversations=series.get(d, (0, 0))[0], unique_people=series.get(d, (0, 0))[1])
                for d in period.dates()
            ],
            top_projects=[
                TopProject(project_id=pid, title=title, times_shown=n, unique_searchers=people)
                for pid, title, n, people in top
            ],
        )

    async def tag_timeline(self, period: Period) -> TagTimeline:
        """
        Every tag with a rolling count of distinct people across the previous period and `period`:
        each point is the number of distinct people in the `window` days ending that day (7 days,
        daily points, for periods up to 92 days; otherwise 28 days every 7th day). Rolling windows
        avoid partial buckets at period edges. Also the period totals, computed from
        (tag, conversation, day, person) rows, so no count is a sum of days.
        """
        previous = period.previous()
        window, step = (7, 1) if period.days <= SHORT_TIMELINE_MAX_DAYS else (28, 7)
        dates: list[TimelinePoint] = []
        for part, current in ((previous, False), (period, True)):
            days = [part.end - dt.timedelta(days=i) for i in range(0, part.days, step)]
            dates += [TimelinePoint(date=d, current=current) for d in reversed(days)]
        first_day = previous.start - dt.timedelta(days=window - 1)

        no_answer = Conversation.outcome == ConversationOutcome.no_answer
        rows = (await self.db.execute(
            select(ConversationTag.tag_id, Conversation.id, utc_date(Conversation.created_at), CONVERSATION_PERSON, no_answer)
            .join(Conversation, ConversationTag.conversation_id == Conversation.id)
            .where(
                Conversation.created_at >= dt.datetime.combine(first_day, dt.time.min, tzinfo=dt.UTC),
                Conversation.created_at < period.bounds()[1],
            )
            .distinct()
        )).all()

        by_day: dict[int, dict[dt.date, set]] = {}
        totals: dict[int, dict[str, set]] = {}
        for tag_id, conversation_id, day, person, unanswered in rows:
            if isinstance(day, str):
                day = dt.date.fromisoformat(day)
            by_day.setdefault(tag_id, {}).setdefault(day, set()).add(person)
            if day < previous.start:
                continue
            bucket = totals.setdefault(tag_id, {"now": set(), "before": set(), "conversations": set(), "no_answer": set()})
            if day >= period.start:
                bucket["now"].add(person)
                bucket["conversations"].add(conversation_id)
                if unanswered:
                    bucket["no_answer"].add(conversation_id)
            else:
                bucket["before"].add(person)

        def rolling(days: dict[dt.date, set]) -> list[int]:
            return [
                len(set().union(*(days.get(p.date - dt.timedelta(days=i), set()) for i in range(window))))
                for p in dates
            ]

        empty = {"now": set(), "before": set(), "conversations": set(), "no_answer": set()}
        items = []
        for tag in (await self.db.scalars(select(Tag))).all():
            t = totals.get(tag.id, empty)
            now, before = len(t["now"]), len(t["before"])
            items.append(TagTimelineItem(
                tag_id=tag.id, name=tag.name, unique_people=now, previous_people=before,
                change=now - before, change_pct=_change_pct(now, before),
                conversations=len(t["conversations"]), no_answer=len(t["no_answer"]),
                points=rolling(by_day.get(tag.id, {})),
            ))
        items.sort(key=lambda i: (-i.unique_people, -i.previous_people, i.name))
        return TagTimeline(
            period=period, previous_period=previous, window_days=window, step_days=step, dates=dates,
            total=len(items), items=items,
        )

    async def trends(self, period: Period, *, location_id: int | None = None) -> TrendList:
        """
        Distinct people per tag and per subtag in `period` vs the previous period of the same
        length, biggest absolute change first. Only tags/subtags with activity in either period.
        :raises NotFoundError: unknown `location_id`.
        """
        if location_id is not None and await self.db.get(Location, location_id) is None:
            raise NotFoundError(resource="Location", key={"id": location_id}, loc=("query", "location_id"))

        previous = period.previous()
        current_start = period.bounds()[0]
        current = _count_distinct(case((Conversation.created_at >= current_start, CONVERSATION_PERSON)))
        before = _count_distinct(case((Conversation.created_at < current_start, CONVERSATION_PERSON)))
        where = [and_(Conversation.created_at >= previous.bounds()[0], Conversation.created_at < period.bounds()[1])]
        if location_id is not None:
            where.append(within_location(Conversation.location_id, location_id))

        def counts(*columns: ColumnElement, extra: tuple = ()):
            return (
                select(*columns, current, before)
                .join(Conversation, ConversationTag.conversation_id == Conversation.id)
                .where(*where, *extra)
                .group_by(*columns)
            )

        tag_rows = (await self.db.execute(counts(ConversationTag.tag_id))).all()
        subtag_rows = (await self.db.execute(counts(
            ConversationTag.tag_id, ConversationTag.subtag_id, extra=(ConversationTag.subtag_id.is_not(None),),
        ))).all()

        tag_names = dict((await self.db.execute(select(Tag.id, Tag.name))).all())
        subtag_names = dict((await self.db.execute(select(Subtag.id, Subtag.name))).all())

        def item(tag_id: int, subtag_id: int | None, now: int, then: int) -> TrendItem:
            return TrendItem(
                tag_id=tag_id,
                tag_name=tag_names[tag_id],
                subtag_id=subtag_id,
                subtag_name=subtag_names[subtag_id] if subtag_id is not None else None,
                current=now,
                previous=then,
                change=now - then,
                change_pct=_change_pct(now, then),
            )

        items = [item(t, None, now, then) for t, now, then in tag_rows]
        items += [item(t, s, now, then) for t, s, now, then in subtag_rows]
        items = [i for i in items if i.current or i.previous]
        items.sort(key=lambda i: (-abs(i.change), -i.current, i.tag_name, i.subtag_name is not None, i.subtag_name or ""))
        return TrendList(
            period=period, previous_period=previous, location_id=location_id, total=len(items), items=items,
        )

    # ----- projects -----

    @staticmethod
    def _match_counts() -> tuple[ColumnElement, ColumnElement, ColumnElement]:
        """times_shown, unique_searchers, opened over `ProjectMatch` joined with its conversation."""
        return (
            func.count(ProjectMatch.id),
            _count_distinct(CONVERSATION_PERSON),
            func.count(case((ProjectMatch.opened, ProjectMatch.id))),
        )

    async def projects(self, period: Period, *, limit: int | None = None, offset: int = 0) -> ProjectRankList:
        """All projects (drafts too) ranked by unique searchers, times shown, then card opens,
        counting the recommendations made in the period."""
        times_shown, unique_searchers, opened = self._match_counts()
        matches = (
            select(
                ProjectMatch.project_id.label("project_id"),
                times_shown.label("times_shown"),
                unique_searchers.label("unique_searchers"),
                opened.label("opened"),
            )
            .join(Conversation, ProjectMatch.conversation_id == Conversation.id)
            .where(in_period(ProjectMatch.created_at, period))
            .group_by(ProjectMatch.project_id)
            .subquery()
        )
        shown = func.coalesce(matches.c.times_shown, 0)
        searchers = func.coalesce(matches.c.unique_searchers, 0)
        opens = func.coalesce(matches.c.opened, 0)
        rows = (await self.db.execute(
            select(Project.id, Project.title, Project.status, shown, searchers, opens)
            .outerjoin(matches, matches.c.project_id == Project.id)
            .order_by(searchers.desc(), shown.desc(), opens.desc(), Project.id)
            .offset(offset)
            .limit(limit)
        )).all()
        total = await self.db.scalar(select(func.count(Project.id)))
        return ProjectRankList(
            period=period,
            total=total,
            items=[
                ProjectRank(
                    project_id=pid, title=title, status=status,
                    times_shown=n, unique_searchers=people, opened=o,
                )
                for pid, title, status, n, people, o in rows
            ],
        )

    async def project(self, project_id: int, period: Period) -> ProjectStats:
        """
        One project (drafts too): recommendations in the period with a per-day series, plus
        all-time participants.
        :raises NotFoundError: missing project.
        """
        project = await self.db.get(Project, project_id)
        if project is None:
            raise NotFoundError(resource="Project", key={"id": project_id}, loc=("path", "project_id"))

        day = utc_date(ProjectMatch.created_at)
        base = (
            select()
            .select_from(ProjectMatch)
            .join(Conversation, ProjectMatch.conversation_id == Conversation.id)
            .where(ProjectMatch.project_id == project_id, in_period(ProjectMatch.created_at, period))
        )
        totals = (await self.db.execute(base.add_columns(*self._match_counts()))).one()
        series = {
            d: (n, people, o)
            for d, n, people, o in (await self.db.execute(
                base.add_columns(day, *self._match_counts()).group_by(day)
            )).all()
        }

        participants = await self.db.scalar(
            select(func.coalesce(func.sum(ProjectParticipant.participants_count), 0))
            .where(ProjectParticipant.project_id == project_id)
        )

        return ProjectStats(
            period=period,
            project_id=project.id,
            title=project.title,
            status=project.status,
            times_shown=totals[0],
            unique_searchers=totals[1],
            opened=totals[2],
            participants_total=participants,
            series=[
                ProjectDay(
                    date=d,
                    times_shown=series.get(d, (0, 0, 0))[0],
                    unique_searchers=series.get(d, (0, 0, 0))[1],
                    opened=series.get(d, (0, 0, 0))[2],
                )
                for d in period.dates()
            ],
        )

    # ----- locations -----

    @staticmethod
    def _target_location(level: ParticipantsLevel) -> ColumnElement:
        """The location a row is counted in: its own, or with `level="county"` the parent
        county of a municipality. NULL for rows without a location."""
        if level != "county":
            return Location.id
        municipality = literal_column(f"'{LocationKind.municipality.value}'", String)
        return case(
            (and_(Location.kind == municipality, Location.parent_id.is_not(None)), Location.parent_id),
            else_=Location.id,
        )

    async def _location_counts(
            self, period: Period, level: ParticipantsLevel,
    ) -> tuple[list[tuple[Location, LocationCounts]], LocationCounts]:
        """(location, counts) for locations with any data, most active first, and the unknown bucket."""
        target = self._target_location(level)

        conversations = (
            select(
                target.label("location_id"),
                Conversation.id.label("conversation_id"),
                CONVERSATION_PERSON.label("person"),
            )
            .select_from(Conversation)
            .outerjoin(Location, Conversation.location_id == Location.id)
            .where(in_period(Conversation.created_at, period))
            .subquery()
        )
        conv_rows = (await self.db.execute(
            select(
                conversations.c.location_id,
                _count_distinct(conversations.c.conversation_id),
                _count_distinct(conversations.c.person),
            ).group_by(conversations.c.location_id)
        )).all()

        participants = (
            select(target.label("location_id"), ProjectParticipant.participants_count.label("count"))
            .select_from(ProjectParticipant)
            .outerjoin(Location, ProjectParticipant.location_id == Location.id)
            .subquery()
        )
        part_rows = (await self.db.execute(
            select(participants.c.location_id, func.sum(participants.c.count))
            .group_by(participants.c.location_id)
        )).all()

        counts: dict[int | None, dict[str, int]] = {}
        for key, n, people in conv_rows:
            counts.setdefault(key, {})
            counts[key].update(conversations=n, unique_people=people)
        for key, total in part_rows:
            counts.setdefault(key, {})["participants"] = int(total or 0)

        def as_counts(values: dict[str, int]) -> LocationCounts:
            return LocationCounts(
                conversations=values.get("conversations", 0),
                unique_people=values.get("unique_people", 0),
                participants=values.get("participants", 0),
            )

        unknown = as_counts(counts.pop(None, {}))
        locations = (await self.db.scalars(select(Location).where(Location.id.in_(counts)))).all() if counts else []
        pairs = [(loc, as_counts(counts[loc.id])) for loc in locations]
        pairs = [(loc, c) for loc, c in pairs if c.conversations or c.participants]
        pairs.sort(key=lambda lc: (-lc[1].conversations, -lc[1].participants, lc[0].name))
        return pairs, unknown

    async def locations(self, period: Period, *, level: ParticipantsLevel = None) -> LocationStatsList:
        pairs, unknown = await self._location_counts(period, level)
        return LocationStatsList(
            period=period,
            total=len(pairs),
            unknown=unknown,
            items=[
                LocationStats(
                    location_id=loc.id, name=loc.name, teryt_code=loc.teryt_code, kind=loc.kind,
                    **counts.model_dump(),
                )
                for loc, counts in pairs
            ],
        )

    async def locations_geojson(self, period: Period, *, level: ParticipantsLevel = None) -> LocationStatsCollection:
        """Locations with data as features (boundary, or centroid Point) with the counts in `properties`."""
        pairs, unknown = await self._location_counts(period, level)
        return LocationStatsCollection(
            period=period,
            unknown=unknown,
            features=[
                Feature[LocationStatsProperties](
                    geometry=loc.boundary or point(loc.longitude, loc.latitude),
                    properties=LocationStatsProperties(
                        id=loc.id, name=loc.name, teryt_code=loc.teryt_code, kind=loc.kind,
                        **counts.model_dump(),
                    ),
                )
                for loc, counts in pairs
            ],
        )
