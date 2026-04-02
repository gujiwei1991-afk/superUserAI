from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
    )

    backend_url: str = "http://localhost:8000"
    github_token: str = ""
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    workspace_dir: str = "/tmp/superuserai/workspace"


@lru_cache
def get_settings() -> Settings:
    return Settings()
