import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    slo = tmp_path / "slos.yaml"
    slo.write_text(
        "slos:\n  - name: X\n    service: x\n    target_percent: 99\n"
        "    window_days: 30\n    metric_query: up\n"
    )
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom:9090")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SLO_CONFIG_PATH", str(slo))
    from config.settings import get_settings
    get_settings.cache_clear()


async def test_app_builds_and_health_ok():
    import app as appmod
    application = appmod.build()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/health")
    assert r.status_code == 200
