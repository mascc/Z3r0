from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SandboxImageStatusSchema(StrEnum):
    PULLING = "pulling"
    READY = "ready"
    FAILED = "failed"
    CANCELED = "canceled"


# sandbox image public data schema
class SandboxImageSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    image_name: str
    image_size: int
    image_hash: str
    status: SandboxImageStatusSchema
    created_at: datetime
    updated_at: datetime


# create sandbox image request schema
class CreateSandboxImageRequest(BaseModel):
    image_name: str = Field(min_length=1, max_length=255)

    @field_validator("image_name", mode="before")
    @classmethod
    def normalize_image_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


# delete sandbox image response schema
class DeleteSandboxImageResponse(BaseModel):
    id: int
    deleted: bool


# query sandbox images response schema
class QuerySandboxImagesResponse(BaseModel):
    page: int
    size: int
    items: list[SandboxImageSchema]
