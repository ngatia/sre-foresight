from config.settings import Settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom:9090")
    s = Settings()
    assert s.database_url.startswith("sqlite+aiosqlite")
    assert s.prometheus_url == "http://prom:9090"
    assert s.poll_interval_seconds == 60
    assert s.kubernetes_watch_enabled is False


def test_env_override(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom:9090")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "15")
    s = Settings()
    assert s.database_url.startswith("postgresql+asyncpg")
    assert s.poll_interval_seconds == 15
