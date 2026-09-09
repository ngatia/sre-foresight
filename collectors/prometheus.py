from datetime import UTC, datetime

import httpx

from collectors.base import MetricsSource


class PrometheusSource(MetricsSource):
    def __init__(self, url: str, token: str | None = None, timeout: float = 10.0):
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._timeout = timeout

    async def query_instant(self, promql: str) -> float | None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(
                f"{self._url}/api/v1/query",
                params={"query": promql},
                headers=self._headers,
            )
            r.raise_for_status()
            result = r.json()["data"]["result"]
            if not result:
                return None
            return float(result[0]["value"][1])

    async def query_range(
        self, promql: str, start: datetime, end: datetime, step_seconds: int
    ) -> list[tuple[datetime, float]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(
                f"{self._url}/api/v1/query_range",
                params={
                    "query": promql,
                    "start": start.timestamp(),
                    "end": end.timestamp(),
                    "step": step_seconds,
                },
                headers=self._headers,
            )
            r.raise_for_status()
            result = r.json()["data"]["result"]
            if not result:
                return []
            return [
                (datetime.fromtimestamp(float(ts), tz=UTC), float(v))
                for ts, v in result[0]["values"]
            ]
