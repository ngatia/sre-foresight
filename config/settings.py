from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./data/foresight.db"
    prometheus_url: str = "http://localhost:9090"
    prometheus_token: str | None = None
    slo_config_path: str = "config/slos.yaml"
    poll_interval_seconds: int = 60

    slack_webhook_url: str | None = None
    notify_webhook_url: str | None = None
    postmortem_dir: str | None = None

    kubernetes_watch_enabled: bool = False
    argocd_url: str | None = None
    argocd_token: str | None = None
    argocd_insecure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
