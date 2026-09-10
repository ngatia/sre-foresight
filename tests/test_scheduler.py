from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import scheduler as sched
from config.slos import SLODefinition
from db.base import init_db, make_engine, make_session_factory
from db.models import AlertEvent, BurnRateSample
from events.base import ChangeEventInput, ChangeEventStore


class FakeSource:
    def __init__(self, good): self._good = good
    async def query_instant(self, q): return self._good
    async def query_range(self, q, start, end, step):
        n = 12
        return [(start + timedelta(minutes=5*i), self._good) for i in range(n)]

class NoDataSource:
    """Range query returns nothing and the instant fallback is None."""
    async def query_instant(self, q): return None
    async def query_range(self, q, start, end, step): return []

class VariableSource:
    """Good ratio can be changed between polls to simulate state transitions."""
    def __init__(self, good): self.good = good
    async def query_instant(self, q): return self.good
    async def query_range(self, q, start, end, step):
        n = 12
        return [(start + timedelta(minutes=5*i), self.good) for i in range(n)]

class RecordingSource:
    """Records every query it's asked. `range_good` backs the 1h/6h range
    queries; `instant_value` backs the window-average budget instant query
    (and the no-data instant fallback, which these tests never exercise since
    range queries always return data)."""
    def __init__(self, range_good, instant_value):
        self._range_good = range_good
        self._instant_value = instant_value
        self.instant_queries: list[str] = []
        self.range_queries: list[str] = []

    async def query_instant(self, q):
        self.instant_queries.append(q)
        return self._instant_value

    async def query_range(self, q, start, end, step):
        self.range_queries.append(q)
        n = 12
        return [(start + timedelta(minutes=5*i), self._range_good) for i in range(n)]

class FallbackSource:
    """Budget instant query returns None (e.g. a metrics gap); range queries
    still have data, so evaluation must not crash and must fall back to the
    6h window average for the budget."""
    async def query_instant(self, q): return None
    async def query_range(self, q, start, end, step):
        n = 12
        return [(start + timedelta(minutes=5*i), 1.0) for i in range(n)]

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

async def test_no_data_skips_sample_and_alert(db):
    # An SLI returning no series must not fail open to 100% healthy: no
    # BurnRateSample is persisted, no AlertEvent fires, result is marked no_data.
    store = ChangeEventStore(db)
    out = await sched.evaluate_slo(SLO, NoDataSource(), db, store)
    async with db() as s:
        samples = (await s.execute(select(BurnRateSample))).scalars().all()
        alerts = (await s.execute(select(AlertEvent))).scalars().all()
    assert samples == []
    assert alerts == []
    assert out["status"] == "no_data"
    assert out["budget_remaining_pct"] is None
    assert out["burn_rate_1h"] is None

async def test_burning_slo_fires_alert_and_correlates(db, monkeypatch):
    store = ChangeEventStore(db)
    spike = datetime.now(UTC)
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


async def test_consecutive_criticals_alert_once_with_shared_state(db, monkeypatch):
    # A single ongoing incident polled 3x at the same severity must create
    # exactly one AlertEvent and send exactly one notification, not one per poll.
    store = ChangeEventStore(db)
    sent = []
    async def fake_send(n, **kw): sent.append(n)
    monkeypatch.setattr(sched, "send", fake_send)

    alert_state: dict = {}
    source = VariableSource(0.80)  # 20x burn -> critical
    for _ in range(3):
        out = await sched.evaluate_slo(SLO, source, db, store, alert_state=alert_state)
        assert out["severity"] == "critical"

    async with db() as s:
        alerts = (await s.execute(select(AlertEvent))).scalars().all()
    assert len(alerts) == 1
    assert len(sent) == 1


