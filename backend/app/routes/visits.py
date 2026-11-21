from fastapi import APIRouter, status

from app.dependencies import DatabaseDep
from app.docs import Tags
from app.repos.stats_repo import VisitRepo
from app.schemas.stats import VisitCreate, VisitModel
from app.utils.auth import VisitorDep

router = APIRouter(
    prefix="/visits",
    tags=[Tags.Statistics],
    responses={},
)


@router.post("",
             dependencies=None,
             response_model=VisitModel,
             status_code=status.HTTP_201_CREATED,
             summary="Record page view",
             response_description="Successful Response")
async def record_visit(
        db: DatabaseDep,
        actor: VisitorDep,
        visit: VisitCreate,
):
    """
    Record a page view for the site usage statistics; the frontend calls it on each page view. Public. \\
    Sets the anonymous `visitor_id` cookie when missing and links the visit to the logged-in user, if any.
    Only the path is stored: a query string or fragment is dropped, and no IP address is kept. \\
    Rate limited by the default per-IP limit (`RATE_LIMIT`).
    """
    return await VisitRepo(db).record(visit, actor)
