"""
Schemas of the admin statistics (`/stats/*`) and of visit tracking (`POST /visits`).

Days are UTC calendar days. Periods are inclusive (`from` and `to` both count), and
every per-day `series` lists each day of the period, with zeros for days without data.
"""
import datetime as dt
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.location import LocationKind
from app.models.project import ProjectStatus
from app.models.visit import VISIT_PATH_MAX_LENGTH
from app.schemas.default import ItemList
from app.schemas.geojson import FeatureCollection


# ============ visits ============


def _page_path(value: str) -> str:
    """Keeps only the path of a page address: no query string or fragment,
    which could carry search text or personal data."""
    value = value.strip().split("#", 1)[0].split("?", 1)[0]
    if not value.startswith("/"):
        raise ValueError("Path must start with '/'.")
    return value


class VisitCreate(BaseModel):
    """`POST /visits`: the page the visitor opened."""
    path: Annotated[str, AfterValidator(_page_path)] = Field(
        min_length=1, max_length=VISIT_PATH_MAX_LENGTH, examples=["/projects/1"],
        description="Page path; a query string or fragment is dropped before storing.",
    )

    model_config = ConfigDict(extra="forbid")


class VisitModel(BaseModel):
    """A recorded page view (the visitor and user ids are not returned)."""
    id: int = Field(ge=1, examples=[1])
    path: str = Field(examples=["/projects/1"])
    created_at: dt.datetime = Field(examples=["2026-10-03T12:00:00Z"])

    model_config = ConfigDict(from_attributes=True)


# ============ period ============


class Period(BaseModel):
    """An inclusive range of UTC days, serialized as `{"from": ..., "to": ...}`."""
    start: dt.date = Field(serialization_alias="from", examples=["2026-09-04"])
    end: dt.date = Field(serialization_alias="to", examples=["2026-10-03"])

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def bounds(self) -> tuple[dt.datetime, dt.datetime]:
        """`[start 00:00 UTC, day after end 00:00 UTC)` for filtering `created_at` columns."""
        return (
            dt.datetime.combine(self.start, dt.time.min, tzinfo=dt.UTC),
            dt.datetime.combine(self.end + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC),
        )

    def previous(self) -> "Period":
        """The period of the same length right before this one."""
        return Period(start=self.start - dt.timedelta(days=self.days), end=self.start - dt.timedelta(days=1))

    def dates(self) -> list[dt.date]:
        return [self.start + dt.timedelta(days=i) for i in range(self.days)]


# ============ site ============


class SiteDay(BaseModel):
    date: dt.date = Field(examples=["2026-10-03"])
    visits: int = Field(ge=0, examples=[42])
    unique_visitors: int = Field(ge=0, examples=[17])
    conversations: int = Field(ge=0, examples=[9])


class SiteStats(BaseModel):
    period: Period
    visits: int = Field(ge=0, examples=[420], description="Page views.")
    unique_visitors: int = Field(ge=0, examples=[130], description="Distinct people with a page view.")
    conversations: int = Field(ge=0, examples=[85], description="Conversations started.")
    registered_users: int = Field(ge=0, examples=[12], description="All accounts with the `user` role (not per period).")
    series: list[SiteDay]


# ============ tags ============


class TagCounts(BaseModel):
    conversations: int = Field(ge=0, examples=[12], description="Conversations with the tag (each counted once).")
    unique_people: int = Field(ge=0, examples=[10], description="Distinct people in those conversations.")
    no_answer: int = Field(ge=0, examples=[2], description="Those conversations whose outcome is `no_answer`.")


class SubtagStats(TagCounts):
    subtag_id: int = Field(ge=1, examples=[1])
    name: str = Field(examples=["Cyfryzacja szkół"])


class TagStats(TagCounts):
    tag_id: int = Field(ge=1, examples=[1])
    name: str = Field(examples=["Edukacja"])
    subtags: list[SubtagStats]


class TagStatsList(ItemList[TagStats]):
    period: Period


class TagDay(BaseModel):
    date: dt.date = Field(examples=["2026-10-03"])
    conversations: int = Field(ge=0, examples=[3])
    unique_people: int = Field(ge=0, examples=[3])


class TopProject(BaseModel):
    project_id: int = Field(ge=1, examples=[1])
    title: str = Field(examples=["Spółdzielnia sąsiedzka"])
    times_shown: int = Field(ge=0, examples=[7], description="Conversations with the tag that recommended it.")
    unique_searchers: int = Field(ge=0, examples=[6])


class TagDetailStats(TagStats):
    period: Period
    series: list[TagDay]
    top_projects: list[TopProject] = Field(description="Most shown projects in conversations with this tag (up to 10).")


# ============ tag timeline ============


class TimelinePoint(BaseModel):
    """One chart point: the last UTC day of a rolling window of `window_days` days."""
    date: dt.date = Field(examples=["2026-10-03"])
    current: bool = Field(examples=[True], description="In the requested period (false: the previous one).")


class TagTimelineItem(BaseModel):
    tag_id: int = Field(ge=1, examples=[1])
    name: str = Field(examples=["Edukacja"])
    unique_people: int = Field(ge=0, examples=[12], description="Distinct people in the requested period.")
    previous_people: int = Field(ge=0, examples=[8], description="Distinct people in the previous period.")
    change: int = Field(examples=[4], description="`unique_people - previous_people`.")
    change_pct: float | None = Field(examples=[50.0], description="Percent change; null when the previous period had no one.")
    conversations: int = Field(ge=0, examples=[14], description="Conversations in the requested period.")
    no_answer: int = Field(ge=0, examples=[2], description="Of those, with outcome `no_answer`.")
    points: list[int] = Field(description="Distinct people in the window ending on each `dates` day.")


