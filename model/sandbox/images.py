from datetime import datetime

from sqlalchemy import BigInteger, Column
from sqlmodel import Field, SQLModel

from schema.sandbox.images import SandboxImageStatus


class SandboxImage(SQLModel, table=True):
    __tablename__ = "sandbox_images"

    id: int | None = Field(default=None, primary_key=True)
    image_name: str = Field(default="")
    image_size: int = Field(default=0, sa_column=Column(BigInteger, nullable=False))
    image_hash: str = Field(default="")
    status: SandboxImageStatus = Field(default=SandboxImageStatus.PULLING)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
