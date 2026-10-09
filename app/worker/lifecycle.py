"""Persistent event loop lifecycle management for Celery workers.

Provides a persistent asyncio event loop across the lifetime of a Celery worker,
preventing 'RuntimeError: Event loop is closed' on Windows (-P solo) and ensuring
the async Supabase client / httpx connection pool is retained and reused across tasks.
"""

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any

from celery.signals import (
    worker_init,
    worker_process_init,
    worker_process_shutdown,
    worker_shutdown,
)

from app.core.supabase import close_async_supabase_client, get_async_supabase_client
from app.utils.logger import logger


class WorkerLoopManager:
    """Manages a persistent asyncio event loop for Celery worker processes."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._ready_event = threading.Event()

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop

    @property
    def is_running(self) -> bool:
        return (
            self._loop is not None
            and not self._loop.is_closed()
            and self._loop.is_running()
        )

    def start(self) -> asyncio.AbstractEventLoop:
        """Start the persistent worker event loop if not already running."""
        with self._lock:
            if self.is_running:
                assert self._loop is not None
                return self._loop

            if self._loop is not None and not self._loop.is_closed():
                try:
                    self._loop.call_soon_threadsafe(self._loop.stop)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("[worker-lifecycle] Stopping previous loop: %s", exc)

            self._ready_event.clear()
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run_event_loop,
                name="celery-worker-event-loop",
                daemon=True,
            )
            self._thread.start()

            if not self._ready_event.wait(timeout=10.0):
                logger.error("[worker-lifecycle] Timeout waiting for worker event loop to start.")
                raise RuntimeError("Failed to start worker event loop within timeout.")

            logger.info("[worker-lifecycle] Persistent worker event loop started.")
            return self._loop

    def _run_event_loop(self) -> None:
        """Target function running inside the persistent loop thread."""
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._ready_event.set()
        try:
            self._loop.run_forever()
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
            except Exception as exc:  # noqa: BLE001
                logger.debug("[worker-lifecycle] Cancelling pending tasks: %s", exc)

    def run[T](self, coro: Coroutine[Any, Any, T], timeout: float | None = None) -> T:
        """Execute a coroutine in the persistent event loop and return its result."""
        if not self.is_running:
            self.start()

        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def stop(self) -> None:
        """Gracefully stop and close the persistent worker event loop."""
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                self._loop = None
                self._thread = None
                return

            logger.info("[worker-lifecycle] Stopping persistent worker event loop...")
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
                if self._thread is not None and self._thread.is_alive():
                    self._thread.join(timeout=5.0)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[worker-lifecycle] Error stopping loop: %s", exc)
            finally:
                try:
                    if not self._loop.is_closed():
                        self._loop.close()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[worker-lifecycle] Error closing loop: %s", exc)
                self._loop = None
                self._thread = None
                logger.info("[worker-lifecycle] Worker event loop stopped and closed.")


_worker_loop_manager = WorkerLoopManager()


def get_worker_loop_manager() -> WorkerLoopManager:
    return _worker_loop_manager


def run_in_worker_loop[T](coro: Coroutine[Any, Any, T], timeout: float | None = None) -> T:
    """Run any coroutine synchronously within the persistent worker event loop."""
    return _worker_loop_manager.run(coro, timeout=timeout)


@worker_process_init.connect
@worker_init.connect
def on_worker_init(**kwargs: Any) -> None:
    """Celery signal hook: initialize persistent loop and pre-warm async Supabase client."""
    logger.info("[worker-lifecycle] Celery worker initializing persistent event loop...")
    manager = get_worker_loop_manager()
    manager.start()

    try:
        manager.run(get_async_supabase_client())
        logger.info("[worker-lifecycle] Supabase async client initialized on persistent loop.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[worker-lifecycle] Could not pre-initialize Supabase client: %s", exc)


@worker_process_shutdown.connect
@worker_shutdown.connect
def on_worker_shutdown(**kwargs: Any) -> None:
    """Celery signal hook: gracefully close Supabase async client and stop loop."""
    logger.info("[worker-lifecycle] Celery worker shutting down persistent event loop...")
    manager = get_worker_loop_manager()
    if manager.is_running:
        try:
            manager.run(close_async_supabase_client())
            logger.info("[worker-lifecycle] Supabase async client closed.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[worker-lifecycle] Error during client shutdown: %s", exc)
        finally:
            manager.stop()
