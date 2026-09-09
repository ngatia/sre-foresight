import math
from datetime import UTC, datetime, timedelta

from engine.forecaster import ExhaustionForecast, ExhaustionForecaster


def _samples(values, start=None, step_min=60):
    start = start or datetime(2026, 1, 1, tzinfo=UTC)

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


def test_exponential_decay_with_partial_self_healing():
    # Exponential decay pattern: [100, 70, 55, 48, 45]
    # This exhibits decay with diminishing rate of change (partial self-healing)
    # which is typical of exponential models vs linear
    fc = ExhaustionForecaster.forecast(_samples([100, 70, 55, 48, 45]))
    assert fc.point_estimate_hours is not None
    # Verify confidence interval bounds are properly ordered
    assert fc.lower_ci_hours <= fc.point_estimate_hours <= fc.upper_ci_hours
    # Verify point estimate is positive (budget exhaustion is in the future)
    assert fc.point_estimate_hours > 0


def test_declining_series_never_returns_degenerate_zero():
    # Regression test with real teeth. The exponential-decay pattern
    # [100, 70, 55, 48, 45] pre-fix produced a degenerate point_estimate of 0.0
    # ("already exhausted") even though the budget is still 45% - well above 0.
    # A plain isfinite() check does NOT catch that (0.0 is finite), so every
    # pattern here ends with budget well above 0 and we require the forecaster
    # to return EITHER None (no usable downward fit) OR a finite estimate
    # strictly > 0 - never a bogus 0.0.
    test_patterns = [
        [100, 90, 80, 70, 60],  # Linear
        [100, 70, 55, 48, 45],  # Exponential-like (the pre-fix 0.0 offender)
        [100, 50, 30, 20, 15],  # Steep then plateau
        [100, 95, 85, 70, 50],  # Variable decline
    ]
    for pattern in test_patterns:
        fc = ExhaustionForecaster.forecast(_samples(pattern))
        # Forecast should be returned (not None) for a clearly declining series.
        assert fc is not None, f"forecast() returned None for pattern {pattern}"
        if fc.point_estimate_hours is not None:
            # Finite (no NaN/inf) AND not the degenerate already-exhausted 0.0.
            assert math.isfinite(fc.point_estimate_hours) and fc.point_estimate_hours > 0, \
                f"bogus point_estimate {fc.point_estimate_hours} for pattern {pattern}"
            assert math.isfinite(fc.lower_ci_hours), \
                f"lower_ci_hours is NaN for pattern {pattern}"
            assert math.isfinite(fc.upper_ci_hours), \
                f"upper_ci_hours is NaN for pattern {pattern}"
