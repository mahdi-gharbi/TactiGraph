from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SOURCE_COMMIT = "4b73468fc5b0f1950f9f66fada70ad3a4f9327cb"
SOURCE_BASE = f"https://raw.githubusercontent.com/hudl/open-data/{SOURCE_COMMIT}"
SOURCE_WEB = f"https://github.com/hudl/open-data/blob/{SOURCE_COMMIT}"
METRIC_VERSION = "shot-count-v1"
PIPELINE_VERSION = "foundation-v1"
MATCH_ID = 19717
COMPETITION_ID = 37
SEASON_ID = 4


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TACTIGRAPH_", env_file=".env", extra="ignore", populate_by_name=True
    )
    database_url: str = "sqlite:///data/tactigraph.db"
    league: Literal["wsl", "premier-league"] = "wsl"

    def for_league(self, league):
        if league == self.league:
            return self
        if league != "premier-league":
            raise ValueError("Unsupported dataset transition")
        directory = self.data_dir / "premier-league"
        return self.model_copy(
            update={
                "league": league,
                "data_dir": directory,
                "database_url": f"sqlite:///{directory.as_posix()}/tactigraph.db",
            }
        )

    @field_validator("database_url")
    @classmethod
    def postgres_driver(cls, value):
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    data_dir: Path = Path("data")
    frontend_dir: Path = Path("frontend/dist")
    mode: Literal["local", "public"] = "local"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_digest: str = ""
    ollama_timeout_seconds: float = 30.0
    groq_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="GROQ_API_KEY")
    groq_model: Literal["openai/gpt-oss-20b"] = "openai/gpt-oss-20b"
    groq_timeout_seconds: float = Field(default=20.0, gt=0, le=60)
