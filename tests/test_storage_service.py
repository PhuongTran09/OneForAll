from unittest.mock import MagicMock

from app.schemas.file import PresignedUrlResponse
from app.services.storage_service import StorageService


def test_storage_service_unconfigured_fallback():
    service = StorageService()
    service.get_client = MagicMock(return_value=None)

    resp = service.create_presigned_upload_url(
        key="test/doc.pdf", content_type="application/pdf", expires_in=300
    )
    assert isinstance(resp, PresignedUrlResponse)
    assert resp.key == "test/doc.pdf"
    assert resp.method == "PUT"
    assert "upload/test/doc.pdf" in resp.url

    download_resp = service.create_presigned_download_url(
        key="test/doc.pdf", expires_in=300
    )
    assert isinstance(download_resp, PresignedUrlResponse)
    assert download_resp.key == "test/doc.pdf"
    assert download_resp.method == "GET"
    assert "download/test/doc.pdf" in download_resp.url


def test_storage_service_with_boto3_client():
    service = StorageService()
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://r2.test.fake/presigned"
    service.get_client = MagicMock(return_value=mock_client)

    resp = service.create_presigned_upload_url(
        key="uploads/file.png", content_type="image/png", expires_in=600
    )
    assert resp.url == "https://r2.test.fake/presigned"
    mock_client.generate_presigned_url.assert_called_once_with(
        ClientMethod="put_object",
        Params={
            "Bucket": "oneforall",
            "Key": "uploads/file.png",
            "ContentType": "image/png",
        },
        ExpiresIn=600,
    )


def test_storage_service_crud_methods():
    service = StorageService()
    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_body.read.return_value = b"file-bytes-content"
    mock_client.get_object.return_value = {"Body": mock_body}
    service.get_client = MagicMock(return_value=mock_client)

    # Upload
    key = service.upload_bytes(
        data=b"hello", key="uploads/hello.txt", content_type="text/plain"
    )
    assert key == "uploads/hello.txt"
    mock_client.put_object.assert_called_once()

    # Download
    data = service.download_bytes(key="uploads/hello.txt")
    assert data == b"file-bytes-content"

    # Delete
    deleted = service.delete_file(key="uploads/hello.txt")
    assert deleted is True

    # Exists
    exists = service.file_exists(key="uploads/hello.txt")
    assert exists is True
