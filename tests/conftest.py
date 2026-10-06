import asyncio
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app

# In-memory SQLite for testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine_test = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(
    bind=engine_test,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


_fake_storage: dict[str, bytes] = {}


@pytest.fixture(autouse=True)
def mock_external_services(monkeypatch):
    _fake_storage.clear()

    def fake_upload(*, data, key, **kwargs):
        _fake_storage[key] = data
        return key

    def fake_download(*, key, **kwargs):
        if key in _fake_storage:
            return _fake_storage[key]
        return b"fake-file-content"

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
        "app.services.storage_service.storage_service.download_bytes",
        fake_download,
    )
    monkeypatch.setattr(
        "app.services.storage_service.storage_service.delete_file",
        fake_delete,
    )
    monkeypatch.setattr(
        "app.worker.tasks.convert.AsyncSessionLocal",
        TestingSessionLocal,
    )
    monkeypatch.setattr(
        "app.worker.tasks.cleanup.AsyncSessionLocal",
        TestingSessionLocal,
    )


@pytest.fixture(autouse=True)
async def prepare_database():
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
