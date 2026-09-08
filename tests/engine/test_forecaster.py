from datetime import datetime, timezone, timedelta
from engine.forecaster import ExhaustionForecaster, ExhaustionForecast


def _samples(values, start=None, step_min=60):
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)

    class S:  # minimal stand-in with the two attributes the forecaster reads
        def __init__(self, v, t):
            self.budget_remaining_pct = v
            self.sampled_at = t

    return [S(v, start + timedelta(minutes=i * step_min)) for i, v in enumerate(values)]


def test_none_when_too_few():
    assert ExhaustionForecaster.forecast(_samples([90, 80])) is None


def test_flat_budget_no_exhaustion():
    fc = ExhaustionForecaster.forecast(_samples([90, 90, 90, 90]))
    assert fc.model_used == "none"
    assert fc.point_estimate_hours is None


def test_linear_decline_predicts_known_zero():
    # budget drops 10 pts/hour from 100; last sample at t=3h => 70 left => ~7h to zero
    fc = ExhaustionForecaster.forecast(_samples([100, 90, 80, 70]))
    assert fc.point_estimate_hours is not None
    assert 6.0 < fc.point_estimate_hours < 8.0
    assert fc.lower_ci_hours <= fc.point_estimate_hours <= fc.upper_ci_hours
    assert fc.confidence_score > 0.98  # near-perfect linear fit


def test_returns_forecast_type():
    fc = ExhaustionForecaster.forecast(_samples([100, 90, 80, 70]))
    assert isinstance(fc, ExhaustionForecast)
