from fastapi import APIRouter

from app.core.config import settings
from app.services.bg_removal_service import bg_removal_service

router = APIRouter()


@router.get("/health", summary="Health Check")
async def health_check():
    """Kiểm tra tình trạng hoạt động của API và AI Model"""
    ai_status = bg_removal_service.get_system_status()
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        **ai_status,
    }
