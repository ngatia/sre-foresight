import logging
from datetime import UTC, datetime

import httpx

from collectors.base import MetricsSource

logger = logging.getLogger(__name__)


class PrometheusSource(MetricsSource):
    def __init__(
        self,
        url: str,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 10.0,
    ):
        self._url = url.rstrip("/")
        self._timeout = timeout

        self._auth: httpx.BasicAuth | None = None
        self._headers: dict[str, str] = {}
        if username and password:
            if token:
                logger.debug(
                    "PROMETHEUS_TOKEN is set but basic-auth credentials take "
                    "precedence; the bearer token will not be sent"
                )
            self._auth = httpx.BasicAuth(username, password)
        elif token:
            self._headers = {"Authorization": f"Bearer {token}"}

    def _client_kwargs(self) -> dict:
        kwargs: dict = {"timeout": self._timeout, "headers": self._headers}
        if self._auth is not None:
            kwargs["auth"] = self._auth
        return kwargs

    async def query_instant(self, promql: str) -> float | None:
        async with httpx.AsyncClient(**self._client_kwargs()) as client:
            r = await client.get(
                f"{self._url}/api/v1/query",
                params={"query": promql},
            )
            r.raise_for_status()
            result = r.json()["data"]["result"]
            if not result:
                return None
            return float(result[0]["value"][1])

    async def query_range(
        self, promql: str, start: datetime, end: datetime, step_seconds: int
    ) -> list[tuple[datetime, float]]:
        async with httpx.AsyncClient(**self._client_kwargs()) as client:
            r = await client.get(
                f"{self._url}/api/v1/query_range",
                params={
                    "query": promql,
                    "start": start.timestamp(),
                    "end": end.timestamp(),
                    "step": step_seconds,
                },
            )
            r.raise_for_status()
            result = r.json()["data"]["result"]
            if not result:
                return []
            return [
                (datetime.fromtimestamp(float(ts), tz=UTC), float(v))
                for ts, v in result[0]["values"]
            ]
