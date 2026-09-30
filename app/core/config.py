from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "OneForAll"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production-123456789"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./oneforall.db"

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # AI Model Settings
    BIREFNET_MODEL_NAME: str = "ZhengPeng7/BiRefNet"
    MODEL_DEVICE: str = "cuda"  # 'cuda', 'auto', or 'cpu'
    PRELOAD_MODEL: bool = True  # Preload model into GPU on startup

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
