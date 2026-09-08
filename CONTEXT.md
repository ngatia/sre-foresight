# Context: SRE Foresight

The glossary for this project. Domain language only, no implementation detail.
If a term here conflicts with how the code or a conversation uses a word, the
conflict is a bug in one of them - resolve it, don't leave both.

## Core reliability terms

- **SLO (Service Level Objective)** - a target reliability level for a
  service, stated as a good/bad signal plus a percentage target over a rolling
  window (for example: 99.0% of requests succeed over 30 days).

- **SLI (Service Level Indicator)** - the measured signal an SLO is judged
  against (for example: the success ratio of HTTP requests).

- **Error Budget** - the amount of failure an SLO permits within its window.
  It is `1 - target`. A 99.0% target over 30 days is a 1.0% error budget.

- **Burn Rate** - how fast the error budget is being consumed relative to a
  steady baseline. A burn rate of 1 means the budget will last exactly the
  window; a burn rate of 10 means it will be gone ten times faster. Measured
  over several windows at once (short windows catch fast burns, long windows
  catch slow ones).

- **Budget Remaining** - the fraction of the error budget still unspent in the
  current window, from 100% (untouched) down to 0% (exhausted).

## The differentiators

- **Exhaustion Forecast** - the predicted future time at which Budget
  Remaining reaches zero, produced by fitting a trend to recent history. This
  is a *prediction*, not a current reading, and it is the primary thing this
  project does that a plain SLO dashboard does not.

- **Forecast Cone** - the confidence range around an Exhaustion Forecast (a
  lower and upper bound, not a single line). The cone widens when the trend is
  noisy and narrows when it is clean.

- **Change Event** - a deploy or pipeline occurrence that could plausibly have
  changed a service's reliability. Sourced from watching the cluster, from an
  inbound webhook, or from an optional Adapter.

- **Correlation** - the act of matching a burn spike to the Change Event most
  likely to have caused it, judged by how close in time the event was to the
  spike. Its output is a **Probable Cause**: a single named Change Event with a
  confidence score, plus the runners-up.

- **Postmortem Draft** - an auto-generated incident writeup, in Markdown,
  produced when Budget Remaining falls critically low. A starting point for a
  human, never a finished document.

## Deployment and extension terms

- **Data Source** - where SLIs are read from. In this project the built-in
  Data Source is anything that answers PromQL queries.

- **Adapter** - an optional, pluggable source of metrics or Change Events
  beyond the built-in defaults (for example an ArgoCD adapter or a Bitbucket
  adapter). Adapters are how a specific organization's tooling plugs in without
  the core needing to know about it.

- **Deployer** - a person who pulls this project and runs it on their own
  infrastructure. The Deployer is a first-class audience: the tool must be
  useful to someone who is not its author.
