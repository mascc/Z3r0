import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


ROOT_PATH = Path(__file__).resolve().parent
WORKSPACE = ROOT_PATH / ".z3r0"


# strict type config base model
class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# system config
class SystemConfig(StrictConfigModel):
    listen_addr: str = Field(default="127.0.0.1")
    listen_port: int = Field(default=8000)
    encrypt_key: str = Field(default="z3r0-jwt-secret-key-1234567890!@#$")


# database config
class DatabaseConfig(StrictConfigModel):
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=5433)
    database: str = Field(default="z3r0")
    username: str = Field(default="")
    password: str = Field(default="")


# agent config
class AgentConfig(StrictConfigModel):
    code: str = Field(default="")
    name: str = Field(default="")
    description: str = Field(default="")
    base_url: str = Field(default="")
    api_key: str = Field(default="")
    model: str = Field(default="")


# global config
class GlobalConfig(StrictConfigModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    agents: dict[str, AgentConfig] = Field(default_factory=dict)


###
# global config instance
###
_cfg: GlobalConfig = GlobalConfig()


def load_config():
    """load config from json file"""
    global _cfg

    config_file = WORKSPACE / "config.json"
    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    next_cfg = GlobalConfig.model_validate(data)
    for field_name in type(_cfg).model_fields:
        setattr(_cfg, field_name, getattr(next_cfg, field_name))


def get_config():
    """get config instance"""
    global _cfg
    return _cfg
