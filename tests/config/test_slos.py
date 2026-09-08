import pytest

from config.slos import SLODefinition, load_slos

FIX = "tests/config/fixtures/slos_valid.yaml"

def test_loads_valid():
    slos = load_slos(FIX)
    assert len(slos) == 1
    s = slos[0]
    assert isinstance(s, SLODefinition)
    assert s.name == "Resume - Availability"
    assert s.target_percent == 99.0
    assert s.critical_burn_rate == 10.0

def test_missing_query_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "slos:\n  - name: x\n    service: x\n    target_percent: 99\n    window_days: 30\n"
    )
    with pytest.raises(ValueError, match="metric_query"):
        load_slos(str(p))

def test_duplicate_name_raises(tmp_path):
    p = tmp_path / "dup.yaml"
    p.write_text(
        "slos:\n"
        + 2 * ("  - name: dup\n    service: s\n    target_percent: 99\n"
               "    window_days: 30\n    metric_query: q\n")
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_slos(str(p))
