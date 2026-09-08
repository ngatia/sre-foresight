# 3. SLOs are declared in YAML; the API and dashboard are read-only over them

Date: 2026-09-08

## Status

Accepted

## Context

A Deployer has to tell the tool which SLOs to track (each is a PromQL query, a
target, a window, and alert thresholds). There are three common shapes for
this: a declarative config file, a CRUD API backed by the database, or a
Kubernetes custom resource with a controller.

The original build stored SLOs in Postgres and edited them through the API.
That couples "defining an SLO" to "having a writable database up," and it makes
the SLO set invisible to version control - the reliability targets, which are
exactly the kind of thing that should be reviewed and history-tracked, live
only in a database.

## Decision

SLOs are declared in a YAML file (committed to a repo, or mounted as a
ConfigMap). The tool loads them at startup and on reload. The REST API and the
dashboard are read-only over the loaded set in v1: they show SLOs, budgets,
forecasts, and correlations, but they do not create or edit SLOs.

## Consequences

- The lowest-friction deploy story: define SLOs in a file, start the container,
  done. No write path to the database is needed just to declare targets.
- GitOps-native. SLO changes are diffs in a pull request, which suits both the
  homelab and any serious SRE shop. It also fits the reference deployment
  (SLOs live in the Helm chart's values or a mounted file).
- Runtime editing from the dashboard is not available in v1. Anyone who needs
  that must edit the YAML and reload. A CRD-based model (option we rejected)
  remains the natural future path if in-cluster, API-driven editing is wanted,
  at the cost of locking the tool to Kubernetes.
