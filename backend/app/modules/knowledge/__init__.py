"""Public integration entry for the knowledge module.

Other modules use only the names below. ``get_knowledge_service()`` builds the Qdrant-backed
service lazily and raises ``KnowledgeUnavailable`` when it is not configured or reachable.
"""

from .errors import InnovationNotFound, KnowledgeUnavailable
from .router import router
from .schemas import Evidence, InnovationCard, InnovationMeta, RetrievedInnovation
from .service import KnowledgeService, get_knowledge_service, warm_up
from .taxonomy import CATEGORY_CRITERIA, CATEGORY_LABELS, Category

__all__ = [
    "router",
    "Category",
    "CATEGORY_LABELS",
    "CATEGORY_CRITERIA",
    "Evidence",
    "InnovationCard",
    "InnovationMeta",
    "RetrievedInnovation",
    "KnowledgeService",
    "KnowledgeUnavailable",
    "InnovationNotFound",
    "get_knowledge_service",
    "warm_up",
]
