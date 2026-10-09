from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    """User profile model backed by Supabase public.profiles table (linked to auth.users.id)."""

    id: str = Field(..., description="UUID corresponding to auth.users.id")
    email: str | None = None
    username: str
    full_name: str | None = None
    is_active: bool = True
    is_superuser: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


Profile = User
