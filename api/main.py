import os
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from db.models import AlertEvent, BurnRateSample
from events.base import ChangeEventInput

_DASHBOARD = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "index.html")


class EventIn(BaseModel):
    service: str
    event_type: str = Field(pattern="^(deploy|pipeline)$")
    source: str
    description: str
    timestamp: datetime
    metadata: dict | None = None


def create_app(session_factory, event_store, slos, latest_state: dict) -> FastAPI:
    app = FastAPI(title="SRE Foresight")

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/slos")
    async def get_slos():
        return list(latest_state.values())

    @app.get("/api/slos/{name}/history")
    async def history(name: str):
        async with session_factory() as s:
            rows = (await s.execute(
                select(BurnRateSample).where(BurnRateSample.slo_name == name)
                .order_by(BurnRateSample.sampled_at.desc()).limit(288)
            )).scalars().all()
        return [
            {"sampled_at": r.sampled_at.isoformat(),
             "budget_remaining_pct": r.budget_remaining_pct,
             "burn_rate_1h": r.burn_rate_1h} for r in reversed(rows)
        ]

    @app.get("/api/alerts")
    async def alerts():
        async with session_factory() as s:
            rows = (await s.execute(
                select(AlertEvent).order_by(AlertEvent.fired_at.desc()).limit(50)
            )).scalars().all()
        return [
            {"slo_name": r.slo_name, "service": r.service, "severity": r.severity,
             "burn_rate": r.burn_rate, "fired_at": r.fired_at.isoformat()} for r in rows
        ]

    @app.post("/api/events", status_code=202)
    async def ingest(event: EventIn):
        await event_store.record(ChangeEventInput(
            service=event.service, event_type=event.event_type,
            source_system=event.source, description=event.description,
            occurred_at=event.timestamp, metadata=event.metadata,
        ))
        return {"accepted": True}

    @app.get("/")
    async def dashboard():
        if os.path.exists(_DASHBOARD):
            return FileResponse(_DASHBOARD)
        return JSONResponse({"detail": "dashboard not found"}, status_code=404)

    return app
