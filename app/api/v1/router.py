from fastapi import APIRouter

from app.api.v1.endpoints import bg_removal, converter, health, users

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(bg_removal.router, tags=["AI Background Removal"])
api_router.include_router(converter.router)