class TagTimeline(ItemList[TagTimelineItem]):
    period: Period
    previous_period: Period
    window_days: int = Field(examples=[7], description="7 for periods up to 92 days, otherwise 28.")
    step_days: int = Field(examples=[1], description="Days between points: 1 for periods up to 92 days, otherwise 7.")
    dates: list[TimelinePoint] = Field(description="Point days of the previous period, then of the requested one.")


# ============ trends ============


class TrendItem(BaseModel):
    """Distinct people searching in a tag (`subtag_id` null) or one of its subtags,
    in the period compared with the previous period of the same length."""
    tag_id: int = Field(ge=1, examples=[1])
    tag_name: str = Field(examples=["Edukacja"])
    subtag_id: int | None = Field(examples=[None])
    subtag_name: str | None = Field(examples=[None])
    current: int = Field(ge=0, examples=[12])
    previous: int = Field(ge=0, examples=[8])
    change: int = Field(examples=[4], description="`current - previous`.")
    change_pct: float | None = Field(examples=[50.0], description="Percent change; null when `previous` is 0.")


class TrendList(ItemList[TrendItem]):
    period: Period
    previous_period: Period
    location_id: int | None = Field(examples=[None])


# ============ projects ============


class ProjectSearchCounts(BaseModel):
    times_shown: int = Field(ge=0, examples=[20], description="Conversations that recommended the project.")
    unique_searchers: int = Field(ge=0, examples=[15], description="Distinct people of those conversations.")
    opened: int = Field(ge=0, examples=[6], description="Recommendations whose project card was opened.")


class ProjectRank(ProjectSearchCounts):
    project_id: int = Field(ge=1, examples=[1])
    title: str = Field(examples=["Spółdzielnia sąsiedzka"])
    status: ProjectStatus = Field(examples=[ProjectStatus.published])


class ProjectRankList(ItemList[ProjectRank]):
    period: Period


class ProjectDay(ProjectSearchCounts):
    date: dt.date = Field(examples=["2026-10-03"])


class ProjectStats(ProjectRank):
    period: Period
    participants_total: int = Field(ge=0, examples=[120], description="All participants (not per period).")
    series: list[ProjectDay]


# ============ workspace ============


class WorkspaceOutcomes(BaseModel):
    """Stored `chat_operations.result.outcome` of the turns. Not the legacy `no_answer` field."""
    matched: int = Field(ge=0, examples=[30], description="Answers that proposed at least one innovation.")
    no_match: int = Field(ge=0, examples=[8], description="Answers without a matching innovation.")
    unavailable: int = Field(ge=0, examples=[2], description="The knowledge base could not answer.")


class WorkspaceDay(WorkspaceOutcomes):
    date: dt.date = Field(examples=["2026-10-03"])
    threads: int = Field(ge=0, examples=[4], description="Workspace threads started.")
    operations: int = Field(ge=0, examples=[9], description="Questions sent (one per user/assistant pair).")


class InnovationRank(BaseModel):
    """A knowledge-base innovation shown in the workspace chat (`innovation_matches`)."""
    innovation_id: str = Field(examples=["uprp-p-441234"])
    title: str = Field(examples=["Czujnik jakości powietrza dla szkół"])
    unique_searchers: int = Field(ge=0, examples=[15], description="Distinct owners of the threads that showed it.")
    times_shown: int = Field(ge=0, examples=[20], description="Threads that showed it (each counted once).")
    opened: int = Field(ge=0, examples=[6], description="Of those, threads where its details were opened.")


class InnovationRankList(ItemList[InnovationRank]):
    period: Period


class WorkspaceStats(BaseModel):
    """The logged-in chat on `/` (workspace threads and their `chat_operations`)."""
    period: Period
    threads: int = Field(ge=0, examples=[40], description="Workspace threads started.")
    unique_users: int = Field(ge=0, examples=[25], description="Distinct owners of those threads.")
    operations: int = Field(ge=0, examples=[110], description="Questions sent in the period.")
    processing: int = Field(ge=0, examples=[0], description="Of those, still being answered.")
    completed: int = Field(ge=0, examples=[100], description="Of those, answered.")
    failed: int = Field(ge=0, examples=[10], description="Of those, failed (retrieval unavailable or expired).")
    outcomes: WorkspaceOutcomes
    series: list[WorkspaceDay]


# ============ locations ============


class LocationCounts(BaseModel):
    conversations: int = Field(ge=0, examples=[14], description="Conversations started with this location.")
    unique_people: int = Field(ge=0, examples=[11], description="Distinct people of those conversations.")
    participants: int = Field(ge=0, examples=[120], description="Project participants from it (not per period).")


class LocationStats(LocationCounts):
    location_id: int = Field(ge=1, examples=[1])
    name: str = Field(examples=["Rzeszów"])
    teryt_code: str = Field(examples=["1863011"])
    kind: LocationKind = Field(examples=[LocationKind.municipality])


class LocationStatsList(ItemList[LocationStats]):
    period: Period
    unknown: LocationCounts = Field(description="Conversations and participants without a location.")


class LocationStatsProperties(LocationCounts):
    """`properties` of a feature in `/stats/locations?format=geojson`."""
    id: int = Field(ge=1, examples=[1])
    name: str = Field(examples=["Rzeszów"])
    teryt_code: str = Field(examples=["1863011"])
    kind: LocationKind = Field(examples=[LocationKind.municipality])


class LocationStatsCollection(FeatureCollection[LocationStatsProperties]):
    """A GeoJSON FeatureCollection; `period` and `unknown` are foreign members that map
    libraries ignore."""
    period: Period
    unknown: LocationCounts
