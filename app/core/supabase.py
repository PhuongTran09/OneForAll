"""Supabase Client Initialization and Management.

Provides both async (FastAPI) and sync (Celery workers) Supabase clients
for database (PostgREST) and Auth interactions.
"""

from app.core.config import settings
from app.utils.logger import logger
from supabase import AsyncClient, Client, create_async_client, create_client

_async_client: AsyncClient | None = None
_sync_client: Client | None = None


def get_supabase_url() -> str:
    return settings.SUPABASE_URL or "https://placeholder.supabase.co"


def get_supabase_key() -> str:
    # Use SERVICE_ROLE_KEY for backend/worker operations to bypass RLS,
    # or fallback to SUPABASE_KEY (anon key)
    return (
        settings.SUPABASE_SERVICE_ROLE_KEY
        or settings.SUPABASE_KEY
        or "placeholder-key"
    )


async def get_async_supabase_client() -> AsyncClient:
    """Returns singleton AsyncClient for async FastAPI handlers and async worker tasks."""
    global _async_client
    if _async_client is not None:
        return _async_client

    url = get_supabase_url()
    key = get_supabase_key()
    try:
        _async_client = await create_async_client(url, key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not initialize async Supabase client: %s", exc)
        _async_client = await create_async_client("https://placeholder.supabase.co", "placeholder-key")

    return _async_client


def get_sync_supabase_client() -> Client:
    """Returns singleton sync Client for blocking Celery tasks if needed."""
    global _sync_client
    if _sync_client is not None:
        return _sync_client

    url = get_supabase_url()
    key = get_supabase_key()
    try:
        _sync_client = create_client(url, key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not initialize sync Supabase client: %s", exc)
        _sync_client = create_client("https://placeholder.supabase.co", "placeholder-key")

    return _sync_client


def reset_supabase_clients() -> None:
    """Reset clients (primarily for tests/monkeypatching)."""
    global _async_client, _sync_client
    _async_client = None
    _sync_client = None
