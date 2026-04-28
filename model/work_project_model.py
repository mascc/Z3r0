from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


class WorkProjectStatus(StrEnum):
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class WorkProjectType(StrEnum):
    PENETRATION_TEST = "penetration_test"
    SOURCE_CODE_AUDIT = "source_code_audit"


class WorkProject(SQLModel, table=True):
    __tablename__ = "work_projects"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="")
    session_id: str = Field(default="")
    description: str = Field(default="")
    status: WorkProjectStatus = Field(default=WorkProjectStatus.WORKING)
    type: WorkProjectType = Field(default=WorkProjectType.PENETRATION_TEST)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)