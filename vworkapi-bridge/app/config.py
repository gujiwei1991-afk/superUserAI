from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
    )

    qiniu_ak: str = ""
    qiniu_sk: str = ""
    qiniu_bucket: str = ""
    qiniu_domain: str = ""
    image_bridge_token: str = ""
    vworkapi_host: str = "127.0.0.1"
    vworkapi_port: int = 8989
    tmp_dir: str = "/tmp/superuserai-images"
    max_image_bytes: int = 10 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
