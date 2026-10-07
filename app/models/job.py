from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(StrEnum):
    PENDING = "queued"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Job(BaseModel):
    """Job domain model backed by Supabase public.jobs table."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    type: str
    status: str = JobStatus.QUEUED.value
    progress: int = 0
    input_key: str | None = None
    output_key: str | None = None
    error: str | None = None
    job_metadata: dict = Field(default_factory=dict, alias="metadata")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @property
    def metadata(self) -> dict:
        return self.job_metadata
