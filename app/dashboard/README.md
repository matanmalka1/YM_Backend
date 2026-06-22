## Scope

This file owns only:

- A pointer to the canonical domain doc.

Source of truth: reference

> **Canonical doc:** [`docs/domains/dashboard.md`](../../../docs/domains/dashboard.md)

## Tests

```bash
JWT_SECRET=test-secret ./.venv/bin/python -m pytest -q tests/dashboard
```
