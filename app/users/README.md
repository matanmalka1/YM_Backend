## Scope

This file owns only:

- A pointer to the canonical domain doc.

Source of truth: reference

> **Canonical doc:** [`docs/domains/users.md`](../../../docs/domains/users.md)

## Tests

```bash
JWT_SECRET=test-secret ./.venv/bin/python -m pytest -q tests/auth tests/users tests/middleware/test_rate_limiting.py tests/core/test_config_additional.py
```
