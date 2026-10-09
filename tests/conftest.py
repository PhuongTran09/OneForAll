import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app

# In-memory database storage for Supabase tests
_fake_db: dict[str, list[dict[str, Any]]] = {
    "profiles": [],
    "jobs": [],
}
_fake_storage: dict[str, bytes] = {}

TEST_JWT_SECRET = "test-secret-key-12345678901234567890"
settings.SUPABASE_JWT_SECRET = TEST_JWT_SECRET


def create_test_supabase_token(
    user_id: str | None = None,
    email: str = "test@example.com",
    username: str = "testuser",
    full_name: str = "Test User",
    is_superuser: bool = False,
) -> str:
    """Generates a valid Supabase JWT for testing."""
    uid = user_id or str(uuid4())
    payload = {
        "sub": uid,
        "aud": "authenticated",
        "role": "authenticated",
        "email": email,
        "user_metadata": {
            "username": username,
            "full_name": full_name,
        },
        "app_metadata": {
            "is_superuser": is_superuser,
            "provider": "email",
        },
        "exp": int(datetime.now(UTC).timestamp()) + 3600,
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


class MockResponse:
    def __init__(self, data: Any):
        self.data = data


class MockTableQuery:
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.action = "select"
        self.insert_data: Any = None
        self.update_data: dict[str, Any] | None = None
        self.filters: list[tuple[str, str, Any]] = []  # (op, col, val)
        self.range_val: tuple[int, int] | None = None

    def select(self, fields: str = "*"):
        self.action = "select"
        return self

    def insert(self, data: Any):
        self.action = "insert"
        self.insert_data = data
        return self

    def update(self, data: dict[str, Any]):
        self.action = "update"
        self.update_data = data
        return self

    def delete(self):
        self.action = "delete"
        return self

    def eq(self, col: str, val: Any):
        self.filters.append(("eq", col, val))
        return self

    def lte(self, col: str, val: Any):
        self.filters.append(("lte", col, val))
        return self

    def range(self, start: int, end: int):
        self.range_val = (start, end)
        return self

    def _matches_filters(self, row: dict[str, Any]) -> bool:
        for op, col, val in self.filters:
            row_val = row.get(col)
            if op == "eq":
                if str(row_val) != str(val):
                    return False
            elif op == "lte" and (row_val is None or str(row_val) > str(val)):
                return False
        return True

    async def execute(self) -> MockResponse:
        table_rows = _fake_db.setdefault(self.table_name, [])

        if self.action == "insert":
            items = (
                self.insert_data
                if isinstance(self.insert_data, list)
                else [self.insert_data]
            )
            inserted = []
            for item in items:
                row = dict(item)
                table_rows.append(row)
                inserted.append(row)
            return MockResponse(inserted)

        if self.action == "update":
            updated = []
            for row in table_rows:
                if self._matches_filters(row):
                    row.update(self.update_data or {})
                    updated.append(dict(row))
            return MockResponse(updated)

        if self.action == "delete":
            to_keep = [r for r in table_rows if not self._matches_filters(r)]
            _fake_db[self.table_name] = to_keep
            return MockResponse([])

        # Default select
        matched = [dict(r) for r in table_rows if self._matches_filters(r)]
        if self.range_val:
            s, e = self.range_val
            matched = matched[s : e + 1]
        return MockResponse(matched)


class MockAuth:
    async def get_user(self, token: str):
        try:
            payload = jwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"], options={"verify_aud": False})
            class MockSupabaseUser:
                id = payload.get("sub")
                email = payload.get("email")
                user_metadata = payload.get("user_metadata", {})
                app_metadata = payload.get("app_metadata", {})
            class UserResp:
                user = MockSupabaseUser()
            return UserResp()
        except Exception:  # noqa: BLE001
            return None


class MockAsyncSupabaseClient:
    def __init__(self):
        self.auth = MockAuth()

    def table(self, table_name: str) -> MockTableQuery:
        return MockTableQuery(table_name)


_mock_client_instance = MockAsyncSupabaseClient()


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def mock_external_services(monkeypatch):
    _fake_storage.clear()
    _fake_db["profiles"] = []
    _fake_db["jobs"] = []

    def fake_upload(*, data, key, **kwargs):
        _fake_storage[key] = data
        return key

    def fake_upload_file(*, local_path, key, **kwargs):
        from pathlib import Path

        _fake_storage[key] = Path(local_path).read_bytes()
        return key

    def fake_upload_fileobj(*, fileobj, key, **kwargs):
        _fake_storage[key] = fileobj.read()
        return key

    def fake_download(*, key, **kwargs):
        if key in _fake_storage:
            return _fake_storage[key]
        return b"fake-file-content"

    def fake_download_to_file(*, key, local_path, **kwargs):
        from pathlib import Path

        dest = Path(local_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = _fake_storage.get(key, b"fake-file-content")
        dest.write_bytes(content)
        return dest

    def fake_download_stream(*, key, **kwargs):
        yield fake_download(key=key)

    def fake_delete(*, key, **kwargs):
        _fake_storage.pop(key, None)
        return True

    monkeypatch.setattr(
        "app.services.task_queue_service.task_queue_service.enqueue_job",
        lambda **kwargs: "mocked-task-id",
    )
    monkeypatch.setattr(
        "app.services.storage_service.storage_service.upload_bytes",
        fake_upload,
    )
    monkeypatch.setattr(
        "app.services.storage_service.storage_service.upload_file",
        fake_upload_file,
    )
    monkeypatch.setattr(
        "app.services.storage_service.storage_service.upload_fileobj",
        fake_upload_fileobj,
    )
    monkeypatch.setattr(
        "app.services.storage_service.storage_service.download_bytes",
        fake_download,
    )
    monkeypatch.setattr(
        "app.services.storage_service.storage_service.download_to_file",
        fake_download_to_file,
    )
    monkeypatch.setattr(
        "app.services.storage_service.storage_service.download_stream",
        fake_download_stream,
    )
    monkeypatch.setattr(
        "app.services.storage_service.storage_service.delete_file",
        fake_delete,
    )

    # Supabase Client mocks
    import app.core.supabase as supabase_module

    supabase_module._async_client = _mock_client_instance
    supabase_module._sync_client = _mock_client_instance

    async def get_mock_async_client():
        return _mock_client_instance

    def get_mock_sync_client():
        return _mock_client_instance

    monkeypatch.setattr(
        "app.core.supabase.get_async_supabase_client",
        get_mock_async_client,
    )
    monkeypatch.setattr(
        "app.core.supabase.get_sync_supabase_client",
        get_mock_sync_client,
    )


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
