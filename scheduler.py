import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from collectors.base import MetricsSource
from config.slos import SLODefinition, load_slos
from correlate.correlator import correlate
from db.models import AlertEvent, BurnRateSample, CorrelationEvent
from engine.burn_rate import budget_remaining_pct, compute_burn_rate
from engine.forecaster import ExhaustionForecaster
from events.base import ChangeEventStore
from outputs.notify import Notification, send
from outputs.postmortem import render_postmortem, write_postmortem

logger = logging.getLogger(__name__)


async def evaluate_slo(
    slo: SLODefinition,
    source: MetricsSource,
    session_factory,
    event_store: ChangeEventStore,
    *,
    notify_webhook_url: str | None = None,
    slack_webhook_url: str | None = None,
    postmortem_dir: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    series_1h = await source.query_range(slo.metric_query, now - timedelta(hours=1), now, 300)
    good_1h = [v for _, v in series_1h] or [await _instant(source, slo)]
    good_1h = [g for g in good_1h if g is not None] or [1.0]

    latest_good = good_1h[-1]
    burn_1h = compute_burn_rate(sum(good_1h) / len(good_1h), slo.target_percent)
    series_6h = await source.query_range(slo.metric_query, now - timedelta(hours=6), now, 300)
    good_6h = [v for _, v in series_6h] or good_1h
    burn_6h = compute_burn_rate(sum(good_6h) / len(good_6h), slo.target_percent)
    budget = budget_remaining_pct(good_6h, slo.target_percent)

    async with session_factory() as s:
        s.add(BurnRateSample(slo_name=slo.name, service=slo.service,
                             budget_remaining_pct=budget, burn_rate_1h=burn_1h,
                             burn_rate_6h=burn_6h, sampled_at=now))
        await s.commit()
        recent = (await s.execute(
            select(BurnRateSample).where(BurnRateSample.slo_name == slo.name)
            .order_by(BurnRateSample.sampled_at.desc()).limit(24)
        )).scalars().all()

    forecast = ExhaustionForecaster.forecast(list(reversed(recent)))
    forecast_hours = forecast.point_estimate_hours if forecast else None

    out = {
        "slo": slo.name, "service": slo.service, "budget_remaining_pct": budget,
        "burn_rate_1h": burn_1h, "burn_rate_6h": burn_6h,
        "forecast_hours": forecast_hours, "latest_good": latest_good,
        "severity": None, "probable_cause": None, "probable_cause_type": None,
    }

    severity = None
    if burn_1h >= slo.critical_burn_rate:
        severity = "critical"
    elif burn_1h >= slo.warning_burn_rate:
        severity = "warning"
    if severity is None:
        return out

    async with session_factory() as s:
        alert = AlertEvent(slo_name=slo.name, service=slo.service,
                           severity=severity, burn_rate=burn_1h, fired_at=now)
        s.add(alert)
        await s.commit()
        alert_id = alert.id

    changes = await event_store.recent_for_service(
        slo.service, now - timedelta(minutes=30), now + timedelta(minutes=5))
    # SQLite drops tzinfo on round-trip (DateTime(timezone=True) is not enforced
    # by the sqlite dialect), so timestamps read back from a fresh session come
    # back naive even though the store always writes UTC. Reattach UTC here at
    # the wiring boundary rather than comparing naive vs. aware downstream.
    for change in changes:
        if change.occurred_at.tzinfo is None:
            change.occurred_at = change.occurred_at.replace(tzinfo=timezone.utc)
    corr = correlate(changes, now)
    out.update(severity=severity, probable_cause=corr.probable_cause,
               probable_cause_type=corr.probable_cause_type)

    async with session_factory() as s:
        for e in corr.events[:3]:
            s.add(CorrelationEvent(alert_event_id=alert_id, event_time=e["time"],
                                   event_type=e["type"], source_system=e["source"],
                                   description=e["description"], score=e["final_score"]))
        await s.commit()

    notification = Notification(slo.name, slo.service, severity, burn_1h, budget,
                                forecast_hours, corr.probable_cause)
    await send(notification, webhook_url=notify_webhook_url, slack_webhook_url=slack_webhook_url)

    if severity == "critical" and postmortem_dir:
        md = render_postmortem(slo.name, slo.service, severity, burn_1h, budget,
                               forecast_hours, corr)
        write_postmortem(md, postmortem_dir, slo.name, now)

    return out


async def _instant(source, slo):
    try:
        return await source.query_instant(slo.metric_query)
    except Exception:  # noqa: BLE001
        return None


def run_scheduler(slos, source, session_factory, event_store, settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    for slo in slos:
        scheduler.add_job(
            evaluate_slo, "interval", seconds=settings.poll_interval_seconds,
            args=[slo, source, session_factory, event_store],
            kwargs=dict(notify_webhook_url=settings.notify_webhook_url,
                        slack_webhook_url=settings.slack_webhook_url,
                        postmortem_dir=settings.postmortem_dir),
            id=f"eval:{slo.name}", max_instances=1, coalesce=True,
        )
    return scheduler
