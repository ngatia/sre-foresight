from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import select

from db.base import init_db, make_engine, make_session_factory
from db.models import BurnRateSample


async def _round_trip(sampled_at: datetime) -> datetime:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    session_factory = make_session_factory(engine)
    async with session_factory() as s:
        s.add(BurnRateSample(
            slo_name="x", service="x", budget_remaining_pct=90.0,
            burn_rate_1h=1.0, burn_rate_6h=1.0,
            sampled_at=sampled_at,
        ))
        await s.commit()
    async with session_factory() as s:
        row = (await s.execute(select(BurnRateSample))).scalars().one()
        return row.sampled_at


async def test_naive_datetime_round_trips_as_utc():
    naive = datetime(2026, 9, 8, 12, 0, 0)
    result = await _round_trip(naive)
    assert result.tzinfo == UTC
    assert result == naive.replace(tzinfo=UTC)


async def test_non_utc_aware_datetime_round_trips_as_same_instant_in_utc():
    plus_five = timezone(timedelta(hours=5))
    aware = datetime(2026, 9, 8, 17, 0, 0, tzinfo=plus_five)
    result = await _round_trip(aware)
    assert result.tzinfo == UTC
    assert result == aware.astimezone(UTC)
    # 17:00+05:00 is 12:00 UTC
    assert result == datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)
