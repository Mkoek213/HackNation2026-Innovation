"""Replaceable server-side owner boundary. CookieOwnerResolver implements anonymous browser ownership."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from starlette.requests import Request
from starlette.responses import Response


@dataclass(frozen=True)
class ResolvedOwner:
    """Trusted principal obtained from a verified cookie or future account resolver."""

    id: UUID


class OwnerResolver(Protocol):
    async def resolve(
        self, request: Request, response: Response, *, allow_create: bool = False,
    ) -> ResolvedOwner:
        """Resolve ownership server-side, issuing a cookie only for explicit bootstrap.

        Missing/invalid tokens fail on reads. Never trust a body/header/query owner ID.
        Services scope every conversation, turn and artifact operation to this principal;
        unowned IDs produce 404 before content or revision metadata is disclosed.
        """
        ...