async def test_state_transitions_fire_dedupe_and_recover(db, monkeypatch):
    store = ChangeEventStore(db)
    sent = []
    async def fake_send(n, **kw): sent.append(n)
    monkeypatch.setattr(sched, "send", fake_send)

    alert_state: dict = {}
    source = VariableSource(0.80)  # critical

    # None -> critical: fires
    out = await sched.evaluate_slo(SLO, source, db, store, alert_state=alert_state)
    assert out["severity"] == "critical"
    assert out["alerted"] is True

    # critical -> critical: does not re-fire
    out = await sched.evaluate_slo(SLO, source, db, store, alert_state=alert_state)
    assert out["severity"] == "critical"
    assert out["alerted"] is False

    async with db() as s:
        alerts = (await s.execute(select(AlertEvent))).scalars().all()
    assert len(alerts) == 1
    assert len(sent) == 1

    # critical -> None: sends a recovery notification, no new AlertEvent
    source.good = 1.0
    out = await sched.evaluate_slo(SLO, source, db, store, alert_state=alert_state)
    assert out["severity"] is None
    assert out["alerted"] is False

    async with db() as s:
        alerts = (await s.execute(select(AlertEvent))).scalars().all()
    assert len(alerts) == 1
    assert len(sent) == 2
    assert sent[-1].severity == "resolved"

    # None -> critical again (post-recovery): fires again
    source.good = 0.80
    out = await sched.evaluate_slo(SLO, source, db, store, alert_state=alert_state)
    assert out["severity"] == "critical"
    assert out["alerted"] is True

    async with db() as s:
        alerts = (await s.execute(select(AlertEvent))).scalars().all()
    assert len(alerts) == 2
    assert len(sent) == 3


async def test_budget_query_is_a_window_aligned_subquery(db):
    # budget_remaining_pct must be computed from a single server-side
    # avg_over_time(...)[window_days:res] subquery over the SLO's declared
    # window, not the 6h range used for burn_rate_6h.
    store = ChangeEventStore(db)
    source = RecordingSource(range_good=1.0, instant_value=1.0)
    await sched.evaluate_slo(SLO, source, db, store)  # SLO.window_days == 30
    assert len(source.instant_queries) == 1
    q = source.instant_queries[0]
    assert q.startswith("avg_over_time(")
    assert "[30d:" in q

async def test_budget_reflects_full_window_average_not_a_brief_blip(db):
    # KEY test: a window-average of 0.9999 (a brief 5-min blip diluted over
    # 30 days) must leave ~90% of the budget, not zero it - proving the fix
    # for the flapping caused by the old 6h-average approximation.
    store = ChangeEventStore(db)

    healthy = RecordingSource(range_good=1.0, instant_value=1.0)
    out = await sched.evaluate_slo(SLO, healthy, db, store)
    assert out["budget_remaining_pct"] == 100.0

    slo_999 = SLODefinition("x", "resume", 99.9, 30, "q")
    exhausted = RecordingSource(range_good=1.0, instant_value=0.999)
    out = await sched.evaluate_slo(slo_999, exhausted, db, store)
    assert out["budget_remaining_pct"] == 0.0

    blip_diluted = RecordingSource(range_good=1.0, instant_value=0.9999)
    out = await sched.evaluate_slo(slo_999, blip_diluted, db, store)
    assert out["budget_remaining_pct"] == pytest.approx(90.0, abs=1.0)

async def test_burn_rate_1h_still_comes_from_1h_range_unaffected_by_budget(db):
    # burn_rate_1h/6h are short-window alerting signals and must stay exactly
    # as before: derived from the 1h/6h range queries, independent of the
    # window-average budget query's result.
    store = ChangeEventStore(db)
    source = RecordingSource(range_good=1.0, instant_value=0.5)
    out = await sched.evaluate_slo(SLO, source, db, store)
    assert out["burn_rate_1h"] == 0.0
    assert out["severity"] is None

async def test_budget_falls_back_to_6h_window_when_subquery_has_no_data(db):
    # A metrics gap on the budget subquery (query_instant -> None) must not
    # crash evaluation; it falls back to the existing 6h good-ratio average.
    store = ChangeEventStore(db)
    out = await sched.evaluate_slo(SLO, FallbackSource(), db, store)
    assert out["status"] == "ok"
    assert out["budget_remaining_pct"] == 100.0
