"""Mock Prometheus for the demo.

Serves a synthetic "fraction good" ratio that degrades over real time once a
burn is injected (or from process start), so the app's error budget declines
gradually and the exhaustion forecaster produces a real cone, then the burn
rate climbs past the critical threshold to fire an alert. The whole arc is
time-compressed (about 2.5 minutes) so `make demo` shows the headline
behaviour quickly; it is not meant to be physically realistic.
"""
import time
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI

app = FastAPI()

# target_percent of the demo SLO; allowed error budget = 1 - target.
_TARGET = 0.99
_ALLOWED_ERROR = 1.0 - _TARGET  # 0.01

# Phase durations (seconds), time-compressed for the demo.
_DECLINE_SECONDS = 90.0   # budget 95% -> 0% (the forecast cone renders here)
_ESCALATE_SECONDS = 60.0  # burn rate climbs 1x -> ~12x (the alert fires here)

STATE = {"burn_at": time.monotonic()}


def _good_ratio(elapsed: float) -> float:
    """Fraction-good for a given elapsed time since the burn started."""
    if elapsed < _DECLINE_SECONDS:
        # Budget declines linearly 95% -> 0%.
        budget_frac = 0.95 * (1.0 - elapsed / _DECLINE_SECONDS)
        consumed = (1.0 - budget_frac) * _ALLOWED_ERROR
        return 1.0 - consumed
    if elapsed < _DECLINE_SECONDS + _ESCALATE_SECONDS:
        # Budget is spent; push the error rate up so burn crosses critical.
        frac = (elapsed - _DECLINE_SECONDS) / _ESCALATE_SECONDS
        return _TARGET - 0.11 * frac  # 0.99 -> 0.88 (burn ~1x -> ~12x)
    return 0.88


def _current_good() -> float:
    return round(_good_ratio(time.monotonic() - STATE["burn_at"]), 5)


@app.post("/inject/burn")
def inject_burn(good: float | None = None):
    """(Re)start the degradation arc from now. `good` is accepted for
    backward compatibility with the injector but ignored."""
    STATE["burn_at"] = time.monotonic()
    return {"restarted": True}


@app.get("/api/v1/query")
def query(query: str):
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": {}, "value": [datetime.now(UTC).timestamp(), str(_current_good())]}
            ],
        },
    }


@app.get("/api/v1/query_range")
def query_range(query: str, start: float, end: float, step: float):
    now = datetime.now(UTC)
    good = str(_current_good())
    vals = [[(now - timedelta(minutes=5 * i)).timestamp(), good] for i in range(12)]
    return {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [{"metric": {}, "values": list(reversed(vals))}],
        },
    }
