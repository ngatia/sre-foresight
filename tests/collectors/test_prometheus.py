import respx
from datetime import datetime, timezone, timedelta
from httpx import Response
from collectors.prometheus import PrometheusSource

BASE = "http://prom:9090"

@respx.mock
async def test_query_instant_returns_scalar_value():
    respx.get(f"{BASE}/api/v1/query").mock(return_value=Response(200, json={
        "status": "success",
        "data": {"resultType": "vector", "result": [
            {"metric": {}, "value": [1700000000, "0.995"]}
        ]},
    }))
    src = PrometheusSource(BASE)
    val = await src.query_instant("up")
    assert abs(val - 0.995) < 1e-9

@respx.mock
async def test_query_instant_empty_is_none():
    respx.get(f"{BASE}/api/v1/query").mock(return_value=Response(200, json={
        "status": "success", "data": {"resultType": "vector", "result": []},
    }))
    src = PrometheusSource(BASE)
    assert await src.query_instant("up") is None

@respx.mock
async def test_query_range_parses_pairs():
    respx.get(f"{BASE}/api/v1/query_range").mock(return_value=Response(200, json={
        "status": "success",
        "data": {"resultType": "matrix", "result": [
            {"metric": {}, "values": [[1700000000, "0.99"], [1700000060, "0.98"]]}
        ]},
    }))
    src = PrometheusSource(BASE)
    now = datetime.now(timezone.utc)
    pairs = await src.query_range("up", now - timedelta(minutes=5), now, 60)
    assert [v for _, v in pairs] == [0.99, 0.98]
    assert all(ts.tzinfo is not None for ts, _ in pairs)
