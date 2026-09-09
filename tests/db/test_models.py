from datetime import UTC, datetime

import pytest

from db.base import init_db, make_engine, make_session_factory
from db.models import BurnRateSample


@pytest.fixture
async def session_factory():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    return make_session_factory(engine)


async def test_insert_and_read_sample(session_factory):
    async with session_factory() as s:
        s.add(BurnRateSample(
            slo_name="x", service="x", budget_remaining_pct=90.0,
            burn_rate_1h=1.0, burn_rate_6h=1.0,
            sampled_at=datetime.now(UTC),
        ))
        await s.commit()
    async with session_factory() as s:
        from sqlalchemy import select
        rows = (await s.execute(select(BurnRateSample))).scalars().all()
        assert len(rows) == 1 and rows[0].budget_remaining_pct == 90.0
