"""Exhaustion forecaster: predict when the error budget hits zero.

Fits linear regression and exponential decay to recent budget-remaining
history, selecting the model with the better R^2. CI from the linear
standard error / the exponential covariance.
"""
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from scipy import stats
from scipy.optimize import curve_fit

logger = logging.getLogger(__name__)


@dataclass
class ExhaustionForecast:
    point_estimate_hours: float | None
    lower_ci_hours: float | None
    upper_ci_hours: float | None
    model_used: str
    confidence_score: float
    forecasted_at: datetime
    sample_count: int


class ExhaustionForecaster:
    @staticmethod
    def forecast(samples) -> ExhaustionForecast | None:
        if len(samples) < 3:
            return None

        ordered = sorted(samples, key=lambda s: s.sampled_at)
        t0 = ordered[0].sampled_at
        times = np.array([(s.sampled_at - t0).total_seconds() / 3600.0 for s in ordered])
        budgets = np.array([s.budget_remaining_pct for s in ordered])

        if budgets[-1] >= budgets[0]:
            return ExhaustionForecast(None, None, None, "none", 0.0,
                                      datetime.now(UTC), len(samples))

        linear = ExhaustionForecaster._fit_linear(times, budgets)
        expo = ExhaustionForecaster._fit_exponential(times, budgets)

        if linear and expo:
            selected, name = ((linear, "linear") if linear["r2"] >= expo["r2"]
                              else (expo, "exponential"))
        elif linear:
            selected, name = linear, "linear"
        elif expo:
            selected, name = expo, "exponential"
        else:
            return None

        return ExhaustionForecast(
            point_estimate_hours=selected["hours_to_zero"],
            lower_ci_hours=selected["lower_ci"],
            upper_ci_hours=selected["upper_ci"],
            model_used=name,
            confidence_score=selected["r2"],
            forecasted_at=datetime.now(UTC),
            sample_count=len(samples),
        )

    @staticmethod
    def _fit_linear(times, budgets):
        try:
            slope, intercept, r, _, std_err = stats.linregress(times, budgets)
            if slope >= 0:
                return None
            hours_to_zero = -intercept / slope
            remaining = max(0.0, hours_to_zero - times[-1])
            ci = 1.96 * std_err * remaining
            return {"hours_to_zero": remaining, "r2": r ** 2,
                    "lower_ci": max(0.0, remaining - ci), "upper_ci": remaining + ci}
        except Exception as e:  # noqa: BLE001
            logger.error("linear fit failed: %s", e)
            return None

    @staticmethod
    def _fit_exponential(times, budgets):
        try:
            def exp_decay(t, a, lam, c):
                return a * np.exp(-lam * t) + c

            a0, lam0, c0 = budgets[0] - budgets[-1], 0.1, budgets[-1]
            params, cov = curve_fit(exp_decay, times, budgets, p0=[a0, lam0, c0], maxfev=10000)
            a, lam, c = params
            resid = budgets - exp_decay(times, a, lam, c)
            ss_res = np.sum(resid ** 2)
            ss_tot = np.sum((budgets - np.mean(budgets)) ** 2)
            r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
            if a + c <= 0 or lam <= 0:
                return None
            # Guard against np.log returning NaN: (-c/a) must be positive
            if -c / a <= 0:
                return None
            t_zero = -np.log(-c / a) / lam
            remaining = max(0.0, t_zero - times[-1])
            ci = 1.96 * float(np.sqrt(np.diag(cov))[1]) * remaining
            lower_ci = max(0.0, remaining - ci)
            upper_ci = remaining + ci
            # Verify finite values before returning
            if not (np.isfinite(remaining) and np.isfinite(lower_ci) and np.isfinite(upper_ci)):
                return None
            return {"hours_to_zero": remaining, "r2": r2,
                    "lower_ci": lower_ci, "upper_ci": upper_ci}
        except Exception as e:  # noqa: BLE001
            logger.error("exponential fit failed: %s", e)
            return None
