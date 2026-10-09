from typing import Literal

from pydantic import BaseModel, Field


class PresignedUrlRequest(BaseModel):
    key: str = Field(min_length=1, max_length=1024)
    content_type: str | None = Field(default=None, max_length=255)
    expires_in: int = Field(default=900, ge=60, le=86_400)


class PresignedUrlResponse(BaseModel):
    key: str
    url: str
    method: Literal["GET", "PUT"]
    expires_in: int
