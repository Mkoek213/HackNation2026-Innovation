from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.config import settings


def register_security_middlewares(app: FastAPI) -> None:
    """
    Registration order matters -- Starlette wraps middleware so the *last*
    one added ends up outermost (runs first). ProxyHeadersMiddleware must be
    outermost so it rewrites scope["client"]/scope["scheme"] from
    X-Forwarded-For/-Proto *before* anything downstream reads them --
    notably the rate limiter's per-IP key (app.middlewares.limiter), which
    would otherwise see the proxy's IP for every single request behind
    AGH's proxy and effectively rate-limit nothing.
    """
    if settings.require_trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_domains)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_hosts,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", settings.csrf_header_name, "X-Admin-Token"],
    )

    if settings.behind_proxy:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.proxy_trusted_hosts)
