import os
import re
from datetime import datetime


def render_postmortem(slo_name, service, severity, burn_rate,
                      budget_remaining_pct, forecast_hours, correlation) -> str:
    eta = f"~{forecast_hours:.1f} hours" if forecast_hours else "no clear exhaustion trend"
    lines = [
        f"# Postmortem: {slo_name}",
        "",
        f"- **Service:** {service}",
        f"- **Severity:** {severity}",
        f"- **Burn rate:** {burn_rate:.1f}x",
        f"- **Budget remaining:** {budget_remaining_pct:.1f}%",
        f"- **Forecast to exhaustion:** {eta}",
        "",
        "## Probable Cause",
        "",
        f"{correlation.probable_cause} (confidence {correlation.confidence:.0%})",
        "",
        "## Timeline",
        "",
    ]
    for e in correlation.events[:5]:
        lines.append(f"- {e['time']:%Y-%m-%d %H:%M} - {e['description']} "
                     f"(score {e['final_score']})")
    lines += ["", "## Impact", "", "_TODO: describe user impact._", "",
              "## Action Items", "", "- [ ] _TODO_", ""]
    return "\n".join(lines)


def write_postmortem(markdown: str, out_dir: str, slo_name: str, when: datetime) -> str:
    os.makedirs(out_dir, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", slo_name.lower()).strip("-")
    path = os.path.join(out_dir, f"{slug}-{when:%Y%m%d-%H%M}.md")
    with open(path, "w") as f:
        f.write(markdown)
    return path
