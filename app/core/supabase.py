"""Supabase Client Initialization and Management.

Provides both async (FastAPI / Celery persistent worker loop) and sync Supabase clients
for database (PostgREST) and Auth interactions.
"""

import asyncio

from app.core.config import settings
from app.utils.logger import logger
from supabase import AsyncClient, Client, create_async_client, create_client

_async_client: AsyncClient | None = None
_async_client_loop: asyncio.AbstractEventLoop | None = None
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
    """Returns singleton AsyncClient for async FastAPI handlers and async worker tasks.

    Ensures the client is bound to the currently running event loop and recreates
    it if the previous event loop was closed or has changed.
    """
    global _async_client, _async_client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _async_client is not None:
        # If client was injected without a recorded loop (e.g. test mock), preserve it
        if _async_client_loop is None:
            return _async_client

        # If current loop matches the client's loop and is open, reuse client
        if _async_client_loop is current_loop and not current_loop.is_closed():
            return _async_client

        # Client was bound to a closed or different event loop - reset it
        logger.info(
            "Supabase async client bound to closed or different loop (%s vs %s). Reinitializing.",
            _async_client_loop,
            current_loop,
        )
        _async_client = None
        _async_client_loop = None

    url = get_supabase_url()
    key = get_supabase_key()
    try:
        _async_client = await create_async_client(url, key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not initialize async Supabase client: %s", exc)
        _async_client = await create_async_client("https://placeholder.supabase.co", "placeholder-key")

    _async_client_loop = current_loop
    return _async_client


async def close_async_supabase_client() -> None:
    """Gracefully close the async Supabase client and its underlying HTTP connection pool."""
    global _async_client, _async_client_loop
    if _async_client is not None:
        try:
            if hasattr(_async_client, "postgrest") and hasattr(_async_client.postgrest, "aclose"):
                await _async_client.postgrest.aclose()
            if hasattr(_async_client, "auth") and hasattr(_async_client.auth, "close"):
                if asyncio.iscoroutinefunction(_async_client.auth.close):
                    await _async_client.auth.close()
                else:
                    _async_client.auth.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error closing async Supabase client: %s", exc)
        finally:
            _async_client = None
            _async_client_loop = None


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
    global _async_client, _sync_client, _async_client_loop
    _async_client = None
    _sync_client = None
    _async_client_loop = None
