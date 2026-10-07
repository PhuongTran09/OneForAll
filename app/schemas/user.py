from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr | None = None
    username: str = Field(..., min_length=3, max_length=50)
    full_name: str | None = None
    is_active: bool = True


class UserCreate(BaseModel):
    """Schema for creating or syncing user profile from Supabase Auth."""

    id: str | None = Field(None, description="UUID from auth.users.id")
    email: EmailStr | None = None
    username: str = Field(..., min_length=3, max_length=50)
    full_name: str | None = None
    is_active: bool = True
    is_superuser: bool = False


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    username: str | None = Field(None, min_length=3, max_length=50)
    full_name: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None


class UserResponse(BaseModel):
    id: str = Field(..., description="UUID primary key")
    email: str | None = None
    username: str
    full_name: str | None = None
    is_active: bool = True
    is_superuser: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


ProfileResponse = UserResponse


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str | None = None
