import logging
from dataclasses import asdict, dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    slo_name: str
    service: str
    severity: str
    burn_rate: float
    budget_remaining_pct: float
    forecast_hours: float | None
    probable_cause: str


def _slack_text(n: Notification) -> str:
    eta = f"~{n.forecast_hours:.1f}h to exhaustion" if n.forecast_hours else "no exhaustion trend"
    return (
        f":rotating_light: *{n.severity.upper()}* SLO burn on *{n.slo_name}*\n"
        f"• burn rate: {n.burn_rate:.1f}x, budget remaining: {n.budget_remaining_pct:.1f}%\n"
        f"• forecast: {eta}\n"
        f"• probable cause: {n.probable_cause}"
    )


async def send(n: Notification, *, webhook_url: str | None, slack_webhook_url: str | None) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        if webhook_url:
            try:
                r = await client.post(webhook_url, json=asdict(n))
                r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                logger.warning("generic webhook failed: %s", e)
        if slack_webhook_url:
            try:
                r = await client.post(slack_webhook_url, json={"text": _slack_text(n)})
                r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                logger.warning("slack webhook failed: %s", e)
