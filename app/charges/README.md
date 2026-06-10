## Scope

This file owns only:

- A pointer to the canonical domain doc.

Source of truth: reference

> **Canonical doc:** [`docs/domains/charges.md`](../../../docs/domains/charges.md)

## Tests

```bash
JWT_SECRET=test-secret pytest -q tests/charges tests/regression/test_core_regressions_binders_charges_notifications.py
```
