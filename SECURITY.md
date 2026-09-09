# Security Policy

## Reporting a vulnerability

Please report security issues privately via GitHub's
[private vulnerability reporting](https://github.com/ngatia/sre-foresight/security/advisories/new)
(Security tab -> Report a vulnerability). Do not open a public issue for a
suspected vulnerability.

We aim to acknowledge reports within a few days.

## Deployment security notes

SRE Foresight ships with **no built-in authentication** and binds internally by
default. It is meant to run behind your own ingress and authorization layer,
like Prometheus or Alertmanager. In particular:

- `POST /api/events` is an unauthenticated ingest endpoint by design. Do not
  expose it to untrusted networks without an auth proxy in front.
- Provide secrets (Prometheus token, Slack/webhook URLs, ArgoCD token) via
  environment variables or a Kubernetes Secret, never committed to the repo.
- Keep TLS verification enabled for the ArgoCD adapter (`ARGOCD_INSECURE=false`,
  the default); only disable it for a self-signed homelab instance you trust.
