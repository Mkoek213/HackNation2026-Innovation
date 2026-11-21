import os
from typing import Literal

from pydantic.v1 import BaseSettings, Field


class Settings(BaseSettings):
    debug: bool = False
    reset_db: bool = False
    database_url: str = f'sqlite+aiosqlite:///{os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test.db")}'
    # Bootstrap admin, created on startup if this username does not exist yet.
    admin_username: str | None = None
    admin_password: str | None = None

    jwt_secret: str = 'CHANGE_IN_PRODUCTION'
    jwt_algorithm: str = 'HS256'
    jwt_access_token_expire_minutes: int = 180
    jwt_cookie_name: str = 'Authorization'

    # Where the access token is accepted/issued:
    # - "bearer": only the `Authorization: Bearer <token>` header. No cookie is set, no CSRF needed.
    # - "cookie": only the HttpOnly cookie named jwt_cookie_name. Needs CSRF protection (see below).
    # - "both":   accepts either, and login sets the cookie *and* returns the token in the body.
    auth_token_location: Literal["bearer", "cookie", "both"] = "cookie"

    # Attributes for both the auth cookie and the CSRF cookie.
    auth_cookie_secure: bool = True
    auth_cookie_samesite: Literal["strict", "lax", "none"] = "lax"
    # None = host-only cookie. Set to e.g. ".example.com"
    # to share the cookie between the frontend and api.* subdomains.
    auth_cookie_domain: str | None = None

    frontend_base_url: str = 'http://localhost:3000'
    # Optional verified operator (PCI) recipient; users can edit it before opening their mail client.
    # With SMTP configured, contact form messages are also e-mailed here.
    radar_contact_email: str = ""

    # Optional SMTP for server-side handoff delivery with a PDF attachment and contact form messages.
    # When unset, the UI falls back to download PDF + mailto.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: int = Field(default=20, ge=1, le=30)

    backend_base_url: str = 'http://localhost:8000'

    # CORS origins
    allowed_hosts: list[str] = [
        "http://localhost:3000",
    ]

    # Host header whitelist, only used when require_trusted_hosts is on
    allowed_domains: list[str] = [
        "localhost",
        "127.0.0.1",
    ]

    proxy_trusted_hosts: list[str] = [
        "172.16.0.0/12"
    ]

    redirect_https: bool = False
    require_trusted_hosts: bool = True
    behind_proxy: bool = True

    # Only relevant when auth_token_location is "cookie" or "both" -- bearer
    # tokens aren't sent automatically by the browser, so they aren't
    # CSRF-able in the first place.
    use_csrf_protection: bool = True
    csrf_secret: str = 'CHANGE_IN_PRODUCTION'
    csrf_cookie_name: str = 'csrf_token'
    csrf_header_name: str = 'X-CSRF-Token'
    csrf_token_expire_minutes: int = 15

    # Anonymous visitor identity (see utils.auth.get_actor). Uses the
    # auth cookie's secure/domain attributes; always HttpOnly + SameSite=Lax.
    visitor_cookie_name: str = 'visitor_id'
    visitor_cookie_max_age_days: int = 365

    # Uploaded files (project PDFs) live in a private S3 bucket, see app/services/files.py.
    # The same S3_* variables configure the knowledge module's document storage.
    s3_endpoint_url: str | None = None
    s3_bucket: str = "radar-documents"
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    max_upload_bytes: int = 20 * 1024 * 1024

    # Vector store + chat engine implementation, see app/services/rag.py and chat_engine.py.
    # "demo" is a deterministic keyword-matching stand-in without external calls.
    ai_backend: Literal["demo"] = "demo"

    # Provisional topic-label gates; calibrate against reviewed Polish examples.
    tagging_min_probability: float = Field(default=0.8, gt=0.5, le=1)
    tagging_min_confidence: float = Field(default=0.6, ge=0, le=1)
    # Workspace conversations are tagged once idle for this long, outside the chat request path.
    tagging_idle_seconds: int = Field(default=300, ge=0)
    # Period of the in-process tagging sweep; 0 disables it. Cloud Run sets 0 and calls
    # POST /internal/tagging/sweep from Cloud Scheduler instead (see docs/DEPLOYMENT.md).
    tagging_sweep_seconds: int = Field(default=60, ge=0)

    rate_limit: str = "120/minute"
    # Chat answers (POST /conversations and its messages), per client IP.
    chat_rate_limit: str = "30/minute"
    login_rate_limit: str = "5/minute"
    register_rate_limit: str = "5/minute"
    # Contact form messages (POST /contact), per client IP.
    contact_rate_limit: str = "5/minute"

    class Config:
        # Runtime environment is supplied by Compose or the development command.
        env_file = None


settings = Settings()
