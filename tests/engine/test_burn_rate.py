from engine.burn_rate import budget_remaining_pct, compute_burn_rate


def test_burn_rate_at_target_is_one():
    # target 99% => allowed error 1%. observed error 1% => burn rate 1.0
    assert abs(compute_burn_rate(good_ratio=0.99, target_percent=99.0) - 1.0) < 1e-9

def test_burn_rate_ten_x():
    # observed error 10% vs allowed 1% => 10x
    assert abs(compute_burn_rate(good_ratio=0.90, target_percent=99.0) - 10.0) < 1e-9

def test_burn_rate_perfect_is_zero():
    assert compute_burn_rate(good_ratio=1.0, target_percent=99.0) == 0.0

def test_budget_full_when_no_errors():
    assert budget_remaining_pct([1.0, 1.0, 1.0], 99.0) == 100.0

def test_budget_half_consumed():
    # allowed error 1%; observed mean error 0.5% => half budget consumed => 50%
    assert abs(budget_remaining_pct([0.995, 0.995], 99.0) - 50.0) < 1e-6

def test_budget_clamps_at_zero():
    assert budget_remaining_pct([0.5], 99.0) == 0.0
