from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ROOT / ".env", extra="ignore")

    env: str = "dev"
    # App role (vp_app): DML only, subject to RLS. Used by the API and workers.
    database_url: str
    # Owner role (vp_migrator): DDL. Used only by Alembic.
    migration_database_url: str
    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
