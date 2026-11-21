"""Knowledge module configuration, read from the environment when the service is first built.

Nothing is read at import time, so the app starts without any of these variables.
"""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class KnowledgeSettings:
    # "https://<cluster>.cloud.qdrant.io:6333", "http://localhost:6333", ":memory:" or a directory path.
    qdrant_url: str | None
    qdrant_api_key: str | None
    # The managed cluster is shared by the team: use a per-environment collection name.
    qdrant_collection: str
    # Dense embeddings come from the Gemini API; the key is shared with the chat agent.
    gemini_api_key: str | None = field(repr=False)
    embedding_model: str
    embedding_dimensions: int
    retrieval_prefetch: int
    evidence_per_innovation: int
    # Shared secret for write operations (X-Admin-Token). Unset => writes are disabled.
    admin_token: str | None
    max_upload_mb: int
    s3_endpoint_url: str | None = None
    s3_bucket: str = "radar-documents"
    s3_region: str = "us-east-1"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def load_knowledge_settings() -> KnowledgeSettings:
    return KnowledgeSettings(
        qdrant_url=os.getenv("QDRANT_URL") or None,
        qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "radar_innovations"),
        gemini_api_key=(os.getenv("GEMINI_API_KEY") or "").strip() or None,
        embedding_model=os.getenv("EMBEDDING_MODEL", "gemini-embedding-2"),
        embedding_dimensions=_int("EMBEDDING_DIMENSIONS", 1536),
        retrieval_prefetch=_int("RETRIEVAL_PREFETCH", 40),
        evidence_per_innovation=_int("EVIDENCE_PER_INNOVATION", 3),
        admin_token=os.getenv("RADAR_ADMIN_TOKEN") or None,
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
        s3_bucket=os.getenv("S3_BUCKET", "radar-documents"),
        s3_region=os.getenv("S3_REGION", "us-east-1"),
        s3_access_key=os.getenv("S3_ACCESS_KEY_ID") or None,
        s3_secret_key=os.getenv("S3_SECRET_ACCESS_KEY") or None,
        max_upload_mb=_int("KNOWLEDGE_MAX_UPLOAD_MB", 100),
    )
