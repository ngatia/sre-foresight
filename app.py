import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.main import create_app
from collectors.prometheus import PrometheusSource
from config.settings import get_settings
from config.slos import load_slos
from db.base import init_db, make_engine, make_session_factory
from events.base import ChangeEventStore
from scheduler import evaluate_slo, run_scheduler

logging.basicConfig(level=logging.INFO)


def build() -> FastAPI:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    slos = load_slos(settings.slo_config_path)
    source = PrometheusSource(settings.prometheus_url, settings.prometheus_token)
    event_store = ChangeEventStore(session_factory)
    latest_state: dict = {}

    async def _eval_and_record(slo):
        result = await evaluate_slo(
            slo, source, session_factory, event_store,
            notify_webhook_url=settings.notify_webhook_url,
            slack_webhook_url=settings.slack_webhook_url,
            postmortem_dir=settings.postmortem_dir,
        )
        latest_state[slo.name] = result

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db(engine)
        scheduler = run_scheduler(slos, source, session_factory, event_store, settings)
        # replace jobs with the state-recording wrapper
        scheduler.remove_all_jobs()
        for slo in slos:
            scheduler.add_job(_eval_and_record, "interval",
                              seconds=settings.poll_interval_seconds, args=[slo],
                              id=f"eval:{slo.name}", max_instances=1, coalesce=True)
        scheduler.start()
        app.state.scheduler = scheduler
        # prime one evaluation so the dashboard is not empty
        for slo in slos:
            asyncio.create_task(_eval_and_record(slo))
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)

    app = create_app(session_factory, event_store, slos, latest_state)
    app.router.lifespan_context = lifespan

    return app


app = build()
