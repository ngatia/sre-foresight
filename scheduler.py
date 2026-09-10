import logging
import math
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from collectors.base import MetricsSource
from config.slos import SLODefinition
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
    alert_state: dict | None = None,
) -> dict:
    now = datetime.now(UTC)
    series_1h = await source.query_range(slo.metric_query, now - timedelta(hours=1), now, 300)
    good_1h = [v for _, v in series_1h]
    if not good_1h:
        instant = await _instant(source, slo.metric_query)
        if instant is not None:
            good_1h = [instant]
    good_1h = [g for g in good_1h if g is not None]

    # Fail closed on missing data: an SLI that returns no series must NOT read as
    # 100% healthy. Skip the sample entirely (no persistence, no alert) and mark
    # the result "no_data" so the caller/dashboard can show it as stale, not green.
    if not good_1h:
        logger.warning("no data for SLO %s, skipping sample", slo.name)
        return {
            "slo": slo.name, "service": slo.service, "status": "no_data",
            "budget_remaining_pct": None, "burn_rate_1h": None, "burn_rate_6h": None,
            "forecast_hours": None, "forecast_lower_hours": None,
            "forecast_upper_hours": None, "forecast_model": None,
            "forecast_confidence": None, "latest_good": None,
            "severity": None, "probable_cause": None, "probable_cause_type": None,
        }

    latest_good = good_1h[-1]
    burn_1h = compute_burn_rate(sum(good_1h) / len(good_1h), slo.target_percent)
    series_6h = await source.query_range(slo.metric_query, now - timedelta(hours=6), now, 300)
    good_6h = [v for _, v in series_6h] or good_1h
    burn_6h = compute_burn_rate(sum(good_6h) / len(good_6h), slo.target_percent)

    # budget_remaining_pct reflects the full declared slo.window_days horizon,
    # not the short 1h/6h windows above (those stay dedicated alerting
    # signals). A single server-side subquery averages the good-ratio over
    # the whole window so a brief blip is diluted rather than zeroing the
    # budget: keep the inner subquery resolution coarse (>=5m, <=~720 steps)
    # so Prometheus/Grafana Cloud can evaluate it as one instant query.
    res_seconds = max(300, math.ceil(slo.window_days * 86400 / 720))
    budget_query = (
        f"avg_over_time(({slo.metric_query})[{slo.window_days}d:{_prom_duration(res_seconds)}])"
    )
    good_window = await _instant(source, budget_query)
    if good_window is not None:
        budget = budget_remaining_pct([good_window], slo.target_percent)
    else:
        logger.debug(
            "budget subquery returned no data for SLO %s, falling back to "
            "6h window average", slo.name,
        )
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
    forecast_lower_hours = forecast.lower_ci_hours if forecast else None
    forecast_upper_hours = forecast.upper_ci_hours if forecast else None
    forecast_model = forecast.model_used if forecast else None
    forecast_confidence = forecast.confidence_score if forecast else None

    out = {
        "slo": slo.name, "service": slo.service, "status": "ok",
        "budget_remaining_pct": budget,
        "burn_rate_1h": burn_1h, "burn_rate_6h": burn_6h,
        "forecast_hours": forecast_hours,
        "forecast_lower_hours": forecast_lower_hours,
        "forecast_upper_hours": forecast_upper_hours,
        "forecast_model": forecast_model, "forecast_confidence": forecast_confidence,
        "latest_good": latest_good,
        "severity": None, "probable_cause": None, "probable_cause_type": None,
        "alerted": False,
    }

    severity = None
    if burn_1h >= slo.critical_burn_rate:
        severity = "critical"
    elif burn_1h >= slo.warning_burn_rate:
        severity = "warning"

    # `alert_state` is a mutable {slo_name: last_severity} map the caller owns
    # and persists across polls, so we can tell a real state transition (e.g.
    # None->critical) apart from the same severity repeating on every poll of
    # an ongoing incident. When the caller doesn't pass one (e.g. existing
    # tests/callers), `prev` is always None so behaviour stays exactly as
    # before: alert on every poll where a threshold is crossed.
    prev = alert_state.get(slo.name) if alert_state is not None else None

    if severity is None:
        out["severity"] = None
        if alert_state is not None and prev is not None:
            # Recovered: burn dropped back under warning after having alerted.
            # Send one recovery notification; no AlertEvent, no correlation.
            notification = Notification(slo.name, slo.service, "resolved", burn_1h,
                                        budget, forecast_hours, "")
            await send(notification, webhook_url=notify_webhook_url,
                      slack_webhook_url=slack_webhook_url)
        if alert_state is not None:
            alert_state[slo.name] = severity
        return out

    out["severity"] = severity
    should_fire = severity != prev

    if should_fire:
        async with session_factory() as s:
            alert = AlertEvent(slo_name=slo.name, service=slo.service,
                               severity=severity, burn_rate=burn_1h, fired_at=now)
            s.add(alert)
            await s.commit()
            alert_id = alert.id

        changes = await event_store.recent_for_service(
            slo.service, now - timedelta(minutes=30), now + timedelta(minutes=5))
        corr = correlate(changes, now)
        out.update(probable_cause=corr.probable_cause,
                   probable_cause_type=corr.probable_cause_type, alerted=True)

        async with session_factory() as s:
            for e in corr.events[:3]:
                s.add(CorrelationEvent(alert_event_id=alert_id, event_time=e["time"],
                                       event_type=e["type"], source_system=e["source"],
                                       description=e["description"], score=e["final_score"]))
            await s.commit()

        notification = Notification(slo.name, slo.service, severity, burn_1h, budget,
                                    forecast_hours, corr.probable_cause)
        await send(notification, webhook_url=notify_webhook_url,
                  slack_webhook_url=slack_webhook_url)

        if severity == "critical" and postmortem_dir:
            md = render_postmortem(slo.name, slo.service, severity, burn_1h, budget,
                                   forecast_hours, corr)
            write_postmortem(md, postmortem_dir, slo.name, now)

    if alert_state is not None:
        alert_state[slo.name] = severity

    return out


async def _instant(source, promql: str) -> float | None:
    try:
        return await source.query_instant(promql)
    except Exception:  # noqa: BLE001
        return None


def _prom_duration(seconds: int) -> str:
    """Format a whole number of seconds as a Prometheus duration string,
    using the coarsest unit that divides it evenly (e.g. 3600 -> "1h")."""
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def run_scheduler(slos, job, poll_interval_seconds: int) -> AsyncIOScheduler:
    """Build an AsyncIOScheduler that runs `job(slo)` for each SLO on an interval.

    `job` is an async callable taking a single SLODefinition; the caller wires in
    the source/session/event_store/notification config it needs.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")
    for slo in slos:
        scheduler.add_job(
            job, "interval", seconds=poll_interval_seconds, args=[slo],
            id=f"eval:{slo.name}", max_instances=1, coalesce=True,
        )
    return scheduler
