from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.config import settings


def rate_limit_key(request: Request) -> str:
    """
    User ip is the rate limit key.
    """
    return get_remote_address(request)


limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[settings.rate_limit],
    headers_enabled=True,
)


def register_rate_limiter(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
