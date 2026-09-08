# SRE Foresight v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Revive SRE Foresight as a public, self-deployable tool that forecasts SLO error-budget exhaustion and correlates burn-rate spikes to the change that caused them, reading any Prometheus-compatible metrics source.

**Architecture:** A single FastAPI process runs a 60-second APScheduler loop. Each tick reads each SLO's SLI via PromQL, computes multi-window burn rate and budget-remaining, persists a time-ordered sample, fits an exhaustion forecast, and on threshold breach raises an alert, correlates it against recent Change Events (from a Kubernetes watcher, an inbound webhook, or optional adapters), sends a notification, and optionally drafts a postmortem. A read-only REST API + a static Chart.js dashboard render the results. State is SQLite by default, Postgres optionally. SLOs are declared in YAML.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async (aiosqlite / asyncpg), APScheduler, httpx, numpy, scipy, pydantic-settings, PyYAML, pytest + pytest-asyncio, respx (HTTP mocking), ruff. Distribution: Docker (multi-arch), docker-compose, Helm. CI: GitHub Actions.

**Spec:** This repo's `CONTEXT.md` (glossary) and `docs/adr/0001..0003` (design decisions). Reference implementation to port from: the old private repo `github.com/ngatia/sre-foresight` (branches `main`/`dev`) - clone read-only into a scratch dir; the crown-jewel files are `engine/forecaster.py`, `engine/correlator.py`, `engine/burn_rate.py`, `collectors/prometheus.py`, `config/slos.yaml`, `dashboard/index.html`. All code needed to execute is embedded below; the reference is a cross-check, not a dependency.

## Global Constraints

- **Python 3.12**; async throughout (no sync DB or HTTP in the request/scheduler path).
- **Metrics input is PromQL only** (ADR 0001). No CloudWatch/Grafana-API code in core.
- **State: SQLite default, Postgres optional** via `DATABASE_URL` (ADR 0002). Schema and queries must run on both. Never use engine-specific SQL.
- **SLOs are declared in YAML; API/dashboard are read-only over them** (ADR 0003).
- **No built-in auth**; bind `0.0.0.0` inside the container but document "put it behind your own ingress." Never add an internet-facing mutating endpoint without a token.
- **No secrets in the repo or in git history.** Config comes from env vars only. `.env` is git-ignored.
- **License headers not required**; Apache-2.0 covers the repo.
- **Container images build multi-arch** (`linux/amd64` + `linux/arm64`).
- **Test coverage target 80%+**; the forecasting and correlation logic must be unit-tested with synthetic fixtures where the correct answer is known by construction.
- **Every task ends green and committed.** Conventional-commit messages. Sign commits with the trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```
sre-foresight/
├── pyproject.toml                 # deps, ruff, pytest config
├── config/
│   ├── settings.py                # env-driven Settings (pydantic-settings)
│   ├── slos.py                    # SLODefinition + load_slos(yaml)
│   └── slos.example.yaml          # sample SLOs (ships in image)
├── db/
│   ├── base.py                    # async engine/session factory from DATABASE_URL
│   └── models.py                  # BurnRateSample, AlertEvent, ChangeEvent, CorrelationEvent
├── collectors/
│   ├── base.py                    # MetricsSource protocol
│   └── prometheus.py              # PrometheusSource (HTTP API)
├── engine/
│   ├── burn_rate.py               # burn rate + budget remaining
│   └── forecaster.py              # exhaustion forecast (linear + exp decay)
├── events/
│   ├── base.py                    # ChangeEvent domain type + ChangeEventStore
│   ├── kubernetes.py              # k8s Deployment/rollout watcher -> ChangeEvent
│   └── argocd.py                  # optional ArgoCD adapter
├── correlate/
│   └── correlator.py              # score ChangeEvents against a spike time
├── outputs/
│   ├── notify.py                  # generic webhook + Slack adapter
│   └── postmortem.py              # Markdown postmortem draft
├── scheduler.py                   # 60s evaluation loop
├── api/
│   └── main.py                    # FastAPI app: read-only API + webhook ingest + dashboard
├── dashboard/
│   └── index.html                 # vanilla JS + Chart.js
├── tests/
│   └── ... (mirrors modules)
├── Dockerfile
├── docker-compose.yml
├── Makefile                       # `make demo`, `make test`
├── demo/                          # mock Prometheus + burn/deploy injector
│   ├── mock_prometheus.py
│   └── inject.py
├── charts/sre-foresight/          # Helm chart
└── .github/workflows/ci.yml
```

---

### Task 1: Project tooling and dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `tests/__init__.py`, `tests/test_smoke.py`

**Interfaces:**
- Produces: a runnable `pytest` + `ruff` toolchain; import root is the repo root (flat package layout, modules imported as `config.settings`, `engine.forecaster`, etc.).

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "sre-foresight"
version = "0.1.0"
description = "Forecast SLO error-budget exhaustion and correlate burn spikes to their cause."
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0",
    "aiosqlite>=0.20",
    "asyncpg>=0.29",
    "greenlet>=3.0",
    "apscheduler>=3.10,<4",
    "httpx>=0.27",
    "numpy>=1.26",
    "scipy>=1.13",
    "pydantic-settings>=2.3",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
    "coverage>=7.5",
    "ruff>=0.5",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "-q"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 2: Write a smoke test** in `tests/test_smoke.py`

```python
def test_python_and_imports():
    import numpy, scipy, fastapi, sqlalchemy  # noqa: F401
    assert True
```

- [ ] **Step 3: Install and run**

Run: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`
Then: `pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/
git commit -m "chore: project tooling (pyproject, pytest, ruff)"
```

---

### Task 2: Settings from environment

**Files:**
- Create: `config/__init__.py` (empty), `config/settings.py`
- Test: `tests/config/test_settings.py`

**Interfaces:**
- Produces: `Settings` (pydantic-settings) and `get_settings() -> Settings`. Fields: `database_url: str` (default `sqlite+aiosqlite:///./data/foresight.db`), `prometheus_url: str`, `prometheus_token: str | None`, `slo_config_path: str` (default `config/slos.yaml`), `poll_interval_seconds: int` (default 60), `slack_webhook_url: str | None`, `notify_webhook_url: str | None`, `postmortem_dir: str | None`, `kubernetes_watch_enabled: bool` (default False), `argocd_url: str | None`, `argocd_token: str | None`.

- [ ] **Step 1: Write the failing test** in `tests/config/test_settings.py` (create `tests/config/__init__.py` too)

```python
from config.settings import Settings

def test_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom:9090")
    s = Settings()
    assert s.database_url.startswith("sqlite+aiosqlite")
    assert s.prometheus_url == "http://prom:9090"
    assert s.poll_interval_seconds == 60
    assert s.kubernetes_watch_enabled is False

def test_env_override(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom:9090")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "15")
    s = Settings()
    assert s.database_url.startswith("postgresql+asyncpg")
    assert s.poll_interval_seconds == 15
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/config/test_settings.py -v`
Expected: FAIL (`ModuleNotFoundError: config.settings`).

- [ ] **Step 3: Implement `config/settings.py`**

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./data/foresight.db"
    prometheus_url: str = "http://localhost:9090"
    prometheus_token: str | None = None
    slo_config_path: str = "config/slos.yaml"
    poll_interval_seconds: int = 60

    slack_webhook_url: str | None = None
    notify_webhook_url: str | None = None
    postmortem_dir: str | None = None

    kubernetes_watch_enabled: bool = False
    argocd_url: str | None = None
    argocd_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/config/test_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config/ tests/config/
git commit -m "feat: env-driven settings"
```

---

### Task 3: SLO definitions from YAML

**Files:**
- Create: `config/slos.py`, `config/slos.example.yaml`
- Test: `tests/config/test_slos.py`, `tests/config/fixtures/slos_valid.yaml`

**Interfaces:**
- Produces: frozen dataclass `SLODefinition(name: str, service: str, target_percent: float, window_days: int, metric_query: str, warning_burn_rate: float, critical_burn_rate: float, threshold_seconds: float | None = None)` and `load_slos(path: str) -> list[SLODefinition]`. `load_slos` raises `ValueError` with a clear message on a malformed file (missing required key, target not in (0,100], duplicate name).

- [ ] **Step 1: Write fixtures and failing tests**

`tests/config/fixtures/slos_valid.yaml`:

```yaml
slos:
  - name: "Resume - Availability"
    service: "resume"
    target_percent: 99.0
    window_days: 30
    metric_query: "avg_over_time(probe_success{instance='https://about.ngatia.me'}[5m])"
    alert_thresholds:
      warning_burn_rate: 2.0
      critical_burn_rate: 10.0
```

`tests/config/test_slos.py`:

```python
import pytest
from config.slos import load_slos, SLODefinition

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
    p.write_text("slos:\n  - name: x\n    service: x\n    target_percent: 99\n    window_days: 30\n")
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/config/test_slos.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `config/slos.py`**

```python
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
                threshold_seconds=(float(e["threshold_seconds"]) if e.get("threshold_seconds") else None),
            )
        )
    return slos
```

- [ ] **Step 4: Create `config/slos.example.yaml`** (ships in the image as a starting point)

```yaml
# Copy to config/slos.yaml and edit. Each SLI is a PromQL query returning a
# ratio in [0,1] for availability SLOs, or a value compared to threshold_seconds
# for latency SLOs.
slos:
  - name: "Example - Availability"
    service: "example"
    target_percent: 99.0
    window_days: 30
    metric_query: "avg_over_time(probe_success{instance='https://example.com'}[5m])"
    alert_thresholds:
      warning_burn_rate: 2.0
      critical_burn_rate: 10.0
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/config/test_slos.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add config/slos.py config/slos.example.yaml tests/config/
git commit -m "feat: declarative YAML SLO loader with validation"
```

---

### Task 4: Database engine, session, and models

**Files:**
- Create: `db/__init__.py`, `db/base.py`, `db/models.py`
- Test: `tests/db/test_models.py`

