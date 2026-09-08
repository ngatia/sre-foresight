import pytest
from datetime import datetime, timezone, timedelta
from db.base import make_engine, make_session_factory, init_db
from db.models import BurnRateSample, AlertEvent
from events.base import ChangeEventStore, ChangeEventInput
from config.slos import SLODefinition
import scheduler as sched
from sqlalchemy import select

class FakeSource:
    def __init__(self, good): self._good = good
    async def query_instant(self, q): return self._good
    async def query_range(self, q, start, end, step):
        n = 12
        return [(start + timedelta(minutes=5*i), self._good) for i in range(n)]

SLO = SLODefinition("Resume - Availability", "resume", 99.0, 30,
                    "q", warning_burn_rate=2.0, critical_burn_rate=10.0)

@pytest.fixture
async def db():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    return make_session_factory(engine)

async def test_healthy_slo_persists_sample_no_alert(db):
    store = ChangeEventStore(db)
    out = await sched.evaluate_slo(SLO, FakeSource(1.0), db, store)
    async with db() as s:
        samples = (await s.execute(select(BurnRateSample))).scalars().all()
        alerts = (await s.execute(select(AlertEvent))).scalars().all()
    assert len(samples) == 1
    assert out["budget_remaining_pct"] == 100.0
    assert alerts == []

async def test_burning_slo_fires_alert_and_correlates(db, monkeypatch):
    store = ChangeEventStore(db)
    spike = datetime.now(timezone.utc)
    await store.record(ChangeEventInput("resume", "deploy", "argocd",
                                        "deploy resume v2", spike - timedelta(minutes=2)))
    sent = {}
    async def fake_send(n, **kw): sent["n"] = n
    monkeypatch.setattr(sched, "send", fake_send)
    # good ratio 0.80 => error 20% vs allowed 1% => burn rate 20x (critical)
    out = await sched.evaluate_slo(SLO, FakeSource(0.80), db, store, slack_webhook_url="http://x")
    async with db() as s:
        alerts = (await s.execute(select(AlertEvent))).scalars().all()
    assert len(alerts) == 1 and alerts[0].severity == "critical"
    assert out["probable_cause_type"] == "deploy"
    assert "resume v2" in sent["n"].probable_cause
