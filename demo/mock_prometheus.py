"""Mock Prometheus for the demo: serves a good-ratio that drops after a burn is injected."""
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI

app = FastAPI()
STATE = {"good": 0.999}


@app.post("/inject/burn")
def inject_burn(good: float = 0.80):
    STATE["good"] = good
    return {"good": STATE["good"]}


@app.get("/api/v1/query")
def query(query: str):
    return {"status": "success", "data": {"resultType": "vector",
            "result": [{"metric": {}, "value": [datetime.now(timezone.utc).timestamp(),
                                                 str(STATE["good"])]}]}}


@app.get("/api/v1/query_range")
def query_range(query: str, start: float, end: float, step: float):
    now = datetime.now(timezone.utc)
    vals = [[(now - timedelta(minutes=5*i)).timestamp(), str(STATE["good"])] for i in range(12)]
    return {"status": "success", "data": {"resultType": "matrix",
            "result": [{"metric": {}, "values": list(reversed(vals))}]}}
