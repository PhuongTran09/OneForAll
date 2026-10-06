from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.job import JobStatus


class JobCreate(BaseModel):
    id: str | None = Field(default=None, max_length=36)
    user_id: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1, max_length=100)
    input_key: str | None = Field(default=None, max_length=1024)
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobResponse(BaseModel):
    id: str
    user_id: str
    type: str
    status: JobStatus
    progress: int
    input_key: str | None
    output_key: str | None
    error: str | None
    metadata: dict[str, Any] = Field(validation_alias="job_metadata")
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None = None

    model_config = {"from_attributes": True}


class JobAccepted(BaseModel):
    job_id: str
    status: JobStatus
