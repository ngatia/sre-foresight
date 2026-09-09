# Contributing

Thanks for your interest in SRE Foresight.

## Development setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

Tests import the flat-layout modules via pytest's `pythonpath` (this is an
application, not an installable library, so the editable install only pulls in
dependencies).

## Before you open a PR

Run what CI runs:

```bash
ruff check .
coverage run -m pytest && coverage report --fail-under=80
helm lint charts/sre-foresight
```

- New behaviour needs tests; the forecasting and correlation logic in
  `engine/` and `correlate/` is unit-tested against synthetic fixtures with
  known answers, so add cases there rather than end-to-end where you can.
- Keep the domain language consistent with [`CONTEXT.md`](CONTEXT.md).
- Load-bearing, hard-to-reverse decisions get a short ADR in
  [`docs/adr/`](docs/adr).

## Pull requests

`main` is protected: every change lands through a PR, and the `test` check
must be green. Small, focused PRs with a clear description are easiest to
review. Conventional-commit titles (`feat:`, `fix:`, `docs:`, `chore:`) are
appreciated.

## Reporting security issues

Please use private vulnerability reporting rather than a public issue. See
[`SECURITY.md`](SECURITY.md).
