from fastapi import APIRouter, status

from app.api.deps import SessionDep
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.user_service import UserService

router = APIRouter()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user_in: UserCreate, session: SessionDep):
    service = UserService(session)
    return await service.create_user(user_in)


@router.get("", response_model=list[UserResponse])
async def list_users(session: SessionDep, skip: int = 0, limit: int = 100):
    service = UserService(session)
    return await service.get_users(skip=skip, limit=limit)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, session: SessionDep):
    service = UserService(session)
    return await service.get_user_by_id(user_id)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user_in: UserUpdate, session: SessionDep):
    service = UserService(session)
    return await service.update_user(user_id, user_in)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, session: SessionDep):
    service = UserService(session)
    await service.delete_user(user_id)
