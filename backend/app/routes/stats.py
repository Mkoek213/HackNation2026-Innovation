import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, status

from app.dependencies import DatabaseDep, PaginationDep
from app.docs import Tags
from app.exceptions import ValidationError
from app.repos.project_repo import ParticipantsLevel
from app.repos.stats_repo import StatsRepo
from app.schemas.default import NOT_FOUND
from app.schemas.stats import (
    InnovationRankList,
    LocationStatsCollection,
    LocationStatsList,
    Period,
    ProjectRankList,
    ProjectStats,
    SiteStats,
    TagDetailStats,
    TagStatsList,
    TagTimeline,
    TrendList,
    WorkspaceStats,
)
from app.utils.auth import get_current_admin

router = APIRouter(
    prefix="/stats",
    tags=[Tags.Statistics],
    responses={},
)

DEFAULT_PERIOD_DAYS = 30
MAX_PERIOD_DAYS = 366


def get_period(
        date_from: dt.date | None = Query(
            None, alias="from", description="First day (UTC), inclusive. Default: 29 days before `to`.",
        ),
        date_to: dt.date | None = Query(
            None, alias="to", description="Last day (UTC), inclusive. Default: today.",
        ),
) -> Period:
    """
    Reads `?from=&to=` (ISO dates). Without both, the period is the last 30 days including today;
    with only `from`, it ends today; with only `to`, it is the 30 days ending then.
    :raises ValidationError: `to` before `from`, or a period longer than 366 days (422).
    """
    if date_to is None:
        date_to = dt.datetime.now(dt.UTC).date()
    if date_from is None:
        date_from = date_to - dt.timedelta(days=DEFAULT_PERIOD_DAYS - 1)
    if date_to < date_from:
        raise ValidationError(msg="`to` must not be before `from`.", loc=("query", "to"), input_=str(date_to))
    period = Period(start=date_from, end=date_to)
    if period.days > MAX_PERIOD_DAYS:
        raise ValidationError(
            msg=f"The period must not be longer than {MAX_PERIOD_DAYS} days.",
            loc=("query", "from"), input_=str(date_from),
        )
    return period


PeriodDep = Annotated[Period, Depends(get_period)]
LevelQuery = Annotated[ParticipantsLevel, Query(description="`county` sums municipalities into their county (powiat).")]


@router.get("/site",
            dependencies=[Depends(get_current_admin)],
            response_model=SiteStats,
            status_code=status.HTTP_200_OK,
            summary="Get site usage statistics",
            response_description="Successful Response")
async def get_site_stats(
        db: DatabaseDep,
        period: PeriodDep,
):
    """
    Page views, distinct visitors and conversations in the period, with a per-day series,
    and the number of registered users. Admin only. \\
    A person is the logged-in user, otherwise the anonymous visitor.
    """
    return await StatsRepo(db).site(period)


@router.get("/workspace",
            dependencies=[Depends(get_current_admin)],
            response_model=WorkspaceStats,
            status_code=status.HTTP_200_OK,
            summary="Get chat workspace statistics",
            response_description="Successful Response")
async def get_workspace_stats(
        db: DatabaseDep,
        period: PeriodDep,
):
    """
    The logged-in chat on `/`: workspace threads started in the period and their distinct owners,
    plus the questions sent in the period by status and by stored outcome (`matched`, `no_match`,
    `unavailable`), with a per-day series. Admin only. \\
    Outcomes come from `chat_operations.result`; they are unrelated to the legacy `no_answer` count.
    """
    return await StatsRepo(db).workspace(period)


@router.get("/innovations",
            dependencies=[Depends(get_current_admin)],
            response_model=InnovationRankList,
            status_code=status.HTTP_200_OK,
            summary="Get chat innovation ranking",
            response_description="Successful Response")
async def get_innovation_stats(
        db: DatabaseDep,
        period: PeriodDep,
        page: PaginationDep,
):
    """
    Knowledge-base innovations shown in the logged-in chat in the period, ranked by
    `unique_searchers`, then `times_shown`, then `opened`. Admin only. \\
    A thread counts once per innovation. Paginated with `?limit=&offset=` (`total` is the number
    of innovations shown at least once). Legacy `project_matches` are in `/stats/projects`.
    """
    return await StatsRepo(db).innovations(period, limit=page.limit, offset=page.offset)


@router.get("/tags",
            dependencies=[Depends(get_current_admin)],
            response_model=TagStatsList,
            status_code=status.HTTP_200_OK,
            summary="Get tag statistics",
            response_description="Successful Response")
