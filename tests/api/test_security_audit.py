from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.url_validator import validate_safe_url
from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.repositories.user_repository import UserRepository
from app.services.payment_service import verify_payos_signature
from app.services.storage_service import storage_service
from app.utils.download_token import generate_download_token
from app.worker.processors.image import image_processor
from tests.conftest import TEST_JWT_SECRET, _fake_storage, create_test_supabase_token


# ===========================================================================
# 1. AUTHENTICATION & PRIVILEGE ESCALATION TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_jwt_verification_rejects_forged_signature(client: AsyncClient):
    """JWT signed with an unknown or incorrect secret must be rejected with 401."""
    fake_token = jwt.encode(
        {"sub": str(uuid4()), "exp": int(datetime.now(UTC).timestamp()) + 3600},
        "wrong-attacker-secret-key-123456789012",
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {fake_token}"}
    response = await client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 401
    assert "Invalid or expired Supabase JWT" in response.json()["detail"]


@pytest.mark.asyncio
async def test_jwt_verification_rejects_missing_secret(client: AsyncClient):
    """When SUPABASE_JWT_SECRET is empty, HS256 tokens must be rejected, not decoded without verification."""
    token = create_test_supabase_token()
    with patch.object(settings, "SUPABASE_JWT_SECRET", ""):
        headers = {"Authorization": f"Bearer {token}"}
        response = await client.get("/api/v1/users/me", headers=headers)
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_jwt_verification_rejects_expired_token(client: AsyncClient):
    """Expired tokens must be rejected with 401."""
    expired_token = jwt.encode(
        {"sub": str(uuid4()), "exp": int(datetime.now(UTC).timestamp()) - 3600},
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    response = await client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_privilege_escalation_prevented_on_profile_update(client: AsyncClient):
    """Regular users cannot set is_superuser or is_active via PATCH /users/me."""
    user_id = str(uuid4())
    token = create_test_supabase_token(user_id=user_id, is_superuser=False)
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt to send is_superuser=True
    response = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"is_superuser": True, "full_name": "Attacker"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_superuser"] is False
    assert data["full_name"] == "Attacker"

    # Verify directly in repository that the user is still not a superuser
    repo = UserRepository()
    db_user = await repo.get_by_id(user_id)
    assert db_user is not None
    assert db_user.is_superuser is False


# ===========================================================================
# 2. PUBLIC JOBS & DOWNLOAD TOKEN SECURITY
# ===========================================================================

@pytest.mark.asyncio
async def test_anonymous_job_creation_returns_token_and_hashes_in_db(client: AsyncClient):
    """Anonymous job creation returns plain token once; only token hash is stored in DB."""
    response = await client.post(
        "/api/v1/convert-file",
        data={"to": "svg"},
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\ntestdata", "image/png")},
    )
    assert response.status_code == 202
    res_data = response.json()
    job_id = res_data["job_id"]
    download_token = res_data.get("download_token")
    assert download_token is not None
    assert len(download_token) >= 32

    # Check database: plaintext token must NOT be stored
    repo = JobRepository()
    job = await repo.get(job_id)
    assert job is not None
    assert job.user_id == "anonymous"
    stored_metadata = job.job_metadata or {}
    assert "download_token" not in stored_metadata
    assert "download_token_hash" in stored_metadata
    assert stored_metadata["download_token_hash"] != download_token


@pytest.mark.asyncio
async def test_consumed_endpoint_requires_valid_token_for_public_job(client: AsyncClient):
    """POST /files/{job_id}/consumed requires valid ?token= for anonymous jobs, blocking IDOR."""
    token, token_hash = generate_download_token()
    repo = JobRepository()
    job = await repo.create(
        user_id="anonymous",
        type="convert",
        input_key=None,
        metadata={"download_token_hash": token_hash},
    )
    output_key = f"outputs/{job.id}/result.pdf"
    storage_service.upload_bytes(data=b"%PDF-1.4 Fake", key=output_key)
    await repo.mark_completed(job, output_key=output_key)

    # 1. Missing token -> 403
    res_no_token = await client.post(f"/api/v1/files/{job.id}/consumed")
    assert res_no_token.status_code == 403

    # 2. Invalid token -> 403
    res_bad_token = await client.post(f"/api/v1/files/{job.id}/consumed?token=invalid-secret-token")
    assert res_bad_token.status_code == 403

    # 3. Valid token -> 200 and cleans up
    res_ok = await client.post(f"/api/v1/files/{job.id}/consumed?token={token}")
    assert res_ok.status_code == 200
    assert await repo.get(job.id) is None


@pytest.mark.asyncio
async def test_private_job_cannot_be_downloaded_by_another_user(client: AsyncClient):
    """Private job belongs to User A; User B cannot download it even with valid JWT."""
    user_a = str(uuid4())
    user_b = str(uuid4())

    repo = JobRepository()
    job = await repo.create(
        user_id=user_a,
        type="convert",
        input_key="uploads/test.txt",
    )
    output_key = f"outputs/{job.id}/result.pdf"
    storage_service.upload_bytes(data=b"%PDF-1.4 Fake", key=output_key)
    await repo.mark_completed(job, output_key=output_key)

    token_b = create_test_supabase_token(user_id=user_b)
    headers_b = {"Authorization": f"Bearer {token_b}"}

    res = await client.get(f"/api/v1/files/{job.id}/download", headers=headers_b)
    assert res.status_code == 403


# ===========================================================================
# 3. SSRF & ARGUMENT INJECTION VALIDATION TESTS
# ===========================================================================

def test_url_validator_blocks_ssrf_and_argument_injections():
    """Verify validate_safe_url blocks dangerous internal addresses and CLI flags."""
    # Argument injection
    with pytest.raises(AppException):
        validate_safe_url("--exec id")

    with pytest.raises(AppException):
        validate_safe_url("-o output.txt")

    # Local file scheme
    with pytest.raises(AppException):
        validate_safe_url("file:///etc/passwd")

    # Loopback IP
    with pytest.raises(AppException):
        validate_safe_url("http://127.0.0.1:8000/test")

    with pytest.raises(AppException):
        validate_safe_url("http://localhost:6379")

    # Cloud metadata (AWS, GCP, Azure link-local)
    with pytest.raises(AppException):
        validate_safe_url("http://169.254.169.254/latest/meta-data/")

    # Private internal IP ranges
    with pytest.raises(AppException):
        validate_safe_url("http://10.0.0.1/admin")

    with pytest.raises(AppException):
        validate_safe_url("http://192.168.1.1/router")

    # Forbidden Docker service names
    with pytest.raises(AppException):
        validate_safe_url("http://redis:6379")


# ===========================================================================
# 4. PRESIGNED URL AUTHORIZATION & PATH TRAVERSAL
# ===========================================================================

@pytest.mark.asyncio
async def test_presigned_url_blocks_path_traversal(client: AsyncClient):
    """Presigned URL requests with ../ or leading slash must be rejected."""
    token = create_test_supabase_token()
    headers = {"Authorization": f"Bearer {token}"}

    res_upload = await client.post(
        "/api/v1/files/presigned-upload-url",
        headers=headers,
        json={"key": "../../etc/passwd", "expires_in": 900},
    )
    assert res_upload.status_code == 400

    res_download = await client.post(
        "/api/v1/files/presigned-download-url",
        headers=headers,
        json={"key": "/root/.ssh/id_rsa", "expires_in": 900},
    )
    assert res_download.status_code == 400


@pytest.mark.asyncio
async def test_presigned_upload_blocks_outputs_namespace_for_regular_users(client: AsyncClient):
    """Regular users cannot generate presigned upload URLs directly into outputs/."""
    token = create_test_supabase_token(is_superuser=False)
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.post(
        "/api/v1/files/presigned-upload-url",
        headers=headers,
        json={"key": "outputs/job123/result.mp4", "expires_in": 900},
    )
    assert res.status_code == 403


# ===========================================================================
# 5. RESOURCE LIMITS & IMAGE PROCESSING
# ===========================================================================

def test_image_processor_rejects_excessive_dimensions(tmp_path):
    """Image processor rejects width or height exceeding 8192 pixels."""
    from PIL import Image

    test_img = tmp_path / "test.png"
    Image.new("RGB", (100, 100), color="blue").save(test_img)
    output_img = tmp_path / "out.png"

    # Excessive width
    with pytest.raises(AppException) as exc1:
        image_processor.process_file(
            input_path=test_img,
            output_path=output_img,
            options={"operation": "resize", "options": {"width": 99999}},
        )
    assert "between 1 and 8192" in str(exc1.value.detail)

    # Negative height
    with pytest.raises(AppException) as exc2:
        image_processor.process_file(
            input_path=test_img,
            output_path=output_img,
            options={"operation": "resize", "options": {"height": -10}},
        )
    assert "between 1 and 8192" in str(exc2.value.detail)


# ===========================================================================
# 6. LOCAL STORAGE PATH TRAVERSAL
# ===========================================================================

def test_storage_service_rejects_path_traversal():
    """StorageService raises ValueError when key attempts traversal outside uploads/."""
    from app.services.storage_service import StorageService

    service = StorageService()
    with pytest.raises(ValueError) as exc:
        service.download_bytes(key="../../app/core/config.py")
    assert "Path traversal detected" in str(exc.value)

    with pytest.raises(ValueError):
        service.create_presigned_upload_url(key="../secret.txt")


# ===========================================================================
# 7. PAYOS WEBHOOK SIGNATURE VERIFICATION
# ===========================================================================

def test_payos_webhook_signature_verification():
    """PayOS webhook verification succeeds with valid HMAC and fails on tampering."""
    test_key = "0123456789abcdef0123456789abcdef"
    data = {"orderCode": 12345, "amount": 50000, "status": "PAID"}

    import hashlib
    import hmac

    # Compute expected signature
    sorted_items = sorted((k, v) for k, v in data.items() if v is not None)
    sign_data = "&".join(f"{k}={v}" for k, v in sorted_items)
    valid_sig = hmac.new(test_key.encode("utf-8"), sign_data.encode("utf-8"), hashlib.sha256).hexdigest()

    # Valid signature
    assert verify_payos_signature(data, valid_sig, test_key) is True

    # Tampered signature
    assert verify_payos_signature(data, "tampered-invalid-sig", test_key) is False

    # Tampered amount
    tampered_data = {"orderCode": 12345, "amount": 1000, "status": "PAID"}
    assert verify_payos_signature(tampered_data, valid_sig, test_key) is False
