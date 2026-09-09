import logging
import urllib.parse
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


def _mrkdwn_escape(s: str) -> str:
    """Escape Slack mrkdwn control characters. Order matters: & before < and >."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _redacted_target(url: str) -> str:
    """Return scheme://host[:port] only, dropping userinfo, path, and query.

    urlparse's netloc includes any `user:pass@` userinfo, which would leak
    basic-auth credentials into logs. Build the host from parsed.hostname
    instead, which never includes userinfo.
    """
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}"


def _log_webhook_failure(label: str, url: str, e: Exception) -> None:
    status_code = getattr(getattr(e, "response", None), "status_code", "n/a")
    logger.warning(
        "%s failed: type=%s status=%s target=%s",
        label,
        type(e).__name__,
        status_code,
        _redacted_target(url),
    )


def _slack_text(n: Notification) -> str:
    eta = f"~{n.forecast_hours:.1f}h to exhaustion" if n.forecast_hours else "no exhaustion trend"
    safe_severity = _mrkdwn_escape(n.severity)
    safe_slo_name = _mrkdwn_escape(n.slo_name)
    safe_cause = _mrkdwn_escape(n.probable_cause.replace("\r", "").replace("\n", ""))
    return (
        f":rotating_light: *{safe_severity.upper()}* SLO burn on *{safe_slo_name}*\n"
        f"• burn rate: {n.burn_rate:.1f}x, budget remaining: {n.budget_remaining_pct:.1f}%\n"
        f"• forecast: {eta}\n"
        f"• probable cause: {safe_cause}"
    )


async def send(n: Notification, *, webhook_url: str | None, slack_webhook_url: str | None) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        if webhook_url:
            try:
                r = await client.post(webhook_url, json=asdict(n))
                r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                _log_webhook_failure("generic webhook", webhook_url, e)
        if slack_webhook_url:
            try:
                r = await client.post(slack_webhook_url, json={"text": _slack_text(n)})
                r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                _log_webhook_failure("slack webhook", slack_webhook_url, e)
