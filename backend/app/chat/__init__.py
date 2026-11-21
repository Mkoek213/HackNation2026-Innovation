"""Public chat integration contracts; no routes or infrastructure start on import."""

from .ownership import OwnerResolver, ResolvedOwner
from .schemas import (
    Artifact, ArtifactList, ArtifactPatch, ChatRequest, ChatResponse,
    Conversation, ConversationCreated, ConversationList, ErrorResponse,
    InnovationMatch, Message, MessageList, PaginationQuery, SourceMetadata, StreamEvent,
    parse_event, serialize_event,
)
from .settings import ChatSettings, load_chat_settings

__all__ = [
    "Artifact", "ArtifactList", "ArtifactPatch", "ChatRequest", "ChatResponse",
    "ChatSettings", "Conversation", "ConversationCreated", "ConversationList",
    "ErrorResponse", "InnovationMatch", "Message", "MessageList", "OwnerResolver",
    "PaginationQuery", "ResolvedOwner", "SourceMetadata", "StreamEvent", "load_chat_settings",
    "parse_event", "serialize_event",
]
