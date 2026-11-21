from fastapi import APIRouter, Request, Response, status

from app.config import settings
from app.dependencies import DatabaseDep
from app.docs import Tags
from app.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.middlewares.limiter import limiter
from app.models import User
from app.repos.user_repo import UserRepo
from app.schemas.auth import LoginRequest, LoginResponse, LogoutResponse
from app.schemas.default import CONFLICT, NOT_FOUND, UNAUTHORIZED
from app.schemas.user import UserCreate, UserModel, UserRegister
from app.utils.auth import (CurrentUserDep, clear_auth_cookies, create_access_token, create_csrf_token,
                            is_valid_csrf_token, set_auth_cookies, verify_password)

router = APIRouter(
    prefix="/auth",
    tags=[Tags.Authorization],
    responses={},
)


def _check_auth_origin(request: Request) -> None:
    # Non-browser clients omit Origin. Browsers must use the configured frontend.
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in {settings.frontend_base_url.rstrip("/"), *settings.allowed_hosts}:
        raise ForbiddenError(msg="Untrusted authentication origin.")


def _issue_login(response: Response, user: User) -> LoginResponse:
    token = create_access_token(user.id, user.username, user.role)

    access_token = None
    token_type = None
    if settings.auth_token_location in ("bearer", "both"):
        access_token, token_type = token, "bearer"
    if settings.auth_token_location in ("cookie", "both"):
        set_auth_cookies(response, token)

    return LoginResponse(detail="Logged in.", access_token=access_token, token_type=token_type)


@router.post("/login",
             dependencies=None,
             response_model=LoginResponse,
             responses={status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED},
             status_code=status.HTTP_200_OK,
             summary="Login")
@limiter.limit(settings.login_rate_limit)
async def login(
        request: Request,
        response: Response,
        credentials: LoginRequest,
        db: DatabaseDep,
):
    """
    Verifies username and password, otherwise raises 401 Unauthorized. \\
    Issues a JWT access token per AUTH_TOKEN_LOCATION: set as an HttpOnly cookie, returned in the
    response body, or both. Cookie mode also issues a separate, JS-readable CSRF cookie when
    USE_CSRF_PROTECTION is on.
    """
    _check_auth_origin(request)
    user = await UserRepo(db).get_by_username(credentials.username)
    password_hash = user.hashed_password if user is not None else None
    if user is None or not verify_password(credentials.password, password_hash):
        raise UnauthorizedError(msg="Invalid username or password.", loc=("body", "username"))

    return _issue_login(response, user)


@router.post("/register",
             dependencies=None,
             response_model=UserModel,
             responses={status.HTTP_409_CONFLICT: CONFLICT},
             status_code=status.HTTP_201_CREATED,
             summary="Register")
@limiter.limit(settings.register_rate_limit)
async def register(
        request: Request,
        response: Response,
        data: UserRegister,
        db: DatabaseDep,
):
    """
    Creates an account from username, email, password and an optional `role` (default `user`). \\
    Demo only: anyone can register an `admin` account. Any other extra field raises 422. \\
    Raises 409 Conflict when the username or email is already taken. Does not log in --
    call /auth/login afterwards.
    """
    _check_auth_origin(request)
    return await UserRepo(db).register(data)


@router.post("/logout",
             dependencies=None,
             response_model=LogoutResponse,
             status_code=status.HTTP_200_OK,
             summary="Logout")
async def logout(request: Request, response: Response):
    """
    Clears the auth and CSRF cookies (no-op if cookie mode isn't used). \\
    Bearer tokens are stateless and cannot be invalidated server-side -- a bearer client must
    discard the token itself.
    """
    _check_auth_origin(request)
    clear_auth_cookies(response)
    return LogoutResponse(detail="Logged out.")


@router.post("/debug-login",
             dependencies=None,
             response_model=LoginResponse,
             responses={status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED, status.HTTP_404_NOT_FOUND: NOT_FOUND},
             status_code=status.HTTP_200_OK,
             summary="Debug login",
             include_in_schema=settings.debug)
async def debug_login(response: Response, credentials: LoginRequest, db: DatabaseDep):
    """
    DEBUG ONLY -- 404s unless DEBUG=true. \\
    Logs in as the given username, creating the user on the fly (with the given password and the
    "user" role) if it doesn't exist yet -- no need to run scripts/create_user.py during local development. \\
    If the user already exists, behaves exactly like /auth/login: wrong password still 401s, only
    a nonexistent username gets auto-created.
    """
    if not settings.debug:
        raise NotFoundError(resource="Route", key="/auth/debug-login")

    repo = UserRepo(db)
    user = await repo.get_by_username(credentials.username)
    if user is None:
        user = await repo.create_user(UserCreate(username=credentials.username, password=credentials.password))
    elif not verify_password(credentials.password, user.hashed_password):
        raise UnauthorizedError(msg="Invalid username or password.", loc=("body", "username"))

    return _issue_login(response, user)


@router.get("/session")
async def session(request: Request, response: Response, user: CurrentUserDep):
    """Verify the session and refresh expired CSRF tokens without extending the login."""
    if settings.auth_token_location == "bearer":
        raise UnauthorizedError(msg="Workspace requires cookie authentication.")
    if settings.use_csrf_protection and not is_valid_csrf_token(request.cookies.get(settings.csrf_cookie_name, "")):
        response.set_cookie(settings.csrf_cookie_name, create_csrf_token(),
                            max_age=settings.csrf_token_expire_minutes * 60,
                            secure=settings.auth_cookie_secure, samesite=settings.auth_cookie_samesite,
                            domain=settings.auth_cookie_domain, path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"user": UserModel.model_validate(user), "csrf_cookie": settings.csrf_cookie_name,
            "csrf_header": settings.csrf_header_name}
