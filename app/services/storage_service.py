from collections.abc import Iterator
from pathlib import Path
import shutil
from typing import Any
from urllib.parse import quote

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings
from app.schemas.file import PresignedUrlResponse
from app.utils.logger import logger


class StorageService:
    def __init__(self) -> None:
        self._client: BaseClient | None = None

    @staticmethod
    def _validate_key(key: str) -> None:
        if not key or not isinstance(key, str):
            raise ValueError("Key must be a non-empty string")
        clean = key.replace("\\", "/")
        if ".." in clean or clean.startswith("/"):
            raise ValueError(f"Path traversal detected for storage key: '{key}'")

    @staticmethod
    def _resolve_safe_local_path(key: str, base_dir: Path | str = "uploads") -> Path:
        """Resolve storage key to safe local path, preventing directory traversal."""
        StorageService._validate_key(key)
        base = Path(base_dir).resolve()
        clean_key = str(key).replace("\\", "/").lstrip("/")
        target = (base / clean_key).resolve()
        try:
            target.relative_to(base)
        except ValueError as err:
            raise ValueError(f"Path traversal detected for storage key: '{key}'") from err
        return target

    def get_client(self) -> BaseClient | None:
        """
        Lazily initialize and return the boto3 S3 client configured for Cloudflare R2.
        Returns None if credentials or endpoint are not configured.
        """
        if self._client is not None:
            return self._client

        endpoint = settings.r2_endpoint
        access_key = settings.R2_ACCESS_KEY_ID
        secret_key = settings.R2_SECRET_ACCESS_KEY

        if not endpoint or not access_key or not secret_key:
            return None

        self._client = boto3.client(
            service_name="s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )
        return self._client

    @property
    def is_configured(self) -> bool:
        """Check whether Cloudflare R2 credentials have been configured."""
        return self.get_client() is not None

    def create_presigned_upload_url(
        self, *, key: str, content_type: str | None = None, expires_in: int = 900
    ) -> PresignedUrlResponse:
        """
        Generate a presigned PUT URL allowing clients to upload a file directly to Cloudflare R2.
        """
        self._validate_key(key)
        client = self.get_client()
        if client:
            params: dict[str, Any] = {
                "Bucket": settings.R2_BUCKET_NAME,
                "Key": key,
            }
            if content_type:
                params["ContentType"] = content_type

            url = client.generate_presigned_url(
                ClientMethod="put_object",
                Params=params,
                ExpiresIn=expires_in,
            )
            return PresignedUrlResponse(
                key=key,
                url=url,
                method="PUT",
                expires_in=expires_in,
            )

        # Fallback for local development if R2 credentials are not set yet
        logger.warning(
            "R2 is not configured; generating mock upload URL for key: %s", key
        )
        public_base = settings.R2_PUBLIC_BASE_URL or "https://r2.example.local"
        return PresignedUrlResponse(
            key=key,
            url=f"{public_base.rstrip('/')}/upload/{quote(key)}?expires_in={expires_in}",
            method="PUT",
            expires_in=expires_in,
        )

    def create_presigned_download_url(
        self,
        *,
        key: str,
        expires_in: int = 900,
        response_content_disposition: str | None = None,
    ) -> PresignedUrlResponse:
        """
        Generate a presigned GET URL allowing clients to download a file from Cloudflare R2.
        Supports custom ResponseContentDisposition for proper download filenames.
        """
        self._validate_key(key)
        client = self.get_client()
        if client:
            params: dict[str, Any] = {
                "Bucket": settings.R2_BUCKET_NAME,
                "Key": key,
            }
            if response_content_disposition:
                params["ResponseContentDisposition"] = response_content_disposition

            url = client.generate_presigned_url(
                ClientMethod="get_object",
                Params=params,
                ExpiresIn=expires_in,
            )
            return PresignedUrlResponse(
                key=key,
                url=url,
                method="GET",
                expires_in=expires_in,
            )

        # Fallback for local development if R2 credentials are not set yet
        logger.warning(
            "R2 is not configured; generating mock download URL for key: %s", key
        )
        public_base = settings.R2_PUBLIC_BASE_URL or "https://r2.example.local"
        query_suffix = f"?expires_in={expires_in}"
        if response_content_disposition:
            query_suffix += f"&response_content_disposition={quote(response_content_disposition)}"
        return PresignedUrlResponse(
            key=key,
            url=f"{public_base.rstrip('/')}/download/{quote(key)}{query_suffix}",
            method="GET",
            expires_in=expires_in,
        )

    def upload_file(
        self, *, local_path: str | Path, key: str, content_type: str | None = None
    ) -> str:
        """
        Upload a file directly from SSD/local disk to Cloudflare R2 (or local fallback).
        Uses boto3 managed multipart upload without buffering the entire file into RAM.
        """
        self._validate_key(key)
        src = Path(local_path)
        if not src.exists():
            raise FileNotFoundError(f"Local file '{src}' does not exist for upload to '{key}'.")

        client = self.get_client()
        if client:
            extra_args: dict[str, Any] = {}
            if content_type:
                extra_args["ContentType"] = content_type

            client.upload_file(
                Filename=str(src),
                Bucket=settings.R2_BUCKET_NAME,
                Key=key,
                ExtraArgs=extra_args or None,
            )
            return key

        dest = self._resolve_safe_local_path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        logger.warning("R2 is not configured; copied file locally from %s to %s", src, dest)
        return key

    def upload_fileobj(
        self, *, fileobj: Any, key: str, content_type: str | None = None
    ) -> str:
        """
        Stream an open file-like object directly to Cloudflare R2 (or local fallback).
        Streams in chunks without loading the entire payload into RAM.
        """
        self._validate_key(key)
        client = self.get_client()
        if client:
            extra_args: dict[str, Any] = {}
            if content_type:
                extra_args["ContentType"] = content_type

            client.upload_fileobj(
                Fileobj=fileobj,
                Bucket=settings.R2_BUCKET_NAME,
                Key=key,
                ExtraArgs=extra_args or None,
            )
            return key

        dest = self._resolve_safe_local_path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f_out:
            shutil.copyfileobj(fileobj, f_out, length=1024 * 1024)
        logger.warning("R2 is not configured; saved streamed fileobj to %s", dest)
        return key

    def download_to_file(self, *, key: str, local_path: str | Path) -> Path:
        """
        Download an object from Cloudflare R2 directly to a local SSD file (or local fallback).
        Streams chunks directly to disk without holding the file in RAM.
        """
        self._validate_key(key)
        dest = Path(local_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        client = self.get_client()
        if client:
            client.download_file(
                Bucket=settings.R2_BUCKET_NAME,
                Key=key,
                Filename=str(dest),
            )
            return dest

        src = self._resolve_safe_local_path(key)
        if src.exists():
            shutil.copyfile(src, dest)
            return dest

        raise RuntimeError(f"File {key} not found and Cloudflare R2 is not configured.")

    def upload_bytes(
        self, *, data: bytes, key: str, content_type: str | None = None
    ) -> str:
        """
        Upload raw bytes directly from the server or worker to Cloudflare R2 (or local fallback).
        """
        self._validate_key(key)
        client = self.get_client()
        if client:
            extra_args: dict[str, Any] = {}
            if content_type:
                extra_args["ContentType"] = content_type

            client.put_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=key,
                Body=data,
                **extra_args,
            )
            return key

        # Fallback when R2 is not configured
        local_path = self._resolve_safe_local_path(key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        logger.warning("R2 is not configured; saved file locally to %s", local_path)
        return key

    def download_bytes(self, *, key: str) -> bytes:
        """
        Download file content as raw bytes from Cloudflare R2 (or local fallback).
        """
        self._validate_key(key)
        client = self.get_client()
        if client:
            response = client.get_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=key,
            )
            return response["Body"].read()

        # Local fallback
        local_path = self._resolve_safe_local_path(key)
        if local_path.exists():
            return local_path.read_bytes()
        raise RuntimeError(f"File {key} not found and Cloudflare R2 is not configured.")

    def download_stream(
        self, *, key: str, chunk_size: int = 65536
    ) -> Iterator[bytes]:
        """
        Stream file content in chunks from Cloudflare R2 (or local fallback).
        Prevents high memory usage (RAM) when serving large file downloads.
        """
        self._validate_key(key)
        client = self.get_client()
        if client:
            response = client.get_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=key,
            )
            yield from response["Body"].iter_chunks(chunk_size=chunk_size)
            return

        local_path = self._resolve_safe_local_path(key)
        if local_path.exists():
            with open(local_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    yield chunk
            return
        raise RuntimeError(f"File {key} not found and Cloudflare R2 is not configured.")

    def delete_file(self, *, key: str) -> bool:
        """
        Delete a file from Cloudflare R2 bucket.
        """
        self._validate_key(key)
        client = self.get_client()
        if not client:
            return False

        try:
            client.delete_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=key,
            )
            return True
        except ClientError as exc:
            logger.error("Failed to delete %s from R2: %s", key, exc)
            return False

    def file_exists(self, *, key: str) -> bool:
        """
        Check if an object exists in Cloudflare R2 bucket.
        """
        client = self.get_client()
        if not client:
            return False

        try:
            client.head_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=key,
            )
            return True
        except ClientError:
            return False

    def test_connection(self) -> dict[str, Any]:
        """
        Test the connection to Cloudflare R2 and verify bucket access.
        """
        client = self.get_client()
        if not client:
            return {
                "connected": False,
                "error": "R2 credentials missing (R2_ACCOUNT_ID/R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY)",
            }

        try:
            client.head_bucket(Bucket=settings.R2_BUCKET_NAME)
            return {
                "connected": True,
                "bucket": settings.R2_BUCKET_NAME,
                "endpoint": settings.r2_endpoint,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "connected": False,
                "bucket": settings.R2_BUCKET_NAME,
                "error": str(exc),
            }


storage_service = StorageService()
