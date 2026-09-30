import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_remove_bg_v1_invalid_file(client: AsyncClient):
    # Test uploading non-image file to /api/v1/remove-bg
    files = {"file": ("test.txt", b"plain text content", "text/plain")}
    response = await client.post("/api/v1/remove-bg", files=files)
    assert response.status_code == 400
    assert "Vui lòng tải lên file định dạng ảnh hợp lệ." in response.json()["detail"]


@pytest.mark.asyncio
async def test_remove_bg_root_invalid_file(client: AsyncClient):
    # Test uploading non-image file to /remove-bg (root alias)
    files = {"file": ("test.txt", b"plain text content", "text/plain")}
    response = await client.post("/remove-bg", files=files)
    assert response.status_code == 400
    assert "Vui lòng tải lên file định dạng ảnh hợp lệ." in response.json()["detail"]
