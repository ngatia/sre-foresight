import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from db.base import make_engine, make_session_factory, init_db
from events.base import ChangeEventStore
from config.slos import SLODefinition
from api.main import create_app

SLO = SLODefinition("Resume - Availability", "resume", 99.0, 30, "q")


@pytest.fixture
async def client():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sf = make_session_factory(engine)
    state = {"Resume - Availability": {"slo": "Resume - Availability", "budget_remaining_pct": 100.0}}
    app = create_app(sf, ChangeEventStore(sf), [SLO], state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


async def test_slos_returns_state(client):
    r = await client.get("/api/slos")
    assert r.status_code == 200
    assert r.json()[0]["slo"] == "Resume - Availability"


async def test_event_ingest_valid(client):
    r = await client.post("/api/events", json={
        "service": "resume", "event_type": "deploy", "source": "argocd",
        "description": "deploy v2", "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    assert r.status_code == 202


async def test_event_ingest_invalid(client):
    r = await client.post("/api/events", json={"service": "resume"})
    assert r.status_code == 422
