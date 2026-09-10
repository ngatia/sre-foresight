import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.main import create_app
from collectors.prometheus import PrometheusSource
from config.settings import get_settings
from config.slos import load_slos
from db.base import init_db, make_engine, make_session_factory
from events import argocd, kubernetes
from events.base import ChangeEventStore
from scheduler import evaluate_slo, run_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _log_task_exc(task: asyncio.Task) -> None:
    """Done-callback that surfaces a background task's failure instead of
    letting it be silently swallowed."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("background task %r failed", task.get_name(), exc_info=exc)


def build() -> FastAPI:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    slos = load_slos(settings.slo_config_path)
    source = PrometheusSource(
        settings.prometheus_url,
        settings.prometheus_token,
        username=settings.prometheus_username,
        password=settings.prometheus_password,
    )
    event_store = ChangeEventStore(session_factory)
    latest_state: dict = {}
    # Per-SLO last-seen severity, shared across polls, so evaluate_slo can
    # alert on state transitions instead of on every poll that crosses a
    # threshold. Single-replica in-memory state: fine for this app's
    # single-scheduler deployment model, lost on restart (worst case: one
    # re-alert after a redeploy).
    alert_state: dict = {}

    async def _eval_and_record(slo):
        result = await evaluate_slo(
            slo, source, session_factory, event_store,
            notify_webhook_url=settings.notify_webhook_url,
            slack_webhook_url=settings.slack_webhook_url,
            postmortem_dir=settings.postmortem_dir,
            alert_state=alert_state,
        )
        latest_state[slo.name] = result

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db(engine)

        # Single clean scheduling path: the interval jobs run the state-recording
        # wrapper directly, no build-then-replace dance.
        scheduler = run_scheduler(slos, _eval_and_record, settings.poll_interval_seconds)
        scheduler.start()
        app.state.scheduler = scheduler

        background: list[asyncio.Task] = []

        # Prime one evaluation per SLO so the dashboard is not empty on startup.
        for slo in slos:
            t = asyncio.create_task(_eval_and_record(slo), name=f"prime:{slo.name}")
            t.add_done_callback(_log_task_exc)
            background.append(t)

        # Optional adapters (opt-in; default config leaves both off). Each is
        # wrapped so a failure is logged and never crashes startup.
        if settings.kubernetes_watch_enabled:
            async def _run_k8s_watch():
                try:
                    await kubernetes.watch_deployments(event_store, settings)
                except Exception:
                    logger.exception("kubernetes deployment watcher stopped")
            k8s_task = asyncio.create_task(_run_k8s_watch(), name="k8s-watch")
            k8s_task.add_done_callback(_log_task_exc)
            background.append(k8s_task)

        if settings.argocd_url and settings.argocd_token:
            async def _run_argocd_poll():
                try:
                    await argocd.poll_loop(
                        event_store, settings.argocd_url, settings.argocd_token,
                        interval_seconds=60, verify=not settings.argocd_insecure,
                    )
                except Exception:
                    logger.exception("argocd poll loop stopped")
            argo_task = asyncio.create_task(_run_argocd_poll(), name="argocd-poll")
            argo_task.add_done_callback(_log_task_exc)
            background.append(argo_task)

        app.state.background_tasks = background
        try:
            yield
        finally:
            for t in background:
                t.cancel()
            scheduler.shutdown(wait=False)

    app = create_app(session_factory, event_store, slos, latest_state)
    app.router.lifespan_context = lifespan

    return app


app = build()
