from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class MetricsSource(Protocol):
    async def query_instant(self, promql: str) -> float | None: ...

    async def query_range(
        self, promql: str, start: datetime, end: datetime, step_seconds: int
    ) -> list[tuple[datetime, float]]: ...
