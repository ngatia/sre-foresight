# SRE Foresight

**Grafana tells you the house is on fire. SRE Foresight tells you which room
started it, how long until it burns down, and hands you the fire report while
you are still fighting it.**

SRE Foresight sits on top of your existing Prometheus-compatible metrics and
does the two things SLO dashboards do not:

1. **Forecasts error-budget exhaustion** - not just "burn rate is high right
   now," but "at this trend, the budget is gone in ~4h (range 2h to 7h)," with
   a confidence cone.
2. **Correlates burn spikes to the change that caused them** - it watches your
   deploys and pipelines and names the probable culprit, instead of leaving you
   to cross-reference timestamps by hand.

It reads any Prometheus-compatible source (self-hosted Prometheus, Mimir,
Thanos, Amazon Managed Prometheus, Grafana Cloud), runs as a single container,
and needs no database to get started.

> Status: revival in progress. This README describes the target v1. See
> [`CONTEXT.md`](CONTEXT.md) for the domain glossary and
> [`docs/adr/`](docs/adr) for the key design decisions.

## Why not just Grafana / Datadog / Nobl9?

Those tools show you the *current* burn rate and alert on thresholds, and they
do it well - keep using them. What they do not do: forecast *when* the budget
runs out, or tell you *which deploy* caused the spike. SRE Foresight is
complementary, not a replacement.

## Quick start

```bash
# (target experience - not wired up yet)
docker compose up
# open http://localhost:8000
```

## How it works

_To be written as the implementation lands._

## Configuration

SLOs are declared in YAML (see [ADR 0003](docs/adr/0003-declarative-yaml-slos.md)).
Metrics come from any Prometheus-compatible source
([ADR 0001](docs/adr/0001-prometheus-as-sole-metrics-interface.md)). State lives
in SQLite by default, Postgres optionally
([ADR 0002](docs/adr/0002-sqlite-default-postgres-optional.md)).

## Security

SRE Foresight ships with no built-in authentication and binds internally by
default. Put it behind your own ingress and authorization layer before exposing
it. This follows the same convention as Prometheus and Alertmanager.

## License

[Apache-2.0](LICENSE)
