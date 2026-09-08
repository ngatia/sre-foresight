# 2. SQLite by default, Postgres optional

Date: 2026-09-08

## Status

Accepted

## Context

The tool stores time-ordered burn-rate samples, alert events, and correlation
events, and needs that history to fit forecasts. The original build required a
PostgreSQL instance. For a tool whose selling point is "anyone can pull and
deploy it on their own infra," a mandatory external database is significant
friction: it turns a one-command trial into a multi-service setup.

## Decision

SQLite is the default store, written to a single file (a mounted volume in
Kubernetes). Postgres is opt-in through a single `DATABASE_URL` environment
variable. The persistence layer is written against the ORM so both work without
code changes.

## Consequences

- A newcomer gets a working instance from one `docker run` or one manifest,
  with no database to provision. This is the single biggest lever on real
  deploy-ability.
- A serious Deployer (or the homelab, pointing at the existing shared Postgres)
  flips `DATABASE_URL` and gets durability and concurrent access.
- SQLite's single-writer model is acceptable: this is one background poller
  writing on a fixed interval, not a high-concurrency workload.
- We must keep the schema and queries to the intersection both engines support,
  and test against both in CI. That constraint is the cost of the flexibility.
