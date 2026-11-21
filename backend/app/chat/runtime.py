"""Runtime assembly, independently importable by isolated tests."""
from .provider import GeminiProvider, ProviderUnavailable
from .settings import load_chat_settings
from .store import ChatStore, CookieOwnerResolver
from .service import ChatService


async def start_chat(app, sessions):
    settings = load_chat_settings()
    store = ChatStore(sessions)
    await store.recover()
    app.state.chat_store = store
    app.state.chat_owners = CookieOwnerResolver(sessions, settings)
    try:
        provider = GeminiProvider(settings)
    except ProviderUnavailable:
        app.state.chat_service = None
    else:
        app.state.chat_service = ChatService(store, provider, settings)
