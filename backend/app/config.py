from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
    )

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/superuserai"
    redis_url: str = "redis://localhost:6379"
    vwork_api_host: str = "127.0.0.1"
    vwork_api_port: int = 8989
    vwork_msg_port: int = 9000
    github_token: str = ""
    github_webhook_secret: str = ""
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    admin_password: str = "admin123"
    jwt_secret: str = "CHANGE_ME_USE_OPENSSL_RAND_HEX_32"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    intent_llm_model: str = ""  # empty = use llm_model
    intent_llm_timeout_seconds: float = 5.0
    group_bound_auto_activate: bool = True
    pmagent_ready_hint_after_turns: int = 3
    claude_cli_executable: str = "claude"
    claude_cli_timeout_seconds: int = 180


@lru_cache
def get_settings() -> Settings:
    return Settings()
