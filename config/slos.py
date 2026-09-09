from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class SLODefinition:
    name: str
    service: str
    target_percent: float
    window_days: int
    metric_query: str
    warning_burn_rate: float = 2.0
    critical_burn_rate: float = 10.0
    threshold_seconds: float | None = None


_REQUIRED = ("name", "service", "target_percent", "window_days", "metric_query")


def load_slos(path: str) -> list[SLODefinition]:
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    entries = raw.get("slos")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path}: no 'slos' list found")

    slos: list[SLODefinition] = []
    seen: set[str] = set()
    for i, e in enumerate(entries):
        for key in _REQUIRED:
            if key not in e or e[key] in (None, ""):
                raise ValueError(f"{path}: slo #{i} missing required key '{key}'")
        target = float(e["target_percent"])
        if not 0 < target <= 100:
            raise ValueError(f"{path}: slo '{e['name']}' target_percent must be in (0,100]")
        if e["name"] in seen:
            raise ValueError(f"{path}: duplicate slo name '{e['name']}'")
        seen.add(e["name"])
        thr = e.get("alert_thresholds") or {}
        slos.append(
            SLODefinition(
                name=e["name"],
                service=e["service"],
                target_percent=target,
                window_days=int(e["window_days"]),
                metric_query=e["metric_query"],
                warning_burn_rate=float(thr.get("warning_burn_rate", 2.0)),
                critical_burn_rate=float(thr.get("critical_burn_rate", 10.0)),
                threshold_seconds=(
                    float(e["threshold_seconds"]) if e.get("threshold_seconds") else None
                ),
            )
        )
    return slos