async def get_tag_stats(
        db: DatabaseDep,
        period: PeriodDep,
):
    """
    Every tag with its subtags nested: `{conversations, unique_people, no_answer}` for the
    conversations started in the period, most searched first. Admin only. \\
    A conversation counts once per tag and subtag, however many follow-up messages it has.
    """
    return await StatsRepo(db).tags(period)


@router.get("/tags/timeline",
            dependencies=[Depends(get_current_admin)],
            response_model=TagTimeline,
            status_code=status.HTTP_200_OK,
            summary="Get tag timeline",
            response_description="Successful Response")
async def get_tag_timeline(
        db: DatabaseDep,
        period: PeriodDep,
):
    """
    Every tag with a rolling count of distinct people across the previous period of the same length
    and the requested one: each point counts the people of the `window_days` days ending on its date
    (7-day window with daily points up to 92 days, otherwise a 28-day window every 7th day), plus
    period totals: `unique_people`, `previous_people`, `change`, `change_pct`, `conversations`,
    `no_answer`. Most searched first. Admin only.
    """
    return await StatsRepo(db).tag_timeline(period)


@router.get("/tags/{tag_id}",
            dependencies=[Depends(get_current_admin)],
            response_model=TagDetailStats,
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Get one tag statistics",
            response_description="Successful Response")
async def get_tag_stats_one(
        db: DatabaseDep,
        period: PeriodDep,
        tag_id: int = Path(ge=1),
):
    """
    One tag: totals, per-day series, subtag breakdown and the 10 projects most often recommended
    in its conversations. Admin only. \\
    Raises 404 Not Found when the tag does not exist.
    """
    return await StatsRepo(db).tag(tag_id, period)


@router.get("/trends",
            dependencies=[Depends(get_current_admin)],
            response_model=TrendList,
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Get tag trends",
            response_description="Successful Response")
async def get_trends(
        db: DatabaseDep,
        period: PeriodDep,
        location_id: int | None = Query(
            None, ge=1, description="Only conversations from this location or the units inside it.",
        ),
):
    """
    Distinct people searching in each tag (`subtag_id` null) and subtag in the period compared
    with the previous period of the same length, biggest absolute change first. Admin only. \\
    `change_pct` is null when the previous period had no one. Tags and subtags without activity
    in both periods are left out. Raises 404 Not Found for an unknown `location_id`.
    """
    return await StatsRepo(db).trends(period, location_id=location_id)


@router.get("/projects",
            dependencies=[Depends(get_current_admin)],
            response_model=ProjectRankList,
            status_code=status.HTTP_200_OK,
            summary="Get project ranking",
            response_description="Successful Response")
async def get_project_stats(
        db: DatabaseDep,
        period: PeriodDep,
        page: PaginationDep,
):
    """
    All projects (drafts too) ranked by `unique_searchers`, then `times_shown`, then `opened`,
    counting the chat recommendations made in the period. Admin only. \\
    Paginated with `?limit=&offset=` (`total` is the number of projects).
    """
    return await StatsRepo(db).projects(period, limit=page.limit, offset=page.offset)


@router.get("/projects/{project_id}",
            dependencies=[Depends(get_current_admin)],
            response_model=ProjectStats,
            responses={status.HTTP_404_NOT_FOUND: NOT_FOUND},
            status_code=status.HTTP_200_OK,
            summary="Get one project statistics",
            response_description="Successful Response")
async def get_project_stats_one(
        db: DatabaseDep,
        period: PeriodDep,
        project_id: int = Path(ge=1),
):
    """
    One project: recommendations in the period (`times_shown`, `unique_searchers`, `opened`) with a
    per-day series, plus all-time `participants_total`. Admin only. \\
    Raises 404 Not Found when the project does not exist.
    """
    return await StatsRepo(db).project(project_id, period)


@router.get("/locations",
            dependencies=[Depends(get_current_admin)],
            response_model=LocationStatsList | LocationStatsCollection,
            status_code=status.HTTP_200_OK,
            summary="Get location statistics",
            response_description="Successful Response")
async def get_location_stats(
        db: DatabaseDep,
        period: PeriodDep,
        level: LevelQuery = None,
        response_format: Literal["json", "geojson"] = Query(
            "json", alias="format", description="`geojson` returns a FeatureCollection for a choropleth map.",
        ),
):
    """
    Conversations started in the period (with distinct people) and all-time project participants
    per location, most active first; only locations with data. Admin only. \\
    Conversations and participants without a location are the separate `unknown` count. \\
    `?format=geojson`: a FeatureCollection (boundary, or centroid `Point`) with the counts in
    `properties`, and `period` and `unknown` as foreign members.
    """
    repo = StatsRepo(db)
    if response_format == "geojson":
        return await repo.locations_geojson(period, level=level)
    return await repo.locations(period, level=level)
