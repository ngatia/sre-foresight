"""Kubernetes deploy watcher -> ChangeEvent.

The pure mapper below is unit-tested. `watch_deployments` is thin glue over
kubernetes-asyncio; enable with KUBERNETES_WATCH_ENABLED=true and in-cluster RBAC
allowing watch on deployments. It is optional: the app works without it via the
generic /api/events webhook.
"""
from datetime import datetime, timezone

from events.base import ChangeEventInput


def deployment_to_change_event(obj: dict, service_label: str = "app") -> ChangeEventInput | None:
    meta = obj.get("metadata", {})
    gen = meta.get("generation")
    observed = obj.get("status", {}).get("observedGeneration")
    if gen is None or observed is None or gen <= observed:
        return None
    service = meta.get("labels", {}).get(service_label) or meta.get("name")
    revision = meta.get("annotations", {}).get("deployment.kubernetes.io/revision", "?")
    ns = meta.get("namespace", "default")
    return ChangeEventInput(
        service=service,
        event_type="deploy",
        source_system="kubernetes",
        description=f"Deploy {meta.get('name')} (rev {revision}) in {ns}",
        occurred_at=datetime.now(timezone.utc),
        metadata={"namespace": ns, "generation": gen, "revision": revision},
    )


async def watch_deployments(store, settings) -> None:  # pragma: no cover - live glue
    from kubernetes_asyncio import client, config, watch

    try:
        config.load_incluster_config()
    except Exception:
        await config.load_kube_config()
    api = client.AppsV1Api()
    w = watch.Watch()
    async with w.stream(api.list_deployment_for_all_namespaces) as stream:
        async for event in stream:
            obj = event["raw_object"]
            change = deployment_to_change_event(obj)
            if change:
                await store.record(change)
