from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from correlate.correlator import CorrelationResult, correlate


def _evt(service, etype, source, desc, occurred_at):
    return SimpleNamespace(service=service, event_type=etype, source_system=source,
                           description=desc, occurred_at=occurred_at)

def test_closest_deploy_wins():
    spike = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    near = _evt("resume", "deploy", "argocd", "deploy resume v2", spike - timedelta(minutes=2))
    far = _evt("resume", "pipeline", "gha", "ci run", spike - timedelta(minutes=25))
    res = correlate([far, near], spike)
    assert res.probable_cause_type == "deploy"
    assert "resume v2" in res.probable_cause
    assert res.confidence > 0.4

def test_deploy_beats_equidistant_pipeline():
    spike = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    dep = _evt("s", "deploy", "argocd", "deploy", spike - timedelta(minutes=10))
    pipe = _evt("s", "pipeline", "gha", "pipeline", spike - timedelta(minutes=10))
    res = correlate([pipe, dep], spike)
    assert res.probable_cause_type == "deploy"  # 1.2x weighting breaks the tie

def test_nothing_close_is_unknown():
    spike = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    far = _evt("s", "deploy", "argocd", "deploy", spike - timedelta(hours=2))
    res = correlate([far], spike)
    assert res.probable_cause_type == "unknown"
    assert res.confidence == 0.0

def test_empty_is_unknown():
    res = correlate([], datetime.now(UTC))
    assert isinstance(res, CorrelationResult)
    assert res.probable_cause_type == "unknown"
