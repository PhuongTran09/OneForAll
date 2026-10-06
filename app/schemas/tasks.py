from typing import Any, Literal

from pydantic import BaseModel, Field

VideoOperation = Literal[
    "transcode",
    "extract-audio",
    "thumbnail",
]


class TaskRequest(BaseModel):
    operation: str = Field(min_length=1, max_length=100)
    input_file_key: str = Field(min_length=1, max_length=1024)
    params: dict[str, Any] = Field(default_factory=dict)


class ConvertFileRequest(BaseModel):
    input_key: str = Field(min_length=1, max_length=1024)
    from_format: str = Field(
        alias="from",
        min_length=1,
        max_length=20,
        pattern=r"^[a-z0-9]+$",
    )
    to: str = Field(min_length=1, max_length=20, pattern=r"^[a-z0-9]+$")
    options: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @property
    def operation(self) -> str:
        return f"{self.from_format}-to-{self.to}"


class ImageProcessRequest(BaseModel):
    input_key: str = Field(min_length=1, max_length=1024)
    operation: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9_]+$",
    )
    options: dict[str, Any] = Field(default_factory=dict)


class VideoTaskRequest(TaskRequest):
    operation: VideoOperation
