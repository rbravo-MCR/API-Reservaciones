from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str | None = None  # e.g. mysql+asyncmy://user:pass@host:3306/dbname
    stripe_api_key: str | None = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = None
    use_in_memory: bool = True
    supplier_base_url: str | None = None
    supplier_timeout_seconds: float = 5.0
    americagroup_endpoint: str | None = None
    americagroup_requestor_id: str | None = None
    americagroup_timeout_seconds: float = 5.0
    americagroup_retry_times: int = 2
    americagroup_retry_sleep_ms: int = 300
    
    google_api_key: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
