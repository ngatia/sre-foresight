from dataclasses import dataclass
from datetime import datetime

_MAX_DELTA_SECONDS = 2100.0  # 35 minutes
_DEPLOY_WEIGHT = 1.2
_MIN_CONFIDENCE = 0.4


@dataclass
class CorrelationResult:
    probable_cause: str
    probable_cause_type: str
    confidence: float
    events: list[dict]


def _proximity(event_time: datetime, spike_time: datetime) -> float:
    delta = abs((event_time - spike_time).total_seconds())
    return max(0.0, 1.0 - (delta / _MAX_DELTA_SECONDS))


def correlate(change_events, spike_time: datetime) -> CorrelationResult:
    scored: list[dict] = []
    for e in change_events:
        base = _proximity(e.occurred_at, spike_time)
        final = base * _DEPLOY_WEIGHT if e.event_type == "deploy" else base
        scored.append({
            "type": e.event_type,
            "source": e.source_system,
            "time": e.occurred_at,
            "description": e.description,
            "proximity_score": round(base, 3),
            "final_score": round(final, 3),
        })
    scored.sort(key=lambda x: x["final_score"], reverse=True)

    if scored and scored[0]["final_score"] >= _MIN_CONFIDENCE:
        top = scored[0]
        return CorrelationResult(
            probable_cause=top["description"],
            probable_cause_type=top["type"],
            confidence=min(top["final_score"], 1.0),
            events=scored,
        )
    return CorrelationResult(
        probable_cause="No correlated deployment or pipeline event found",
        probable_cause_type="unknown",
        confidence=0.0,
        events=scored,
    )
