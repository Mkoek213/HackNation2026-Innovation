from fastapi import APIRouter
from starlette import status

from . import (
    auth,
    chat,
    contact,
    conversations,
    operator,
    ideas,
    internal,
    locations,
    matters,
    projects,
    stats,
    tags,
    tester,
    users,
    visits,
)
from ..schemas.default import UNAUTHORIZED, FORBIDDEN

router = APIRouter(
    responses={
       status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED,
       status.HTTP_403_FORBIDDEN: FORBIDDEN,
    },
)
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(tags.router)
router.include_router(locations.router)
router.include_router(projects.router)
router.include_router(projects.matches_router)
router.include_router(conversations.router)
router.include_router(tester.router)
router.include_router(ideas.router)
router.include_router(matters.router)
router.include_router(operator.router)
router.include_router(contact.router)
router.include_router(visits.router)
router.include_router(stats.router)
router.include_router(internal.router)

router.include_router(chat.router)

from . import workspace
router.include_router(workspace.router)
