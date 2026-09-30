from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints.bg_removal import router as bg_removal_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import Base, engine
from app.services.bg_removal_service import bg_removal_service
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} in {settings.APP_ENV} mode...")
    # Create tables automatically for quick-start development if SQLite
    if "sqlite" in settings.DATABASE_URL:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified/created.")

    # Preload AI model on startup
    if settings.PRELOAD_MODEL:
        try:
            import asyncio

            logger.info("Đang nạp trước mô hình BiRefNet lên GPU/VRAM...")
            await asyncio.to_thread(bg_removal_service.load_model)
            logger.info("Mô hình BiRefNet đã nạp sẵn sàng phục vụ các yêu cầu.")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Không thể tải trước mô hình AI lúc khởi động: {e}")

    yield

    logger.info(f"Shutting down {settings.APP_NAME}...")
    await engine.dispose()


def create_application() -> FastAPI:
    app = FastAPI(
        title=f"{settings.APP_NAME} - API",
        version="1.2.0",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        redoc_url=f"{settings.API_V1_PREFIX}/redoc",
        lifespan=lifespan,
    )

    # Configure CORS
    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Root endpoints (for convenience & backwards compatibility)
    app.include_router(health_router, prefix="", tags=["Health"])
    app.include_router(bg_removal_router, prefix="", tags=["AI Background Removal"])

    # API v1 routes (/api/v1/...)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
