import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import settings


class UploadTooLarge(Exception):
    pass


class UploadSizeLimitMiddleware:
    """Bound request-body buffering before multipart parsing starts."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app
        # Include a small allowance for multipart boundaries and form fields.
        overhead = 2 * 1024 * 1024
        self.path_limits = {
            "/convert-file": settings.MAX_DOCUMENT_UPLOAD_BYTES + overhead,
            "/convert": settings.MAX_DOCUMENT_UPLOAD_BYTES + overhead,
            "/media/process": settings.MAX_VIDEO_UPLOAD_BYTES + overhead,
            "/video/process": settings.MAX_VIDEO_UPLOAD_BYTES + overhead,
            "/video/jobs": settings.MAX_VIDEO_UPLOAD_BYTES + overhead,
            "/image/process": settings.MAX_IMAGE_UPLOAD_BYTES + overhead,
        }

    def _limit_for_path(self, path: str) -> int | None:
        for suffix, limit in self.path_limits.items():
            if path == suffix or path.endswith(suffix):
                return limit
        return None

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Awaitable[dict[str, Any]]], send: Callable[..., Awaitable[None]]) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self._limit_for_path(scope.get("path", ""))
        if limit is None:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = -1
            if declared_length > limit:
                await self._send_too_large(send, limit)
                return

        received = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise UploadTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except UploadTooLarge:
            await self._send_too_large(send, limit)

    @staticmethod
    async def _send_too_large(send: Callable[..., Awaitable[None]], limit: int) -> None:
        body = json.dumps(
            {
                "detail": "Request body vượt quá giới hạn dung lượng cho phép.",
                "max_request_bytes": limit,
            }
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
