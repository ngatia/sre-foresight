def compute_burn_rate(good_ratio: float, target_percent: float) -> float:
    allowed_error = 1.0 - (target_percent / 100.0)
    if allowed_error <= 0:
        return 0.0
    observed_error = max(0.0, 1.0 - good_ratio)
    return observed_error / allowed_error


def budget_remaining_pct(good_ratios: list[float], target_percent: float) -> float:
    budget = 1.0 - (target_percent / 100.0)
    if budget <= 0 or not good_ratios:
        return 100.0
    consumed = sum(max(0.0, 1.0 - g) for g in good_ratios) / len(good_ratios)
    remaining = 1.0 - (consumed / budget)
    return max(0.0, min(100.0, remaining * 100.0))
