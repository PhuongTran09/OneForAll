from fastapi import APIRouter

from app.api.v1.endpoints import (
    convert_file,
    files,
    health,
    image,
    jobs,
    media,
    payments,
    users,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(convert_file.router)
api_router.include_router(image.router)
api_router.include_router(media.router)
api_router.include_router(jobs.router)
api_router.include_router(files.router)
api_router.include_router(payments.router)
