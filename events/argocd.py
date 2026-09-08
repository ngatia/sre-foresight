"""Optional ArgoCD adapter: synced applications -> deploy ChangeEvents."""
from datetime import datetime, timezone

import httpx

from events.base import ChangeEventInput


def argocd_app_to_change_event(app: dict) -> ChangeEventInput | None:
    status = app.get("status", {})
    op = status.get("operationState", {})
    if op.get("phase") != "Succeeded":
        return None
    name = app.get("metadata", {}).get("name", "unknown")
    revision = op.get("operation", {}).get("sync", {}).get("revision", "")
    finished = op.get("finishedAt")
    occurred = datetime.fromisoformat(finished.replace("Z", "+00:00")) if finished else datetime.now(timezone.utc)
    return ChangeEventInput(
        service=name,
        event_type="deploy",
        source_system="argocd",
        description=f"ArgoCD synced {name} to {revision[:7]}",
        occurred_at=occurred,
        metadata={"revision": revision},
    )


async def fetch_recent_deploys(argocd_url: str, token: str, since: datetime, *, verify: bool | str = True) -> list[ChangeEventInput]:  # pragma: no cover - live glue
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=10.0, verify=verify) as client:
        r = await client.get(f"{argocd_url.rstrip('/')}/api/v1/applications", headers=headers)
        r.raise_for_status()
        apps = r.json().get("items", [])
    events = [argocd_app_to_change_event(a) for a in apps]
    return [e for e in events if e and e.occurred_at >= since]
