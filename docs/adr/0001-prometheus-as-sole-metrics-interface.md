# 1. Prometheus/PromQL as the sole metrics interface

Date: 2026-09-08

## Status

Accepted

## Context

The original build read metrics from two hardwired sources: the Grafana Cloud
HTTP API and AWS CloudWatch (via boto3). That made sense when the tool served
one organization's specific stack, but this revival targets a different goal:
a public tool that any Deployer can run on their own infrastructure.

Every additional first-class metrics source multiplies the surface we have to
test, document, and keep working for strangers. Meanwhile, the systems people
actually run SLOs against - self-hosted Prometheus, Grafana Mimir, Thanos,
Amazon Managed Prometheus, and Grafana Cloud itself - all answer the same
Prometheus query API. Grafana is itself fed by it.

## Decision

For v1, PromQL over the Prometheus HTTP query API is the single metrics
interface. An SLO's SLI is a PromQL query. CloudWatch, Datadog, and any other
source become optional Adapters behind the same internal contract, added later
only if there is demand.

## Consequences

- One well-tested query path covers the large majority of would-be Deployers,
  including the homelab reference deployment (pointed at its Grafana Cloud
  Prometheus).
- SLO definitions stay portable: a query plus a target, nothing vendor-shaped.
- CloudWatch users cannot deploy v1 without either an Adapter or a metrics
  bridge (for example, a CloudWatch exporter into Prometheus). This is an
  accepted gap, not an oversight.
- The old `collectors/grafana.py` and `collectors/cloudwatch.py` are removed
  from the core path; `collectors/prometheus.py` becomes the reference
  implementation of the Data Source contract.
