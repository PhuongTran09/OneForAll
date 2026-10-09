from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "OneForAll"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # Supabase (Auth & PostgreSQL)
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""

    # Celery / Redis
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    CELERY_PROCESS_JOB_TASK: str = "app.worker.tasks.process_job"
    CELERY_DEFAULT_QUEUE: str = "convert"

    # Cloudflare R2 Storage
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "oneforall"
    R2_ENDPOINT_URL: str = ""
    R2_PUBLIC_BASE_URL: str = ""

    @property
    def r2_endpoint(self) -> str:
        if self.R2_ENDPOINT_URL:
            return self.R2_ENDPOINT_URL
        if self.R2_ACCOUNT_ID:
            return f"https://{self.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        return ""

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # AI Model Settings
    BIREFNET_MODEL_NAME: str = "ZhengPeng7/BiRefNet"
    # Must be an immutable 40-character Hugging Face commit SHA in production.
    BIREFNET_MODEL_REVISION: str = ""
    MODEL_DEVICE: str = "cuda"  # 'cuda', 'auto', or 'cpu'
    PRELOAD_MODEL: bool = False  # Heavy model loading belongs to Celery workers.

    # Upload limits (bytes). Upload middleware caps the whole multipart body;
    # endpoint validation applies stricter limits to the actual file by category.
    MAX_AUDIO_UPLOAD_BYTES: int = 200 * 1024 * 1024
    MAX_IMAGE_UPLOAD_BYTES: int = 50 * 1024 * 1024
    MAX_BACKGROUND_REMOVAL_UPLOAD_BYTES: int = 25 * 1024 * 1024
    MAX_DOCUMENT_UPLOAD_BYTES: int = 100 * 1024 * 1024
    MAX_VIDEO_UPLOAD_BYTES: int = 1024 * 1024 * 1024
    MAX_OTHER_UPLOAD_BYTES: int = 100 * 1024 * 1024

    # Auth Flags (True = Bắt buộc đăng nhập Bearer token, False = Tắt auth / cho phép gọi ẩn danh)
    AUTH_REQUIRED_MEDIA: bool = False
    AUTH_REQUIRED_IMAGE: bool = False
    AUTH_REQUIRED_CONVERT: bool = False
    AUTH_REQUIRED_JOBS: bool = False
    AUTH_REQUIRED_DOWNLOAD: bool = False

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