**Interfaces:**
- Produces:
  - `db/base.py`: `make_engine(url: str)`, `make_session_factory(engine)`, `Base` (DeclarativeBase), `init_db(engine)` (creates all tables).
  - `db/models.py`: `BurnRateSample(id, slo_name, service, budget_remaining_pct, burn_rate_1h, burn_rate_6h, sampled_at)`, `AlertEvent(id, slo_name, service, severity, burn_rate, fired_at)`, `ChangeEvent(id, service, event_type, source_system, description, occurred_at, metadata_json)`, `CorrelationEvent(id, alert_event_id, change_event_id, event_time, event_type, source_system, description, score)`. All timestamps timezone-aware UTC; use `DateTime(timezone=True)`.

- [ ] **Step 1: Write the failing test** (create `tests/db/__init__.py`)

```python
import pytest
from datetime import datetime, timezone
from db.base import make_engine, make_session_factory, init_db
from db.models import BurnRateSample

@pytest.fixture
async def session_factory():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    return make_session_factory(engine)

async def test_insert_and_read_sample(session_factory):
    async with session_factory() as s:
        s.add(BurnRateSample(
            slo_name="x", service="x", budget_remaining_pct=90.0,
            burn_rate_1h=1.0, burn_rate_6h=1.0,
            sampled_at=datetime.now(timezone.utc),
        ))
        await s.commit()
    async with session_factory() as s:
        from sqlalchemy import select
        rows = (await s.execute(select(BurnRateSample))).scalars().all()
        assert len(rows) == 1 and rows[0].budget_remaining_pct == 90.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/db/test_models.py -v`
Expected: FAIL (`ModuleNotFoundError: db.base`).

- [ ] **Step 3: Implement `db/base.py`**

```python
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, future=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 4: Implement `db/models.py`**

```python
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from db.base import Base


