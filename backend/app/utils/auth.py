"""
All authorization logic in one place: password hashing, JWT access tokens,
CSRF tokens, the auth/CSRF cookie helpers, the get_current_user
dependency, the anonymous visitor identity (Actor / VisitorDep), and the
assert_owner check.
"""
import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, Request, Response

from app.config import settings
from app.dependencies import DatabaseDep
from app.exceptions import ForbiddenError, UnauthorizedError
from app.models import User

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_CSRF_PURPOSE = "csrf"


# ============ password hashing ============

_hasher = PasswordHasher()

# Computed once so verify_password() takes roughly the same time whether the
# username exists or not -- otherwise a missing user short-circuits before
# any hashing happens, leaking account existence through response timing.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing-safety")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    try:
        return _hasher.verify(hashed or _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ============ JWT access tokens ============

def create_access_token(user_id: int, username: str, role: str | None = None) -> str:
    """The role claim is informational for the frontend -- authorization
    always re-reads the role from the database (see get_current_user)."""
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """:raises UnauthorizedError: token is missing, expired, or invalid."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError(msg="Session expired, please log in again.", loc=("header", "authorization"))
    except jwt.InvalidTokenError:
        raise UnauthorizedError(msg="Invalid authentication token.", loc=("header", "authorization"))


# ============ CSRF tokens ============

def create_csrf_token() -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "purpose": _CSRF_PURPOSE,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.csrf_token_expire_minutes),
    }
    return jwt.encode(payload, settings.csrf_secret, algorithm=settings.jwt_algorithm)


def is_valid_csrf_token(token: str) -> bool:
    """Signature + expiry check only. The double-submit comparison (does this
    token match the one in the cookie) is the caller's job."""
    try:
        payload = jwt.decode(token, settings.csrf_secret, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError:
        return False
    return payload.get("purpose") == _CSRF_PURPOSE


# ============ auth / CSRF cookies ============

def set_auth_cookies(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.jwt_cookie_name,
        value=token,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        domain=settings.auth_cookie_domain,
        path="/",
    )
    if settings.use_csrf_protection:
        response.set_cookie(
            key=settings.csrf_cookie_name,
            value=create_csrf_token(),
            max_age=settings.csrf_token_expire_minutes * 60,
            httponly=False,  # must be JS-readable: the frontend echoes it back in a header
            secure=settings.auth_cookie_secure,
            samesite=settings.auth_cookie_samesite,
            domain=settings.auth_cookie_domain,
            path="/",
        )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(settings.jwt_cookie_name, domain=settings.auth_cookie_domain, path="/")
    response.delete_cookie(settings.csrf_cookie_name, domain=settings.auth_cookie_domain, path="/")


# ============ get_current_user dependency ============

def _extract_token(request: Request) -> tuple[str | None, bool]:
    """Returns (token, from_cookie). Bearer header takes priority over the
    cookie when auth_token_location == "both" and both are present."""
    if settings.auth_token_location in ("bearer", "both"):
        header = request.headers.get("Authorization")
        if header:
            scheme, _, value = header.partition(" ")
            if scheme.lower() == "bearer" and value:
                return value, False
    if settings.auth_token_location in ("cookie", "both"):
        value = request.cookies.get(settings.jwt_cookie_name)
        if value:
            return value, True
    return None, False


def _verify_csrf(request: Request) -> None:
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get(settings.csrf_header_name)
    if (
        not cookie_token
        or not header_token
        or cookie_token != header_token
        or not is_valid_csrf_token(cookie_token)
    ):
        raise ForbiddenError(
            msg="Missing or invalid CSRF token.",
            loc=("header", settings.csrf_header_name),
        )


async def get_current_user(request: Request, db: DatabaseDep) -> User:
    """:raises UnauthorizedError: no/expired/invalid token, or the user no longer exists.
    :raises ForbiddenError: cookie-derived auth on an unsafe method without a valid CSRF token."""
    # Local import: UserRepo imports hash_password from this module, so a
    # module-level import here would be circular.
    from app.repos.user_repo import UserRepo

    token, from_cookie = _extract_token(request)
    if token is None:
        raise UnauthorizedError(msg="Not authenticated.", loc=("header", "authorization"))

    payload = decode_access_token(token)

    if from_cookie and settings.use_csrf_protection and request.method in _UNSAFE_METHODS:
        _verify_csrf(request)

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise UnauthorizedError(msg="Invalid authentication token.", loc=("header", "authorization"))

    user = await UserRepo(db).get_one(id=user_id, quiet=True)
    if user is None:
        raise UnauthorizedError(msg="User no longer exists.", loc=("header", "authorization"))
    return user


async def get_current_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    """:raises UnauthorizedError: see get_current_user.
    :raises ForbiddenError: the logged-in user is not an admin."""
    if not user.is_admin:
        raise ForbiddenError(msg="Admin role required.", loc=("header", "authorization"))
    return user


async def get_optional_user(request: Request, db: DatabaseDep) -> User | None:
    """Like get_current_user, but returns None instead of raising 401 when there is
    no token, or the token is expired/invalid, or its user no longer exists -- so
    public endpoints keep working for a visitor with a stale session.
    :raises ForbiddenError: a valid cookie session on an unsafe method without a
        valid CSRF token (acting as that user still requires CSRF)."""
    try:
        return await get_current_user(request, db)
    except UnauthorizedError:
        return None


CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentAdminDep = Annotated[User, Depends(get_current_admin)]
OptionalUserDep = Annotated[User | None, Depends(get_optional_user)]


# ============ anonymous visitor identity ============

@dataclass(frozen=True)
class Actor:
    """Who is making a request: the logged-in user (or None) and the anonymous
    visitor id from the visitor cookie. visitor_id is always present, also for
    logged-in users, so statistics can follow a person across login."""
    user: User | None
    visitor_id: uuid.UUID

    @property
    def is_admin(self) -> bool:
        return self.user is not None and self.user.is_admin


def _parse_visitor_id(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def set_visitor_cookie(response: Response, visitor_id: uuid.UUID) -> None:
    response.set_cookie(
        key=settings.visitor_cookie_name,
        value=str(visitor_id),
        max_age=settings.visitor_cookie_max_age_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        domain=settings.auth_cookie_domain,
        path="/",
    )


async def get_actor(request: Request, response: Response, user: OptionalUserDep) -> Actor:
    """
    Dependency for public endpoints (``VisitorDep``).

    Reads the ``visitor_id`` cookie (a UUID). When it is missing or malformed, a new
    UUID is generated and set as an HttpOnly, SameSite=Lax cookie valid for
    ``visitor_cookie_max_age_days`` (secure/domain follow the auth cookie settings).
    An existing valid cookie is reused and not re-sent.

    The cookie is attached to the dependency-injected ``Response``; FastAPI merges it
    into the route's response only when the route returns data, not a ``Response``
    object -- such routes must call :func:`set_visitor_cookie` themselves.

    :raises ForbiddenError: see get_optional_user (CSRF of a logged-in cookie session).
    """
    visitor_id = _parse_visitor_id(request.cookies.get(settings.visitor_cookie_name))
    if visitor_id is None:
        visitor_id = uuid.uuid4()
        set_visitor_cookie(response, visitor_id)
    return Actor(user=user, visitor_id=visitor_id)


VisitorDep = Annotated[Actor, Depends(get_actor)]


def assert_owner(actor: Actor, user_id: int | None, visitor_id: uuid.UUID | None, *, loc: tuple = ()) -> None:
    """
    Checks that ``actor`` owns a resource whose owner columns are ``user_id`` / ``visitor_id``.

    - An admin always passes.
    - A resource with a ``user_id`` belongs only to that logged-in user.
    - A resource without a ``user_id`` (anonymous) belongs to the visitor whose
      cookie matches ``visitor_id``, whether or not they have logged in since.

    :raises ForbiddenError: the actor is not the owner.
    """
    if actor.is_admin:
        return
    if user_id is not None:
        if actor.user is not None and actor.user.id == user_id:
            return
    elif visitor_id is not None and actor.visitor_id == visitor_id:
        return
    raise ForbiddenError(msg="You do not have access to this resource.", loc=loc)
