from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


class SandboxImageStatus(StrEnum):
    PULLING = "pulling"
    READY = "ready"
    FAILED = "failed"
    CANCELED = "canceled"


class SandboxImage(SQLModel, table=True):
    __tablename__ = "sandbox_images"

    id: int | None = Field(default=None, primary_key=True)
    image_name: str = Field(default="")
    image_size: int = Field(default=0)
    image_hash: str = Field(default="")
    status: SandboxImageStatus = Field(default=SandboxImageStatus.PULLING)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
