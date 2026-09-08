import pytest
from datetime import datetime, timezone, timedelta
from db.base import make_engine, make_session_factory, init_db
from db.models import AlertEvent
from events.base import ChangeEventStore, ChangeEventInput
from config.slos import SLODefinition
from scheduler import evaluate_slo
from sqlalchemy import select

class DecliningSource:
    """Good-ratio well below target: forces a critical burn."""
    async def query_instant(self, q): return 0.80
    async def query_range(self, q, start, end, step):
        return [(start + timedelta(minutes=5*i), 0.80) for i in range(12)]

SLO = SLODefinition("Demo - Availability", "demo", 99.0, 30, "q",
                    warning_burn_rate=2.0, critical_burn_rate=10.0)

async def test_demo_end_to_end(monkeypatch):
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sf = make_session_factory(engine)
    store = ChangeEventStore(sf)
    now = datetime.now(timezone.utc)
    await store.record(ChangeEventInput("demo", "deploy", "argocd",
                                        "deploy demo v9 (bad release)", now - timedelta(minutes=1)))
    import scheduler as sched
    async def fake_send(n, **kw): pass
    monkeypatch.setattr(sched, "send", fake_send)
    out = await evaluate_slo(SLO, DecliningSource(), sf, store)
    async with sf() as s:
        alerts = (await s.execute(select(AlertEvent))).scalars().all()
    assert alerts and alerts[0].severity == "critical"
    assert out["probable_cause_type"] == "deploy"
    assert "v9" in out["probable_cause"]
