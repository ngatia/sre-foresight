import pytest
from datetime import datetime, timezone, timedelta
from db.base import make_engine, make_session_factory, init_db
from events.base import ChangeEventStore, ChangeEventInput

@pytest.fixture
async def store():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    return ChangeEventStore(make_session_factory(engine))

async def test_record_and_query_window(store):
    now = datetime.now(timezone.utc)
    await store.record(ChangeEventInput("resume", "deploy", "argocd", "deploy resume", now))
    await store.record(ChangeEventInput("other", "deploy", "argocd", "deploy other", now))
    rows = await store.recent_for_service("resume", now - timedelta(minutes=5), now + timedelta(minutes=5))
    assert len(rows) == 1 and rows[0].service == "resume"

async def test_window_excludes_out_of_range(store):
    now = datetime.now(timezone.utc)
    await store.record(ChangeEventInput("resume", "deploy", "argocd", "old", now - timedelta(hours=2)))
    rows = await store.recent_for_service("resume", now - timedelta(minutes=5), now + timedelta(minutes=5))
    assert rows == []
