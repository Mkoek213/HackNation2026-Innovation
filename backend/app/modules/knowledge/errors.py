class KnowledgeError(Exception):
    """Base error of the knowledge module; the router maps subclasses to HTTP statuses."""


class KnowledgeUnavailable(KnowledgeError):
    """Qdrant is not configured or not reachable."""


class InnovationNotFound(KnowledgeError):
    def __init__(self, innovation_id: str):
        super().__init__(f"Innovation {innovation_id!r} was not found.")
        self.innovation_id = innovation_id