class BurnRateSample(Base):
    __tablename__ = "burn_rate_samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slo_name: Mapped[str] = mapped_column(String(255), index=True)
    service: Mapped[str] = mapped_column(String(255), index=True)
    budget_remaining_pct: Mapped[float] = mapped_column(Float)
    burn_rate_1h: Mapped[float] = mapped_column(Float)
    burn_rate_6h: Mapped[float] = mapped_column(Float)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slo_name: Mapped[str] = mapped_column(String(255), index=True)
    service: Mapped[str] = mapped_column(String(255), index=True)
    severity: Mapped[str] = mapped_column(String(32))
    burn_rate: Mapped[float] = mapped_column(Float)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ChangeEvent(Base):
    __tablename__ = "change_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service: Mapped[str] = mapped_column(String(255), index=True)
    event_type: Mapped[str] = mapped_column(String(32))  # "deploy" | "pipeline"
    source_system: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class CorrelationEvent(Base):
    __tablename__ = "correlation_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_event_id: Mapped[int] = mapped_column(ForeignKey("alert_events.id"), index=True)
    change_event_id: Mapped[int | None] = mapped_column(ForeignKey("change_events.id"), nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_type: Mapped[str] = mapped_column(String(32))
    source_system: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/db/test_models.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add db/ tests/db/
git commit -m "feat: async DB engine, session factory, and models"
```

---

### Task 5: Metrics source contract + Prometheus implementation

**Files:**
- Create: `collectors/__init__.py`, `collectors/base.py`, `collectors/prometheus.py`
- Test: `tests/collectors/test_prometheus.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `collectors/base.py`: `class MetricsSource(Protocol)` with `async def query_instant(self, promql: str) -> float | None` and `async def query_range(self, promql: str, start: datetime, end: datetime, step_seconds: int) -> list[tuple[datetime, float]]`.
  - `collectors/prometheus.py`: `PrometheusSource(url: str, token: str | None = None)` implementing the protocol against the Prometheus HTTP API (`/api/v1/query`, `/api/v1/query_range`). Returns `None` from `query_instant` when the query yields no series. Bearer token header when `token` is set.

- [ ] **Step 1: Write the failing test** (uses `respx` to mock Prometheus; create `tests/collectors/__init__.py`)

```python
import respx
from datetime import datetime, timezone, timedelta
from httpx import Response
from collectors.prometheus import PrometheusSource

BASE = "http://prom:9090"

@respx.mock
async def test_query_instant_returns_scalar_value():
    respx.get(f"{BASE}/api/v1/query").mock(return_value=Response(200, json={
        "status": "success",
        "data": {"resultType": "vector", "result": [
            {"metric": {}, "value": [1700000000, "0.995"]}
        ]},
    }))
    src = PrometheusSource(BASE)
    val = await src.query_instant("up")
    assert abs(val - 0.995) < 1e-9

@respx.mock
async def test_query_instant_empty_is_none():
    respx.get(f"{BASE}/api/v1/query").mock(return_value=Response(200, json={
        "status": "success", "data": {"resultType": "vector", "result": []},
    }))
    src = PrometheusSource(BASE)
    assert await src.query_instant("up") is None

@respx.mock
async def test_query_range_parses_pairs():
    respx.get(f"{BASE}/api/v1/query_range").mock(return_value=Response(200, json={
        "status": "success",
        "data": {"resultType": "matrix", "result": [
            {"metric": {}, "values": [[1700000000, "0.99"], [1700000060, "0.98"]]}
        ]},
    }))
    src = PrometheusSource(BASE)
    now = datetime.now(timezone.utc)
    pairs = await src.query_range("up", now - timedelta(minutes=5), now, 60)
    assert [v for _, v in pairs] == [0.99, 0.98]
    assert all(ts.tzinfo is not None for ts, _ in pairs)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/collectors/test_prometheus.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `collectors/base.py`**

```python
from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class MetricsSource(Protocol):
    async def query_instant(self, promql: str) -> float | None: ...

    async def query_range(
        self, promql: str, start: datetime, end: datetime, step_seconds: int
    ) -> list[tuple[datetime, float]]: ...
```

- [ ] **Step 4: Implement `collectors/prometheus.py`**

```python
from datetime import datetime, timezone
import httpx
from collectors.base import MetricsSource


class PrometheusSource(MetricsSource):
    def __init__(self, url: str, token: str | None = None, timeout: float = 10.0):
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._timeout = timeout

    async def query_instant(self, promql: str) -> float | None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(
                f"{self._url}/api/v1/query",
                params={"query": promql},
                headers=self._headers,
            )
            r.raise_for_status()
            result = r.json()["data"]["result"]
            if not result:
                return None
            return float(result[0]["value"][1])

    async def query_range(
        self, promql: str, start: datetime, end: datetime, step_seconds: int
    ) -> list[tuple[datetime, float]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(
                f"{self._url}/api/v1/query_range",
                params={
                    "query": promql,
                    "start": start.timestamp(),
                    "end": end.timestamp(),
                    "step": step_seconds,
                },
                headers=self._headers,
            )
            r.raise_for_status()
            result = r.json()["data"]["result"]
            if not result:
                return []
            return [
                (datetime.fromtimestamp(float(ts), tz=timezone.utc), float(v))
                for ts, v in result[0]["values"]
            ]
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/collectors/test_prometheus.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add collectors/ tests/collectors/
git commit -m "feat: MetricsSource contract + Prometheus HTTP implementation"
```

---

### Task 6: Burn-rate and budget-remaining engine

**Files:**
- Create: `engine/__init__.py`, `engine/burn_rate.py`
- Test: `tests/engine/test_burn_rate.py`

**Interfaces:**
- Consumes: `SLODefinition` (Task 3).
- Produces: `compute_burn_rate(good_ratio: float, target_percent: float) -> float` where burn rate = observed_error_rate / allowed_error_rate = `(1 - good_ratio) / (1 - target_percent/100)`; returns `0.0` when allowed error is 0. And `budget_remaining_pct(good_ratios: list[float], target_percent: float) -> float` = `100 * (1 - consumed/budget)` clamped to `[0, 100]`, where `consumed = mean(1 - good_ratio)` and `budget = 1 - target_percent/100`.

- [ ] **Step 1: Write the failing test** (create `tests/engine/__init__.py`)

```python
from engine.burn_rate import compute_burn_rate, budget_remaining_pct

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
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/engine/test_burn_rate.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `engine/burn_rate.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/engine/test_burn_rate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/burn_rate.py tests/engine/
git commit -m "feat: burn-rate and budget-remaining engine"
```

---

### Task 7: Exhaustion forecaster (the primary differentiator)

**Files:**
- Create: `engine/forecaster.py`
- Test: `tests/engine/test_forecaster.py`

**Interfaces:**
- Consumes: `BurnRateSample` (Task 4) - uses `.sampled_at` and `.budget_remaining_pct`.
- Produces: dataclass `ExhaustionForecast(point_estimate_hours: float | None, lower_ci_hours: float | None, upper_ci_hours: float | None, model_used: str, confidence_score: float, forecasted_at: datetime, sample_count: int)` and `ExhaustionForecaster.forecast(samples: list[BurnRateSample]) -> ExhaustionForecast | None`. Returns `None` for `< 3` samples; `model_used="none"` (all-`None` hours) when budget is flat or rising; otherwise fits linear (`scipy.stats.linregress`) and exponential decay (`scipy.optimize.curve_fit`), picks the higher R², and returns hours-from-now-to-zero with a 95% CI.

- [ ] **Step 1: Write the failing test** - synthetic series with a *known* answer

```python
from datetime import datetime, timezone, timedelta
from engine.forecaster import ExhaustionForecaster, ExhaustionForecast

def _samples(values, start=None, step_min=60):
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    class S:  # minimal stand-in with the two attributes the forecaster reads
        def __init__(self, v, t): self.budget_remaining_pct = v; self.sampled_at = t
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/engine/test_forecaster.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `engine/forecaster.py`** (ported from the reference `engine/forecaster.py`, imports adjusted; algorithm unchanged)

```python
"""Exhaustion forecaster: predict when the error budget hits zero.

Fits linear regression and exponential decay to recent budget-remaining
history, selecting the model with the better R^2. CI from the linear
standard error / the exponential covariance.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

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
                                      datetime.now(timezone.utc), len(samples))

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
            forecasted_at=datetime.now(timezone.utc),
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
            t_zero = -np.log(-c / a) / lam
            remaining = max(0.0, t_zero - times[-1])
            ci = 1.96 * float(np.sqrt(np.diag(cov))[1]) * remaining
            return {"hours_to_zero": remaining, "r2": r2,
                    "lower_ci": max(0.0, remaining - ci), "upper_ci": remaining + ci}
        except Exception as e:  # noqa: BLE001
            logger.error("exponential fit failed: %s", e)
            return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/engine/test_forecaster.py -v`
Expected: PASS (the linear series yields ~7h with R²≈1).

- [ ] **Step 5: Commit**

```bash
git add engine/forecaster.py tests/engine/test_forecaster.py
git commit -m "feat: exhaustion forecaster (linear + exponential, R2-selected)"
```

---

### Task 8: Change events - domain type, store, and webhook contract

**Files:**
- Create: `events/__init__.py`, `events/base.py`
- Test: `tests/events/test_store.py`

**Interfaces:**
- Consumes: `ChangeEvent` model + session factory (Task 4).
- Produces:
  - `events/base.py`: dataclass `ChangeEventInput(service: str, event_type: str, source_system: str, description: str, occurred_at: datetime, metadata: dict | None = None)` and `class ChangeEventStore` with `async record(self, e: ChangeEventInput) -> int` (returns row id) and `async recent_for_service(self, service: str, start: datetime, end: datetime) -> list[ChangeEvent]`.
  - The canonical webhook JSON contract (documented in the dataclass docstring): `{"service": str, "event_type": "deploy"|"pipeline", "source": str, "description": str, "timestamp": ISO8601, "metadata": {}}`.

- [ ] **Step 1: Write the failing test** (create `tests/events/__init__.py`)

```python
import pytest
from datetime import datetime, timezone, timedelta
from db.base import make_engine, make_session_factory, init_db
from events.base import ChangeEventStore, ChangeEventInput

@pytest.fixture
async def store():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    return ChangeEventStore(make_session_factory(engine))

async def test_record_and_query_window(store):
    now = datetime.now(timezone.utc)
    await store.record(ChangeEventInput("resume", "deploy", "argocd", "deploy resume", now))
    await store.record(ChangeEventInput("other", "deploy", "argocd", "deploy other", now))
    rows = await store.recent_for_service("resume", now - timedelta(minutes=5), now + timedelta(minutes=5))
    assert len(rows) == 1 and rows[0].service == "resume"

async def test_window_excludes_out_of_range(store):
    now = datetime.now(timezone.utc)
    await store.record(ChangeEventInput("resume", "deploy", "argocd", "old", now - timedelta(hours=2)))
    rows = await store.recent_for_service("resume", now - timedelta(minutes=5), now + timedelta(minutes=5))
    assert rows == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/events/test_store.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `events/base.py`**

```python
import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import ChangeEvent


@dataclass
class ChangeEventInput:
    """A deploy/pipeline occurrence.

    Canonical webhook JSON:
      {"service", "event_type": "deploy"|"pipeline", "source",
       "description", "timestamp": ISO8601, "metadata": {}}
    """
    service: str
    event_type: str
    source_system: str
    description: str
    occurred_at: datetime
    metadata: dict | None = None


class ChangeEventStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._sf = session_factory

    async def record(self, e: ChangeEventInput) -> int:
        async with self._sf() as s:
            row = ChangeEvent(
                service=e.service,
                event_type=e.event_type,
                source_system=e.source_system,
                description=e.description,
                occurred_at=e.occurred_at,
                metadata_json=json.dumps(e.metadata) if e.metadata else None,
            )
            s.add(row)
            await s.commit()
            return row.id

    async def recent_for_service(
        self, service: str, start: datetime, end: datetime
    ) -> list[ChangeEvent]:
        async with self._sf() as s:
            stmt = (
                select(ChangeEvent)
                .where(ChangeEvent.service == service)
                .where(ChangeEvent.occurred_at >= start)
                .where(ChangeEvent.occurred_at <= end)
                .order_by(ChangeEvent.occurred_at.desc())
            )
            return list((await s.execute(stmt)).scalars().all())
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/events/test_store.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add events/ tests/events/
git commit -m "feat: change-event domain type + store + webhook contract"
```

---

### Task 9: Correlator (the second differentiator)

**Files:**
- Create: `correlate/__init__.py`, `correlate/correlator.py`
- Test: `tests/correlate/test_correlator.py`

**Interfaces:**
- Consumes: `ChangeEvent` rows (Task 4/8).
- Produces: dataclass `CorrelationResult(probable_cause: str, probable_cause_type: str, confidence: float, events: list[dict])` and pure function `correlate(change_events: list[ChangeEvent], spike_time: datetime) -> CorrelationResult`. Scoring ported from the reference: proximity = `max(0, 1 - |Δt|/2100)`; `deploy` events multiplied by 1.2; top event with final score `>= 0.4` is the probable cause (confidence capped at 1.0), else `"unknown"` with confidence 0.0. This is a **pure function** (no DB, no network) so it is trivially testable; persistence is the scheduler's job.

- [ ] **Step 1: Write the failing test** (create `tests/correlate/__init__.py`)

```python
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from correlate.correlator import correlate, CorrelationResult

def _evt(service, etype, source, desc, occurred_at):
    return SimpleNamespace(service=service, event_type=etype, source_system=source,
                           description=desc, occurred_at=occurred_at)

def test_closest_deploy_wins():
    spike = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    near = _evt("resume", "deploy", "argocd", "deploy resume v2", spike - timedelta(minutes=2))
    far = _evt("resume", "pipeline", "gha", "ci run", spike - timedelta(minutes=25))
    res = correlate([far, near], spike)
    assert res.probable_cause_type == "deploy"
    assert "resume v2" in res.probable_cause
    assert res.confidence > 0.4

def test_deploy_beats_equidistant_pipeline():
    spike = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    dep = _evt("s", "deploy", "argocd", "deploy", spike - timedelta(minutes=10))
    pipe = _evt("s", "pipeline", "gha", "pipeline", spike - timedelta(minutes=10))
    res = correlate([pipe, dep], spike)
    assert res.probable_cause_type == "deploy"  # 1.2x weighting breaks the tie

def test_nothing_close_is_unknown():
    spike = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    far = _evt("s", "deploy", "argocd", "deploy", spike - timedelta(hours=2))
    res = correlate([far], spike)
    assert res.probable_cause_type == "unknown"
    assert res.confidence == 0.0

def test_empty_is_unknown():
    res = correlate([], datetime.now(timezone.utc))
    assert isinstance(res, CorrelationResult)
    assert res.probable_cause_type == "unknown"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/correlate/test_correlator.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `correlate/correlator.py`**

```python
from dataclasses import dataclass
from datetime import datetime

_MAX_DELTA_SECONDS = 2100.0  # 35 minutes
_DEPLOY_WEIGHT = 1.2
_MIN_CONFIDENCE = 0.4


@dataclass
class CorrelationResult:
    probable_cause: str
    probable_cause_type: str
    confidence: float
    events: list[dict]


def _proximity(event_time: datetime, spike_time: datetime) -> float:
    delta = abs((event_time - spike_time).total_seconds())
    return max(0.0, 1.0 - (delta / _MAX_DELTA_SECONDS))


def correlate(change_events, spike_time: datetime) -> CorrelationResult:
    scored: list[dict] = []
    for e in change_events:
        base = _proximity(e.occurred_at, spike_time)
        final = base * _DEPLOY_WEIGHT if e.event_type == "deploy" else base
        scored.append({
            "type": e.event_type,
            "source": e.source_system,
            "time": e.occurred_at,
            "description": e.description,
            "proximity_score": round(base, 3),
            "final_score": round(final, 3),
        })
    scored.sort(key=lambda x: x["final_score"], reverse=True)

    if scored and scored[0]["final_score"] >= _MIN_CONFIDENCE:
        top = scored[0]
        return CorrelationResult(
            probable_cause=top["description"],
            probable_cause_type=top["type"],
            confidence=min(top["final_score"], 1.0),
            events=scored,
        )
    return CorrelationResult(
        probable_cause="No correlated deployment or pipeline event found",
        probable_cause_type="unknown",
        confidence=0.0,
        events=scored,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/correlate/test_correlator.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add correlate/ tests/correlate/
git commit -m "feat: pure correlator with proximity scoring and deploy weighting"
```

---

### Task 10: Notifications (generic webhook + Slack adapter)

**Files:**
- Create: `outputs/__init__.py`, `outputs/notify.py`
- Test: `tests/outputs/test_notify.py`

**Interfaces:**
- Produces: dataclass `Notification(slo_name: str, service: str, severity: str, burn_rate: float, budget_remaining_pct: float, forecast_hours: float | None, probable_cause: str)` and `async def send(n: Notification, *, webhook_url: str | None, slack_webhook_url: str | None) -> None`. Posts the raw `Notification` as JSON to `webhook_url` and a formatted `{"text": ...}` block to `slack_webhook_url`; each is optional and failures are logged, never raised.

- [ ] **Step 1: Write the failing test** (create `tests/outputs/__init__.py`)

```python
import respx
from httpx import Response
from outputs.notify import Notification, send

N = Notification("Resume - Availability", "resume", "critical", 12.0, 8.0, 4.2,
                 "Deploy resume v2 to prod")

@respx.mock
async def test_posts_to_generic_webhook():
    route = respx.post("http://hook/generic").mock(return_value=Response(200))
    await send(N, webhook_url="http://hook/generic", slack_webhook_url=None)
    assert route.called
    body = route.calls.last.request.content.decode()
    assert "resume" in body and "critical" in body

@respx.mock
async def test_posts_slack_text():
    route = respx.post("http://hook/slack").mock(return_value=Response(200))
    await send(N, webhook_url=None, slack_webhook_url="http://hook/slack")
    assert route.called
    assert '"text"' in route.calls.last.request.content.decode()

@respx.mock
async def test_failure_does_not_raise():
    respx.post("http://hook/x").mock(return_value=Response(500))
    await send(N, webhook_url="http://hook/x", slack_webhook_url=None)  # no exception
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/outputs/test_notify.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `outputs/notify.py`**

```python
import logging
from dataclasses import asdict, dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    slo_name: str
    service: str
    severity: str
    burn_rate: float
    budget_remaining_pct: float
    forecast_hours: float | None
    probable_cause: str


def _slack_text(n: Notification) -> str:
    eta = f"~{n.forecast_hours:.1f}h to exhaustion" if n.forecast_hours else "no exhaustion trend"
    return (
        f":rotating_light: *{n.severity.upper()}* SLO burn on *{n.slo_name}*\n"
        f"• burn rate: {n.burn_rate:.1f}x, budget remaining: {n.budget_remaining_pct:.1f}%\n"
        f"• forecast: {eta}\n"
        f"• probable cause: {n.probable_cause}"
    )


async def send(n: Notification, *, webhook_url: str | None, slack_webhook_url: str | None) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        if webhook_url:
            try:
                r = await client.post(webhook_url, json=asdict(n))
                r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                logger.warning("generic webhook failed: %s", e)
        if slack_webhook_url:
            try:
                r = await client.post(slack_webhook_url, json={"text": _slack_text(n)})
                r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                logger.warning("slack webhook failed: %s", e)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/outputs/test_notify.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add outputs/notify.py tests/outputs/
git commit -m "feat: notifications (generic webhook + Slack adapter)"
```

---

### Task 11: Postmortem draft generator

**Files:**
- Create: `outputs/postmortem.py`
- Test: `tests/outputs/test_postmortem.py`

**Interfaces:**
- Consumes: `Notification` (Task 10) + `CorrelationResult` (Task 9).
- Produces: `render_postmortem(slo_name, service, severity, burn_rate, budget_remaining_pct, forecast_hours, correlation) -> str` (Markdown) and `write_postmortem(markdown: str, out_dir: str, slo_name: str, when: datetime) -> str` (writes `<out_dir>/<slug>-<YYYYMMDD-HHMM>.md`, returns the path).

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timezone
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
                            datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    assert path.endswith("resume-availability-20260101-1200.md")
    with open(path) as f:
        assert "# Postmortem" in f.read()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/outputs/test_postmortem.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `outputs/postmortem.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/outputs/test_postmortem.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add outputs/postmortem.py tests/outputs/test_postmortem.py
git commit -m "feat: Markdown postmortem draft generator"
```

---

### Task 12: Evaluation loop (wires the engine together)

**Files:**
- Create: `scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `MetricsSource` (Task 5), `SLODefinition` (Task 3), session factory + models (Task 4), `compute_burn_rate`/`budget_remaining_pct` (Task 6), `ExhaustionForecaster` (Task 7), `ChangeEventStore` (Task 8), `correlate` (Task 9), `send`/`Notification` (Task 10), postmortem (Task 11).
- Produces: `async def evaluate_slo(slo, source, session_factory, event_store, *, notify_webhook_url=None, slack_webhook_url=None, postmortem_dir=None) -> dict`. One evaluation: query the SLI over the last 60m at 5m step, compute per-window burn (1h, 6h) and budget-remaining over the SLO window, persist a `BurnRateSample`, forecast from recent samples, and if `burn_rate_1h >= warning/critical threshold` persist an `AlertEvent`, correlate against change events in `[spike-30m, spike+5m]`, persist `CorrelationEvent`s, send a notification, and (critical only, if `postmortem_dir`) write a postmortem. Returns a summary dict for the API/tests. Also `async def run_scheduler(...)` registering `evaluate_slo` for each SLO on the poll interval via APScheduler.

- [ ] **Step 1: Write the failing test** (fake source, in-memory DB, spy on notify via respx-free monkeypatch)

```python
import pytest
from datetime import datetime, timezone, timedelta
from db.base import make_engine, make_session_factory, init_db
from db.models import BurnRateSample, AlertEvent
from events.base import ChangeEventStore, ChangeEventInput
from config.slos import SLODefinition
import scheduler as sched
from sqlalchemy import select

class FakeSource:
    def __init__(self, good): self._good = good
    async def query_instant(self, q): return self._good
    async def query_range(self, q, start, end, step):
        n = 12
        return [(start + timedelta(minutes=5*i), self._good) for i in range(n)]

SLO = SLODefinition("Resume - Availability", "resume", 99.0, 30,
                    "q", warning_burn_rate=2.0, critical_burn_rate=10.0)

@pytest.fixture
async def db():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    return make_session_factory(engine)

async def test_healthy_slo_persists_sample_no_alert(db):
    store = ChangeEventStore(db)
    out = await sched.evaluate_slo(SLO, FakeSource(1.0), db, store)
    async with db() as s:
        samples = (await s.execute(select(BurnRateSample))).scalars().all()
        alerts = (await s.execute(select(AlertEvent))).scalars().all()
    assert len(samples) == 1
    assert out["budget_remaining_pct"] == 100.0
    assert alerts == []

async def test_burning_slo_fires_alert_and_correlates(db, monkeypatch):
    store = ChangeEventStore(db)
    spike = datetime.now(timezone.utc)
    await store.record(ChangeEventInput("resume", "deploy", "argocd",
                                        "deploy resume v2", spike - timedelta(minutes=2)))
    sent = {}
    async def fake_send(n, **kw): sent["n"] = n
    monkeypatch.setattr(sched, "send", fake_send)
    # good ratio 0.80 => error 20% vs allowed 1% => burn rate 20x (critical)
    out = await sched.evaluate_slo(SLO, FakeSource(0.80), db, store, slack_webhook_url="http://x")
    async with db() as s:
        alerts = (await s.execute(select(AlertEvent))).scalars().all()
    assert len(alerts) == 1 and alerts[0].severity == "critical"
    assert out["probable_cause_type"] == "deploy"
    assert "resume v2" in sent["n"].probable_cause
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_scheduler.py -v`
Expected: FAIL (`ModuleNotFoundError: scheduler`).

- [ ] **Step 3: Implement `scheduler.py`**

```python
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from collectors.base import MetricsSource
from config.slos import SLODefinition, load_slos
from correlate.correlator import correlate
from db.models import AlertEvent, BurnRateSample, CorrelationEvent
from engine.burn_rate import budget_remaining_pct, compute_burn_rate
from engine.forecaster import ExhaustionForecaster
from events.base import ChangeEventStore
from outputs.notify import Notification, send
from outputs.postmortem import render_postmortem, write_postmortem

logger = logging.getLogger(__name__)


async def evaluate_slo(
    slo: SLODefinition,
    source: MetricsSource,
    session_factory,
    event_store: ChangeEventStore,
    *,
    notify_webhook_url: str | None = None,
    slack_webhook_url: str | None = None,
    postmortem_dir: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    series_1h = await source.query_range(slo.metric_query, now - timedelta(hours=1), now, 300)
    good_1h = [v for _, v in series_1h] or [await _instant(source, slo)]
    good_1h = [g for g in good_1h if g is not None] or [1.0]

    latest_good = good_1h[-1]
    burn_1h = compute_burn_rate(sum(good_1h) / len(good_1h), slo.target_percent)
    series_6h = await source.query_range(slo.metric_query, now - timedelta(hours=6), now, 300)
    good_6h = [v for _, v in series_6h] or good_1h
    burn_6h = compute_burn_rate(sum(good_6h) / len(good_6h), slo.target_percent)
    budget = budget_remaining_pct(good_6h, slo.target_percent)

    async with session_factory() as s:
        s.add(BurnRateSample(slo_name=slo.name, service=slo.service,
                             budget_remaining_pct=budget, burn_rate_1h=burn_1h,
                             burn_rate_6h=burn_6h, sampled_at=now))
        await s.commit()
        recent = (await s.execute(
            select(BurnRateSample).where(BurnRateSample.slo_name == slo.name)
            .order_by(BurnRateSample.sampled_at.desc()).limit(24)
        )).scalars().all()

    forecast = ExhaustionForecaster.forecast(list(reversed(recent)))
    forecast_hours = forecast.point_estimate_hours if forecast else None

    out = {
        "slo": slo.name, "service": slo.service, "budget_remaining_pct": budget,
        "burn_rate_1h": burn_1h, "burn_rate_6h": burn_6h,
        "forecast_hours": forecast_hours, "latest_good": latest_good,
        "severity": None, "probable_cause": None, "probable_cause_type": None,
    }

    severity = None
    if burn_1h >= slo.critical_burn_rate:
        severity = "critical"
    elif burn_1h >= slo.warning_burn_rate:
        severity = "warning"
    if severity is None:
        return out

    async with session_factory() as s:
        alert = AlertEvent(slo_name=slo.name, service=slo.service,
                           severity=severity, burn_rate=burn_1h, fired_at=now)
        s.add(alert)
        await s.commit()
        alert_id = alert.id

    changes = await event_store.recent_for_service(
        slo.service, now - timedelta(minutes=30), now + timedelta(minutes=5))
    corr = correlate(changes, now)
    out.update(severity=severity, probable_cause=corr.probable_cause,
               probable_cause_type=corr.probable_cause_type)

    async with session_factory() as s:
        for e in corr.events[:3]:
            s.add(CorrelationEvent(alert_event_id=alert_id, event_time=e["time"],
                                   event_type=e["type"], source_system=e["source"],
                                   description=e["description"], score=e["final_score"]))
        await s.commit()

    notification = Notification(slo.name, slo.service, severity, burn_1h, budget,
                                forecast_hours, corr.probable_cause)
    await send(notification, webhook_url=notify_webhook_url, slack_webhook_url=slack_webhook_url)

    if severity == "critical" and postmortem_dir:
        md = render_postmortem(slo.name, slo.service, severity, burn_1h, budget,
                               forecast_hours, corr)
        write_postmortem(md, postmortem_dir, slo.name, now)

    return out


async def _instant(source, slo):
    try:
        return await source.query_instant(slo.metric_query)
    except Exception:  # noqa: BLE001
        return None


def run_scheduler(slos, source, session_factory, event_store, settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    for slo in slos:
        scheduler.add_job(
            evaluate_slo, "interval", seconds=settings.poll_interval_seconds,
            args=[slo, source, session_factory, event_store],
            kwargs=dict(notify_webhook_url=settings.notify_webhook_url,
                        slack_webhook_url=settings.slack_webhook_url,
                        postmortem_dir=settings.postmortem_dir),
            id=f"eval:{slo.name}", max_instances=1, coalesce=True,
        )
    return scheduler
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_scheduler.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat: SLO evaluation loop (sample, forecast, alert, correlate, notify)"
```

---

### Task 13: FastAPI app - read-only API, webhook ingest, dashboard, health

**Files:**
- Create: `api/__init__.py`, `api/main.py`
- Test: `tests/api/test_api.py`

**Interfaces:**
- Consumes: everything above via a small app-state container.
- Produces: `create_app(session_factory, event_store, slos, latest_state) -> FastAPI` with routes: `GET /api/health` -> `{"status":"ok"}`; `GET /api/slos` -> list of the latest evaluation dicts; `GET /api/slos/{name}/history` -> recent `BurnRateSample` rows as JSON; `GET /api/alerts` -> recent alerts; `POST /api/events` -> ingest a Change Event (validates the webhook contract, 202 on success, 422 on bad body); `GET /` -> serves `dashboard/index.html`. `latest_state` is a shared dict the scheduler updates and the API reads.

- [ ] **Step 1: Write the failing test** (create `tests/api/__init__.py`; use `httpx.ASGITransport`)

```python
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from db.base import make_engine, make_session_factory, init_db
from events.base import ChangeEventStore
from config.slos import SLODefinition
from api.main import create_app

SLO = SLODefinition("Resume - Availability", "resume", 99.0, 30, "q")

@pytest.fixture
async def client():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sf = make_session_factory(engine)
    state = {"Resume - Availability": {"slo": "Resume - Availability", "budget_remaining_pct": 100.0}}
    app = create_app(sf, ChangeEventStore(sf), [SLO], state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c

async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"

async def test_slos_returns_state(client):
    r = await client.get("/api/slos")
    assert r.status_code == 200
    assert r.json()[0]["slo"] == "Resume - Availability"

async def test_event_ingest_valid(client):
    r = await client.post("/api/events", json={
        "service": "resume", "event_type": "deploy", "source": "argocd",
        "description": "deploy v2", "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    assert r.status_code == 202

async def test_event_ingest_invalid(client):
    r = await client.post("/api/events", json={"service": "resume"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/api/test_api.py -v`
Expected: FAIL (`ModuleNotFoundError: api.main`).

- [ ] **Step 3: Implement `api/main.py`**

```python
import os
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from db.models import AlertEvent, BurnRateSample
from events.base import ChangeEventInput

_DASHBOARD = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "index.html")


class EventIn(BaseModel):
    service: str
    event_type: str = Field(pattern="^(deploy|pipeline)$")
    source: str
    description: str
    timestamp: datetime
    metadata: dict | None = None


def create_app(session_factory, event_store, slos, latest_state: dict) -> FastAPI:
    app = FastAPI(title="SRE Foresight")

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/slos")
    async def get_slos():
        return list(latest_state.values())

    @app.get("/api/slos/{name}/history")
    async def history(name: str):
        async with session_factory() as s:
            rows = (await s.execute(
                select(BurnRateSample).where(BurnRateSample.slo_name == name)
                .order_by(BurnRateSample.sampled_at.desc()).limit(288)
            )).scalars().all()
        return [
            {"sampled_at": r.sampled_at.isoformat(),
             "budget_remaining_pct": r.budget_remaining_pct,
             "burn_rate_1h": r.burn_rate_1h} for r in reversed(rows)
        ]

    @app.get("/api/alerts")
    async def alerts():
        async with session_factory() as s:
            rows = (await s.execute(
                select(AlertEvent).order_by(AlertEvent.fired_at.desc()).limit(50)
            )).scalars().all()
        return [
            {"slo_name": r.slo_name, "service": r.service, "severity": r.severity,
             "burn_rate": r.burn_rate, "fired_at": r.fired_at.isoformat()} for r in rows
        ]

    @app.post("/api/events", status_code=202)
    async def ingest(event: EventIn):
        await event_store.record(ChangeEventInput(
            service=event.service, event_type=event.event_type,
            source_system=event.source, description=event.description,
            occurred_at=event.timestamp, metadata=event.metadata,
        ))
        return {"accepted": True}

    @app.get("/")
    async def dashboard():
        if os.path.exists(_DASHBOARD):
            return FileResponse(_DASHBOARD)
        return JSONResponse({"detail": "dashboard not found"}, status_code=404)

    return app
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/api/test_api.py -v`
Expected: PASS (FastAPI returns 422 for the invalid body automatically).

- [ ] **Step 5: Commit**

```bash
git add api/ tests/api/
git commit -m "feat: read-only API + change-event webhook ingest + dashboard route"
```

---

### Task 14: Application entrypoint (compose settings + scheduler + API)

**Files:**
- Create: `app.py`
- Test: `tests/test_app_wiring.py`

**Interfaces:**
- Consumes: `get_settings`, `load_slos`, `PrometheusSource`, DB helpers, `ChangeEventStore`, `run_scheduler`, `create_app`.
- Produces: `build() -> FastAPI` that reads settings, inits the DB, loads SLOs, constructs the Prometheus source + event store + shared `latest_state`, wires a scheduler job that also updates `latest_state`, starts the scheduler on FastAPI startup, and returns the app. `uvicorn app:app` runs it.

- [ ] **Step 1: Write the failing test** (does not start uvicorn; only checks wiring with a temp SLO file + sqlite)

```python
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    slo = tmp_path / "slos.yaml"
    slo.write_text(
        "slos:\n  - name: X\n    service: x\n    target_percent: 99\n"
        "    window_days: 30\n    metric_query: up\n"
    )
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom:9090")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SLO_CONFIG_PATH", str(slo))
    from config.settings import get_settings
    get_settings.cache_clear()

async def test_app_builds_and_health_ok():
    import app as appmod
    application = appmod.build()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/health")
    assert r.status_code == 200
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_app_wiring.py -v`
Expected: FAIL (`ModuleNotFoundError: app`).

- [ ] **Step 3: Implement `app.py`**

```python
import asyncio
import logging

from fastapi import FastAPI

from api.main import create_app
from collectors.prometheus import PrometheusSource
from config.settings import get_settings
from config.slos import load_slos
from db.base import init_db, make_engine, make_session_factory
from events.base import ChangeEventStore
from scheduler import evaluate_slo, run_scheduler

logging.basicConfig(level=logging.INFO)


def build() -> FastAPI:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    slos = load_slos(settings.slo_config_path)
    source = PrometheusSource(settings.prometheus_url, settings.prometheus_token)
    event_store = ChangeEventStore(session_factory)
    latest_state: dict = {}

    app = create_app(session_factory, event_store, slos, latest_state)

    async def _eval_and_record(slo):
        result = await evaluate_slo(
            slo, source, session_factory, event_store,
            notify_webhook_url=settings.notify_webhook_url,
            slack_webhook_url=settings.slack_webhook_url,
            postmortem_dir=settings.postmortem_dir,
        )
        latest_state[slo.name] = result

    @app.on_event("startup")
    async def _startup():
        await init_db(engine)
        scheduler = run_scheduler(slos, source, session_factory, event_store, settings)
        # replace jobs with the state-recording wrapper
        scheduler.remove_all_jobs()
        for slo in slos:
            scheduler.add_job(_eval_and_record, "interval",
                              seconds=settings.poll_interval_seconds, args=[slo],
                              id=f"eval:{slo.name}", max_instances=1, coalesce=True)
        scheduler.start()
        app.state.scheduler = scheduler
        # prime one evaluation so the dashboard is not empty
        for slo in slos:
            asyncio.create_task(_eval_and_record(slo))

    return app


app = build()
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_app_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite + coverage gate**

Run: `coverage run -m pytest && coverage report --fail-under=80`
Expected: PASS, coverage >= 80%.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app_wiring.py
git commit -m "feat: application entrypoint wiring scheduler + API"
```

---

### Task 15: Dashboard (vanilla JS + Chart.js)

**Files:**
- Create: `dashboard/index.html`
- Test: manual (served by `GET /`); no unit test (static asset).

**Interfaces:**
- Consumes: `GET /api/slos`, `GET /api/slos/{name}/history`, `GET /api/alerts`.
- Produces: a single dark "mission-control" page: an SLO table (budget bar, 1h burn chip, forecast ETA), a forecast chart with the CI cone for the selected SLO, and an alerts/probable-cause feed. Chart.js from a pinned CDN. 30s auto-refresh.

- [ ] **Step 1: Create `dashboard/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>SRE Foresight</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.3/chart.umd.min.js"></script>
<style>
  :root { color-scheme: dark; }
  body { margin:0; background:#0b0f14; color:#e6edf3; font:14px system-ui,sans-serif; }
  header { padding:16px 24px; border-bottom:1px solid #1c2530; font-weight:600; font-size:18px; }
  main { display:grid; grid-template-columns:1fr 1fr; gap:16px; padding:24px; }
  .card { background:#111721; border:1px solid #1c2530; border-radius:10px; padding:16px; }
  table { width:100%; border-collapse:collapse; }
  th,td { text-align:left; padding:8px; border-bottom:1px solid #1c2530; }
  .bar { height:8px; background:#1c2530; border-radius:4px; overflow:hidden; }
  .bar>span { display:block; height:100%; background:#3fb950; }
  .chip { padding:2px 8px; border-radius:12px; font-size:12px; }
  .warn { background:#9e6a03; } .crit { background:#b62324; } .ok { background:#238636; }
  .full { grid-column:1 / -1; }
  .muted { color:#8b949e; }
</style>
</head>
<body>
<header>SRE Foresight - reliability foresight</header>
<main>
  <section class="card full">
    <h3>Service Level Objectives</h3>
    <table id="slo-table"><thead><tr>
      <th>SLO</th><th>Budget remaining</th><th>1h burn</th><th>Forecast</th>
    </tr></thead><tbody></tbody></table>
  </section>
  <section class="card">
    <h3>Forecast cone <span id="sel" class="muted"></span></h3>
    <canvas id="forecast"></canvas>
  </section>
  <section class="card">
    <h3>Alerts &amp; probable cause</h3>
    <div id="alerts"></div>
  </section>
</main>
<script>
let chart, selected = null;
function chip(sev){ return sev==='critical'?'crit':sev==='warning'?'warn':'ok'; }

async function refresh(){
  const slos = await (await fetch('/api/slos')).json();
  const tb = document.querySelector('#slo-table tbody'); tb.innerHTML='';
  for(const s of slos){
    if(!selected) selected = s.slo;
    const eta = s.forecast_hours ? `~${s.forecast_hours.toFixed(1)}h` : ' - ';
    const sev = s.severity||'ok';
    const tr = document.createElement('tr');
    tr.innerHTML =
      `<td><a href="#" data-slo="${s.slo}">${s.slo}</a></td>`+
      `<td><div class="bar"><span style="width:${(s.budget_remaining_pct||0).toFixed(0)}%"></span></div>`+
      `<small class="muted">${(s.budget_remaining_pct||0).toFixed(1)}%</small></td>`+
      `<td><span class="chip ${chip(sev)}">${(s.burn_rate_1h||0).toFixed(1)}x</span></td>`+
      `<td>${eta}</td>`;
    tb.appendChild(tr);
  }
  tb.querySelectorAll('a[data-slo]').forEach(a=>a.onclick=e=>{
    e.preventDefault(); selected=a.dataset.slo; drawForecast();
  });
  drawForecast(); drawAlerts();
}

async function drawForecast(){
  if(!selected) return;
  document.getElementById('sel').textContent = ' - '+selected;
  const hist = await (await fetch(`/api/slos/${encodeURIComponent(selected)}/history`)).json();
  const labels = hist.map(h=>h.sampled_at.slice(11,16));
  const data = hist.map(h=>h.budget_remaining_pct);
  if(chart) chart.destroy();
  chart = new Chart(document.getElementById('forecast'), {
    type:'line',
    data:{ labels, datasets:[{ label:'budget remaining %', data, borderColor:'#58a6ff',
      backgroundColor:'rgba(88,166,255,.15)', fill:true, tension:.25 }] },
    options:{ scales:{ y:{ min:0, max:100 } }, plugins:{ legend:{ display:false } } }
  });
}

async function drawAlerts(){
  const alerts = await (await fetch('/api/alerts')).json();
  document.getElementById('alerts').innerHTML = alerts.length ? alerts.map(a=>
    `<div><span class="chip ${chip(a.severity)}">${a.severity}</span> `+
    `<b>${a.slo_name}</b> - ${a.burn_rate.toFixed(1)}x `+
    `<span class="muted">${a.fired_at.slice(0,16).replace('T',' ')}</span></div>`
  ).join('') : '<span class="muted">No alerts.</span>';
}

refresh(); setInterval(refresh, 30000);
</script>
</body>
</html>
```

- [ ] **Step 2: Manual check**

Run: `uvicorn app:app` (with `PROMETHEUS_URL` set), open `http://localhost:8000`, confirm the table renders and `/api/health` returns ok.

- [ ] **Step 3: Commit**

```bash
git add dashboard/index.html
git commit -m "feat: dark mission-control dashboard (Chart.js)"
```

---

### Task 16: Container + docker-compose

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- Test: manual build + `docker compose up`.

**Interfaces:**
- Produces: a non-root image running `uvicorn app:app --host 0.0.0.0 --port 8000`; a compose file that runs the app with a mounted `config/slos.yaml` and a named volume for the SQLite DB.

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .
COPY . .
RUN useradd -u 10001 -m app && mkdir -p /app/data && chown -R app /app/data
USER app
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create `.dockerignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
tests/
docs/
data/
.git/
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
services:
  foresight:
    build: .
    image: ghcr.io/ngatia/sre-foresight:dev
    ports:
      - "8000:8000"
    environment:
      PROMETHEUS_URL: ${PROMETHEUS_URL:-http://prometheus:9090}
      DATABASE_URL: sqlite+aiosqlite:////app/data/foresight.db
      SLO_CONFIG_PATH: /app/config/slos.yaml
    volumes:
      - ./config/slos.yaml:/app/config/slos.yaml:ro
      - foresight-data:/app/data
volumes:
  foresight-data:
```

- [ ] **Step 4: Build + smoke**

Run: `docker build -t sre-foresight:test .` then `docker run --rm -e PROMETHEUS_URL=http://x sre-foresight:test python -c "import app"`.
Expected: import succeeds (startup DB init runs on uvicorn boot, not import).

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "build: multi-stage container + docker-compose"
```

---

### Task 17: Demo scenario (the proof artifact + integration smoke test)

**Files:**
- Create: `demo/mock_prometheus.py`, `demo/inject.py`, `Makefile`, `demo/docker-compose.demo.yml`
- Test: `tests/test_demo_smoke.py`

**Interfaces:**
- Produces:
  - `demo/mock_prometheus.py`: a tiny FastAPI app answering `/api/v1/query_range` and `/api/v1/query` with a *declining* good-ratio series controlled by a module-level knob toggled via `POST /inject/burn`.
  - `demo/inject.py`: a script that (1) POSTs a burn to the mock, (2) POSTs a deploy Change Event to the app's `/api/events`, so the operator watches the forecast bend and correlation name the culprit.
  - `Makefile`: `make test`, `make demo` (compose up app + mock, then run `inject.py`).
  - `tests/test_demo_smoke.py`: an in-process integration test that runs one `evaluate_slo` against the mock series with an injected deploy and asserts a critical alert + deploy correlation - the automated form of the demo (satisfies the Q11 mock-Prometheus smoke test).

- [ ] **Step 1: Write the integration smoke test** in `tests/test_demo_smoke.py`

```python
import pytest
from datetime import datetime, timezone, timedelta
from db.base import make_engine, make_session_factory, init_db
from db.models import AlertEvent
from events.base import ChangeEventStore, ChangeEventInput
from config.slos import SLODefinition
from scheduler import evaluate_slo
from sqlalchemy import select

class DecliningSource:
    """Good-ratio well below target: forces a critical burn."""
    async def query_instant(self, q): return 0.80
    async def query_range(self, q, start, end, step):
        return [(start + timedelta(minutes=5*i), 0.80) for i in range(12)]

SLO = SLODefinition("Demo - Availability", "demo", 99.0, 30, "q",
                    warning_burn_rate=2.0, critical_burn_rate=10.0)

async def test_demo_end_to_end(monkeypatch):
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sf = make_session_factory(engine)
    store = ChangeEventStore(sf)
    now = datetime.now(timezone.utc)
    await store.record(ChangeEventInput("demo", "deploy", "argocd",
                                        "deploy demo v9 (bad release)", now - timedelta(minutes=1)))
    import scheduler as sched
    async def fake_send(n, **kw): pass
    monkeypatch.setattr(sched, "send", fake_send)
    out = await evaluate_slo(SLO, DecliningSource(), sf, store)
    async with sf() as s:
        alerts = (await s.execute(select(AlertEvent))).scalars().all()
    assert alerts and alerts[0].severity == "critical"
    assert out["probable_cause_type"] == "deploy"
    assert "v9" in out["probable_cause"]
```

- [ ] **Step 2: Run to verify it fails then passes**

Run: `pytest tests/test_demo_smoke.py -v`
Expected: PASS (all dependencies exist by now; this is the integration wiring check).

- [ ] **Step 3: Create `demo/mock_prometheus.py`**

```python
"""Mock Prometheus for the demo: serves a good-ratio that drops after a burn is injected."""
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI

app = FastAPI()
STATE = {"good": 0.999}


@app.post("/inject/burn")
def inject_burn(good: float = 0.80):
    STATE["good"] = good
    return {"good": STATE["good"]}


@app.get("/api/v1/query")
def query(query: str):
    return {"status": "success", "data": {"resultType": "vector",
            "result": [{"metric": {}, "value": [datetime.now(timezone.utc).timestamp(),
                                                 str(STATE["good"])]}]}}


@app.get("/api/v1/query_range")
def query_range(query: str, start: float, end: float, step: float):
    now = datetime.now(timezone.utc)
    vals = [[(now - timedelta(minutes=5*i)).timestamp(), str(STATE["good"])] for i in range(12)]
    return {"status": "success", "data": {"resultType": "matrix",
            "result": [{"metric": {}, "values": list(reversed(vals))}]}}
```

- [ ] **Step 4: Create `demo/inject.py`**

```python
"""Inject a burn into the mock and a deploy event into the app, then poll /api/slos."""
import sys
import time
import httpx

APP = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
MOCK = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:9090"

httpx.post(f"{MOCK}/inject/burn", params={"good": 0.80})
from datetime import datetime, timezone  # noqa: E402
httpx.post(f"{APP}/api/events", json={
    "service": "demo", "event_type": "deploy", "source": "argocd",
    "description": "deploy demo v9 (bad release)",
    "timestamp": datetime.now(timezone.utc).isoformat(),
})
print("Injected burn + deploy. Watch the dashboard: forecast should bend, correlation should name v9.")
for _ in range(6):
    time.sleep(10)
    print(httpx.get(f"{APP}/api/slos").json())
```

- [ ] **Step 5: Create `demo/docker-compose.demo.yml`**

```yaml
services:
  mock-prometheus:
    build: { context: .., dockerfile: Dockerfile }
    command: ["uvicorn", "demo.mock_prometheus:app", "--host", "0.0.0.0", "--port", "9090"]
    ports: ["9090:9090"]
  foresight:
    build: { context: .. }
    environment:
      PROMETHEUS_URL: http://mock-prometheus:9090
      DATABASE_URL: sqlite+aiosqlite:////app/data/foresight.db
      SLO_CONFIG_PATH: /app/demo/slos.demo.yaml
      POLL_INTERVAL_SECONDS: "10"
    volumes: [ "./slos.demo.yaml:/app/demo/slos.demo.yaml:ro" ]
    ports: ["8000:8000"]
    depends_on: [mock-prometheus]
```

Also create `demo/slos.demo.yaml`:

```yaml
slos:
  - name: "Demo - Availability"
    service: "demo"
    target_percent: 99.0
    window_days: 30
    metric_query: "demo_good_ratio"
    alert_thresholds:
      warning_burn_rate: 2.0
      critical_burn_rate: 10.0
```

- [ ] **Step 6: Create `Makefile`**

```makefile
.PHONY: test demo
test:
	coverage run -m pytest && coverage report --fail-under=80

demo:
	docker compose -f demo/docker-compose.demo.yml up --build -d
	@sleep 8
	python demo/inject.py http://localhost:8000 http://localhost:9090
	@echo "Open http://localhost:8000  (make demo-down to stop)"

demo-down:
	docker compose -f demo/docker-compose.demo.yml down -v
```

- [ ] **Step 7: Commit**

```bash
git add demo/ Makefile tests/test_demo_smoke.py
git commit -m "feat: demo scenario (mock Prometheus + burn/deploy injector) + smoke test"
```

---

### Task 18: Kubernetes change-event watcher (optional, off by default)

**Files:**
- Create: `events/kubernetes.py`
- Test: `tests/events/test_kubernetes.py`

**Interfaces:**
- Consumes: `ChangeEventStore` (Task 8).
- Produces: `deployment_to_change_event(obj: dict, service_label: str = "app") -> ChangeEventInput | None` - a **pure** mapping from a Kubernetes Deployment watch object (`ADDED`/`MODIFIED` with a bumped `metadata.generation`) to a `ChangeEventInput` of type `"deploy"`, source `"kubernetes"`, service from the label. Returns `None` for objects without a generation bump. (The live `watch()` loop using `kubernetes-asyncio` is thin glue documented in the module; only the pure mapper is unit-tested to keep the test hermetic.)

- [ ] **Step 1: Write the failing test**

```python
from events.kubernetes import deployment_to_change_event

def test_maps_new_generation_to_deploy():
    obj = {"metadata": {"name": "resume", "namespace": "web", "generation": 4,
                        "labels": {"app": "resume"},
                        "annotations": {"deployment.kubernetes.io/revision": "4"}},
           "status": {"observedGeneration": 3}}
    e = deployment_to_change_event(obj)
    assert e is not None
    assert e.service == "resume" and e.event_type == "deploy"
    assert e.source_system == "kubernetes"
    assert "resume" in e.description

def test_no_generation_bump_is_none():
    obj = {"metadata": {"name": "resume", "generation": 3, "labels": {"app": "resume"}},
           "status": {"observedGeneration": 3}}
    assert deployment_to_change_event(obj) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/events/test_kubernetes.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `events/kubernetes.py`**

```python
"""Kubernetes deploy watcher -> ChangeEvent.

The pure mapper below is unit-tested. `watch_deployments` is thin glue over
kubernetes-asyncio; enable with KUBERNETES_WATCH_ENABLED=true and in-cluster RBAC
allowing watch on deployments. It is optional: the app works without it via the
generic /api/events webhook.
"""
from datetime import datetime, timezone

from events.base import ChangeEventInput


def deployment_to_change_event(obj: dict, service_label: str = "app") -> ChangeEventInput | None:
    meta = obj.get("metadata", {})
    gen = meta.get("generation")
    observed = obj.get("status", {}).get("observedGeneration")
    if gen is None or observed is None or gen <= observed:
        return None
    service = meta.get("labels", {}).get(service_label) or meta.get("name")
    revision = meta.get("annotations", {}).get("deployment.kubernetes.io/revision", "?")
    ns = meta.get("namespace", "default")
    return ChangeEventInput(
        service=service,
        event_type="deploy",
        source_system="kubernetes",
        description=f"Deploy {meta.get('name')} (rev {revision}) in {ns}",
        occurred_at=datetime.now(timezone.utc),
        metadata={"namespace": ns, "generation": gen, "revision": revision},
    )


async def watch_deployments(store, settings) -> None:  # pragma: no cover - live glue
    from kubernetes_asyncio import client, config, watch

    try:
        config.load_incluster_config()
    except Exception:
        await config.load_kube_config()
    api = client.AppsV1Api()
    w = watch.Watch()
    async with w.stream(api.list_deployment_for_all_namespaces) as stream:
        async for event in stream:
            obj = event["raw_object"]
            change = deployment_to_change_event(obj)
            if change:
                await store.record(change)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/events/test_kubernetes.py -v`
Expected: PASS.

- [ ] **Step 5: Add `kubernetes-asyncio` as an optional dep** in `pyproject.toml` under a new extra:

```toml
[project.optional-dependencies]
kubernetes = ["kubernetes-asyncio>=30.0"]
```

- [ ] **Step 6: Commit**

```bash
git add events/kubernetes.py tests/events/test_kubernetes.py pyproject.toml
git commit -m "feat: optional Kubernetes deploy watcher (pure mapper unit-tested)"
```

---

### Task 19: ArgoCD adapter (optional)

**Files:**
- Create: `events/argocd.py`
- Test: `tests/events/test_argocd.py`

**Interfaces:**
- Consumes: nothing app-internal.
- Produces: `async def fetch_recent_deploys(argocd_url, token, since: datetime) -> list[ChangeEventInput]` querying ArgoCD's applications API and mapping synced revisions to `ChangeEventInput` of type `"deploy"`, source `"argocd"`. Pure mapping `argocd_app_to_change_event(app_json: dict) -> ChangeEventInput | None` is the unit-tested seam.

- [ ] **Step 1: Write the failing test**

```python
from events.argocd import argocd_app_to_change_event

def test_maps_synced_app():
    app = {"metadata": {"name": "resume"},
           "status": {"operationState": {"phase": "Succeeded",
                       "finishedAt": "2026-09-08T12:00:00Z",
                       "operation": {"sync": {"revision": "abc123"}}},
                      "sync": {"status": "Synced"}}}
    e = argocd_app_to_change_event(app)
    assert e is not None and e.service == "resume" and e.event_type == "deploy"
    assert "abc123"[:7] in e.description

def test_ignores_unfinished():
    app = {"metadata": {"name": "resume"},
           "status": {"operationState": {"phase": "Running"}}}
    assert argocd_app_to_change_event(app) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/events/test_argocd.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `events/argocd.py`**

```python
"""Optional ArgoCD adapter: synced applications -> deploy ChangeEvents."""
from datetime import datetime

import httpx

from events.base import ChangeEventInput


def argocd_app_to_change_event(app: dict) -> ChangeEventInput | None:
    status = app.get("status", {})
    op = status.get("operationState", {})
    if op.get("phase") != "Succeeded":
        return None
    name = app.get("metadata", {}).get("name", "unknown")
    revision = op.get("operation", {}).get("sync", {}).get("revision", "")
    finished = op.get("finishedAt")
    occurred = datetime.fromisoformat(finished.replace("Z", "+00:00")) if finished else datetime.now()
    return ChangeEventInput(
        service=name,
        event_type="deploy",
        source_system="argocd",
        description=f"ArgoCD synced {name} to {revision[:7]}",
        occurred_at=occurred,
        metadata={"revision": revision},
    )


async def fetch_recent_deploys(argocd_url: str, token: str, since: datetime) -> list[ChangeEventInput]:  # pragma: no cover - live glue
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
        r = await client.get(f"{argocd_url.rstrip('/')}/api/v1/applications", headers=headers)
        r.raise_for_status()
        apps = r.json().get("items", [])
    events = [argocd_app_to_change_event(a) for a in apps]
    return [e for e in events if e and e.occurred_at >= since]
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/events/test_argocd.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add events/argocd.py tests/events/test_argocd.py
git commit -m "feat: optional ArgoCD deploy adapter"
```

---

### Task 20: Helm chart

**Files:**
- Create: `charts/sre-foresight/Chart.yaml`, `values.yaml`, `templates/_helpers.tpl`, `templates/deployment.yaml`, `templates/service.yaml`, `templates/configmap-slos.yaml`, `templates/secret.yaml`
- Test: `helm lint` + `helm template`.

**Interfaces:**
- Produces: an installable chart. `values.yaml` carries `image.repository/tag`, `prometheus.url`, `env` extras, `slos` (rendered into a ConfigMap mounted at `/app/config/slos.yaml`), `persistence` (PVC for SQLite), and `secretEnv` (rendered into a Secret for tokens). Deployment mounts the ConfigMap + PVC, sets env from values + the Secret, and probes `/api/health`.

- [ ] **Step 1: Create `charts/sre-foresight/Chart.yaml`**

```yaml
apiVersion: v2
name: sre-foresight
description: Forecast SLO error-budget exhaustion and correlate burn spikes to their cause.
type: application
version: 0.1.0
appVersion: "0.1.0"
```

- [ ] **Step 2: Create `charts/sre-foresight/values.yaml`**

```yaml
image:
  repository: ghcr.io/ngatia/sre-foresight
  tag: ""            # defaults to .Chart.appVersion
  pullPolicy: IfNotPresent
imagePullSecrets: []

prometheus:
  url: "http://prometheus:9090"

pollIntervalSeconds: 60

env: {}             # extra plain env vars
secretEnv: {}       # rendered into a Secret (e.g. PROMETHEUS_TOKEN, SLACK_WEBHOOK_URL)

persistence:
  enabled: true
  size: 1Gi
  storageClass: ""

service:
  port: 8000

resources:
  requests: { cpu: 100m, memory: 256Mi }
  limits: { cpu: 500m, memory: 512Mi }

slos:
  slos:
    - name: "Example - Availability"
      service: "example"
      target_percent: 99.0
      window_days: 30
      metric_query: "avg_over_time(probe_success{instance='https://example.com'}[5m])"
      alert_thresholds:
        warning_burn_rate: 2.0
        critical_burn_rate: 10.0
```

- [ ] **Step 3: Create `charts/sre-foresight/templates/_helpers.tpl`**

```
{{- define "sre-foresight.fullname" -}}
{{- .Release.Name }}-{{ .Chart.Name -}}
{{- end -}}
```

- [ ] **Step 4: Create `charts/sre-foresight/templates/configmap-slos.yaml`**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "sre-foresight.fullname" . }}-slos
data:
  slos.yaml: |
{{ toYaml .Values.slos | indent 4 }}
```

- [ ] **Step 5: Create `charts/sre-foresight/templates/secret.yaml`**

```yaml
{{- if .Values.secretEnv }}
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "sre-foresight.fullname" . }}-env
type: Opaque
stringData:
{{- range $k, $v := .Values.secretEnv }}
  {{ $k }}: {{ $v | quote }}
{{- end }}
{{- end }}
```

- [ ] **Step 6: Create `charts/sre-foresight/templates/service.yaml`**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "sre-foresight.fullname" . }}
spec:
  selector:
    app: {{ include "sre-foresight.fullname" . }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: 8000
```

- [ ] **Step 7: Create `charts/sre-foresight/templates/deployment.yaml`**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "sre-foresight.fullname" . }}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {{ include "sre-foresight.fullname" . }}
  template:
    metadata:
      labels:
        app: {{ include "sre-foresight.fullname" . }}
    spec:
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets: {{ toYaml . | nindent 8 }}
      {{- end }}
      containers:
        - name: foresight
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - containerPort: 8000
          env:
            - name: PROMETHEUS_URL
              value: {{ .Values.prometheus.url | quote }}
            - name: POLL_INTERVAL_SECONDS
              value: {{ .Values.pollIntervalSeconds | quote }}
            - name: SLO_CONFIG_PATH
              value: /app/config/slos.yaml
            - name: DATABASE_URL
              value: sqlite+aiosqlite:////app/data/foresight.db
            {{- range $k, $v := .Values.env }}
            - name: {{ $k }}
              value: {{ $v | quote }}
            {{- end }}
          {{- if .Values.secretEnv }}
          envFrom:
            - secretRef:
                name: {{ include "sre-foresight.fullname" . }}-env
          {{- end }}
          volumeMounts:
            - name: slos
              mountPath: /app/config/slos.yaml
              subPath: slos.yaml
            - name: data
              mountPath: /app/data
          livenessProbe:
            httpGet: { path: /api/health, port: 8000 }
            initialDelaySeconds: 10
          readinessProbe:
            httpGet: { path: /api/health, port: 8000 }
          resources: {{ toYaml .Values.resources | nindent 12 }}
      volumes:
        - name: slos
          configMap:
            name: {{ include "sre-foresight.fullname" . }}-slos
        - name: data
        {{- if .Values.persistence.enabled }}
          persistentVolumeClaim:
            claimName: {{ include "sre-foresight.fullname" . }}-data
        {{- else }}
          emptyDir: {}
        {{- end }}
{{- if .Values.persistence.enabled }}
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{ include "sre-foresight.fullname" . }}-data
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: {{ .Values.persistence.size }}
  {{- if .Values.persistence.storageClass }}
  storageClassName: {{ .Values.persistence.storageClass }}
  {{- end }}
{{- end }}
```

- [ ] **Step 8: Lint + template**

Run: `helm lint charts/sre-foresight && helm template t charts/sre-foresight >/dev/null && echo OK`
Expected: `OK`.

- [ ] **Step 9: Commit**

```bash
git add charts/
git commit -m "feat: Helm chart (ConfigMap SLOs, PVC, secret env, health probes)"
```

---

### Task 21: GitHub Actions CI/CD

**Files:**
- Create: `.github/workflows/ci.yml`
- Test: pushed to a branch; observe green.

**Interfaces:**
- Produces: a workflow that on PR/push runs ruff + pytest with coverage gate and `helm lint`; on push to `main` and on `v*` tags additionally builds a multi-arch image and pushes to GHCR (`:main`, `:latest`, and the semver tag), and on tags packages the Helm chart as a release asset.

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:

permissions:
  contents: read
  packages: write

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: coverage run -m pytest && coverage report --fail-under=80
      - uses: azure/setup-helm@v4
      - run: helm lint charts/sre-foresight

  image:
    needs: test
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ghcr.io/ngatia/sre-foresight
          tags: |
            type=raw,value=main,enable=${{ github.ref == 'refs/heads/main' }}
            type=semver,pattern={{version}}
            type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/tags/v') }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
```

- [ ] **Step 2: Validate YAML locally**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/
git commit -m "ci: lint + test + coverage gate, multi-arch image, helm lint"
```

---

### Task 22: README completion + `.env.example`

**Files:**
- Modify: `README.md` (fill "How it works", "Quick start", "Configuration reference")
- Create: `.env.example`

**Interfaces:** documentation only.

- [ ] **Step 1: Create `.env.example`**

```bash
PROMETHEUS_URL=http://localhost:9090
# PROMETHEUS_TOKEN=
# DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/foresight
SLO_CONFIG_PATH=config/slos.yaml
POLL_INTERVAL_SECONDS=60
# SLACK_WEBHOOK_URL=
# NOTIFY_WEBHOOK_URL=
# POSTMORTEM_DIR=/app/postmortems
# KUBERNETES_WATCH_ENABLED=false
# ARGOCD_URL=
# ARGOCD_TOKEN=
```

- [ ] **Step 2: Fill the README** "How it works" (the 60s loop), "Quick start" (`cp config/slos.example.yaml config/slos.yaml`, set `PROMETHEUS_URL`, `docker compose up`, open `:8000`), "Try the demo" (`make demo`), and a Configuration table listing every env var from `.env.example` and every Helm value from Task 20. (Prose is the deliverable; write it against the actual behavior implemented above.)

- [ ] **Step 3: Commit**

```bash
git add README.md .env.example
git commit -m "docs: complete README + env example"
```

---

## Self-Review

**1. Spec coverage:**
- Prometheus-only input (ADR 0001) → Tasks 5, 12, 14. ✓
- SQLite default / Postgres optional (ADR 0002) → Tasks 2, 4 (engine-agnostic), 16, 20. ✓
- Declarative YAML SLOs, read-only API (ADR 0003) → Tasks 3, 13. ✓
- Forecasting differentiator → Task 7. ✓
- Correlation differentiator (k8s + webhook + ArgoCD adapter) → Tasks 8, 9, 12, 18, 19. ✓
- Dashboard (keep vanilla JS/Chart.js) → Task 15. ✓
- Postmortem (generic Markdown) → Task 11. ✓
- Notifications (webhook + Slack) → Task 10. ✓
- No built-in auth → documented in README (Task 22); no mutating endpoint added except the deliberately-documented `/api/events`. ✓
- Distribution: image + compose + Helm → Tasks 16, 20. ✓
- Tests: unit math + mock-Prometheus smoke → Tasks 6, 7, 9 + Task 17. ✓
- CI: Actions, multi-arch, semver → Task 21. ✓
- Proof `make demo` → Task 17. ✓
- Homelab GitOps deploy → **out of scope for this plan** (separate follow-on plan in `k8s-homelab`; depends on the published image + chart from Tasks 20/21).

**2. Placeholder scan:** No "TBD"/"implement later" in code steps. The only intentional `_TODO_` strings are literal content of the generated postmortem template (Task 11), which is correct output, not a plan gap. README prose (Task 22) is described, not code.

**3. Type consistency:** `ChangeEventInput` (Task 8) is consumed unchanged by Tasks 12/18/19. `CorrelationResult.events` (list of dicts with `time`/`type`/`source`/`description`/`final_score`) is produced in Task 9 and consumed identically in Tasks 11/12. `Notification` fields (Task 10) match the constructor call in Task 12. `evaluate_slo` signature (Task 12) matches its callers in Tasks 14/17. `MetricsSource` protocol (Task 5) matches the fakes used in Tasks 12/17. Consistent.

## Known hardening items (fold into the named tasks during execution)

- **Task 15 (dashboard) - avoid `innerHTML` with change-event text.** Alert
  descriptions and probable-cause strings originate from Change Events, which
  can arrive via the public `/api/events` webhook, so they are attacker-
  influenced. Build those rows with `textContent` / `createElement` (or escape)
  rather than `innerHTML`, to close a stored-XSS path. Static markup with no
  interpolated data may stay as-is.
- **Task 15 (dashboard) - pin the Chart.js CDN with SRI.** Add
  `integrity="sha384-..." crossorigin="anonymous"` to the Chart.js `<script>`
  (fetch the hash for the pinned 4.4.3 build), or vendor the file into the image.
- **Task 19 (ArgoCD adapter) - do not hardcode `verify=False`.** Make TLS
  verification configurable (`ARGOCD_INSECURE`, default `false`), so the default
  is secure and only a self-signed homelab opts out explicitly.

## Follow-on (separate plan): homelab GitOps deploy

After Tasks 20-21 publish a `ghcr.io/ngatia/sre-foresight` image + Helm chart, a short second plan wires it into `k8s-homelab`: one ArgoCD Application consuming the public chart (pinned tag), a SealedSecret for `PROMETHEUS_TOKEN`/`SLACK_WEBHOOK_URL`/`ARGOCD_TOKEN`, an HTTPRoute for `sre-foresight.k8s.ngatia.me`, and a `values.yaml` with 2-3 real SLOs (resume/about, sms, an arr-stack service) whose PromQL is verified against the live Grafana Cloud Prometheus series first.
