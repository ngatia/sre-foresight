import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import ChangeEvent


@dataclass
class ChangeEventInput:
    """A deploy/pipeline occurrence.

    Canonical webhook JSON:
      {"service", "event_type": "deploy"|"pipeline", "source",
       "description", "timestamp": ISO8601, "metadata": {}}
    """
    service: str
    event_type: str
    source_system: str
    description: str
    occurred_at: datetime
    metadata: dict | None = None


class ChangeEventStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._sf = session_factory

    async def record(self, e: ChangeEventInput) -> int:
        async with self._sf() as s:
            row = ChangeEvent(
                service=e.service,
                event_type=e.event_type,
                source_system=e.source_system,
                description=e.description,
                occurred_at=e.occurred_at,
                metadata_json=json.dumps(e.metadata) if e.metadata else None,
            )
            s.add(row)
            await s.commit()
            return row.id

    async def recent_for_service(
        self, service: str, start: datetime, end: datetime
    ) -> list[ChangeEvent]:
        async with self._sf() as s:
            stmt = (
                select(ChangeEvent)
                .where(ChangeEvent.service == service)
                .where(ChangeEvent.occurred_at >= start)
                .where(ChangeEvent.occurred_at <= end)
                .order_by(ChangeEvent.occurred_at.desc())
            )
            return list((await s.execute(stmt)).scalars().all())
