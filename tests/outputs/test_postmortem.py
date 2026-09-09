from datetime import UTC, datetime

from correlate.correlator import CorrelationResult
from outputs.postmortem import render_postmortem, write_postmortem

CORR = CorrelationResult("Deploy resume v2 to prod", "deploy", 0.9, [])

def test_render_contains_key_sections():
    md = render_postmortem("Resume - Availability", "resume", "critical", 12.0, 8.0, 4.2, CORR)
    assert "# Postmortem" in md
    assert "Resume - Availability" in md
    assert "Probable Cause" in md
    assert "Deploy resume v2" in md
    assert "Timeline" in md

def test_write_creates_file(tmp_path):
    md = render_postmortem("Resume - Availability", "resume", "critical", 12.0, 8.0, 4.2, CORR)
    path = write_postmortem(md, str(tmp_path), "Resume - Availability",
                            datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    assert path.endswith("resume-availability-20260101-1200.md")
    with open(path) as f:
        assert "# Postmortem" in f.read()
