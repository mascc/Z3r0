from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schema.common.responses import PaginatedResponse


# canonical sandbox image status; reused by the model and by the public schema
class SandboxImageStatus(StrEnum):
    PULLING = "pulling"
    READY = "ready"
    FAILED = "failed"
    CANCELED = "canceled"


# sandbox image public data schema
class SandboxImageSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    image_name: str
    image_size: int = Field(json_schema_extra={"format": "int64"})
    image_hash: str
    status: SandboxImageStatus
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


# delete sandbox image response schema (presence implies success)
class DeleteSandboxImageResponse(BaseModel):
    id: int


# query sandbox images response schema
class QuerySandboxImagesResponse(PaginatedResponse[SandboxImageSchema]):
    pass
