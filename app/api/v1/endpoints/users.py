from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, SuperuserDep
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.user_service import user_service

router = APIRouter()


@router.get("/me", response_model=UserResponse, summary="Get current user profile")
async def get_my_profile(current_user: CurrentUser):
    return current_user


@router.patch("/me", response_model=UserResponse, summary="Update current user profile")
async def update_my_profile(user_in: UserUpdate, current_user: CurrentUser):
    return await user_service.update_user(current_user.id, user_in)


@router.get("", response_model=list[UserResponse], summary="List all user profiles (Admin)")
async def list_users(
    superuser: SuperuserDep,
    skip: int = 0,
    limit: int = 100,
):
    return await user_service.get_users(skip=skip, limit=limit)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="Create user profile (Admin)")
async def create_user(
    user_in: UserCreate,
    superuser: SuperuserDep,
):
    return await user_service.create_user(user_in)


@router.get("/{user_id}", response_model=UserResponse, summary="Get user profile by ID")
async def get_user(
    user_id: str,
    current_user: CurrentUser,
):
    if str(current_user.id) != str(user_id) and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied to access this user profile",
        )
    return await user_service.get_user_by_id(user_id)


@router.patch("/{user_id}", response_model=UserResponse, summary="Update user profile (Admin)")
async def update_user(
    user_id: str,
    user_in: UserUpdate,
    superuser: SuperuserDep,
):
    return await user_service.update_user(user_id, user_in)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user profile (Admin)")
async def delete_user(
    user_id: str,
    superuser: SuperuserDep,
):
    await user_service.delete_user(user_id)
