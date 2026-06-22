## Scope
This file owns only:
- Backend test layout and local test-suite reference notes.

This file must not contain:
- Canonical project-wide testing rules.
- Product/domain behavior.
- Architecture decisions.

Source of truth: reference

# Tests Layout

> Last audited: 2026-03-17 (domain-by-domain backend sync).

- Domain-first tree mirrors `app/<domain>` names (e.g., `charge`, not `charges`) so navigation is 1:1.
- Each domain has its own folder: `tests/<domain>/`.
  - API/route tests live in `tests/<domain>/api/` with any API helpers alongside.
  - Service/unit tests live in `tests/<domain>/service/` with domain fakes/enums beside them.
- Cross-domain suites stay in `tests/regression/`; shared fixtures stay in `tests/conftest.py`.
- Prefer intra-domain imports (`tests.<domain>.api.*` / `tests.<domain>.service.*`) instead of reaching across domains.
- File naming: test modules start with `test_*.py` (see `pytest.ini`).

## Run Commands

- Generic domain run: `./.venv/bin/python -m pytest tests/<domain> -q`
- API-only inside a domain: `./.venv/bin/python -m pytest tests/<domain>/api -q`
- Service-only inside a domain: `./.venv/bin/python -m pytest tests/<domain>/service -q`
- Repository-only inside a domain: `./.venv/bin/python -m pytest tests/<domain>/repository -q`

## Domain Commands

- `actions`: `./.venv/bin/python -m pytest tests/actions -q`
- `advance_payments`: `./.venv/bin/python -m pytest tests/advance_payments -q`
- `annual_reports`: `./.venv/bin/python -m pytest tests/annual_reports -q`
- `auth`: `./.venv/bin/python -m pytest tests/auth -q`
- `authority_contact`: `./.venv/bin/python -m pytest tests/authority_contact -q`
- `binders`: `./.venv/bin/python -m pytest tests/binders -q`
- `businesses`: `./.venv/bin/python -m pytest tests/businesses -q`
- `charge`: `./.venv/bin/python -m pytest tests/charge -q`
- `clients`: `./.venv/bin/python -m pytest tests/clients -q`
- `core`: `./.venv/bin/python -m pytest tests/core -q`
- `correspondence`: `./.venv/bin/python -m pytest tests/correspondence -q`
- `dashboard`: `./.venv/bin/python -m pytest tests/dashboard -q`
- `documents`: `./.venv/bin/python -m pytest tests/documents -q`
- `health`: `./.venv/bin/python -m pytest tests/health -q`
- `infrastructure`: `./.venv/bin/python -m pytest tests/infrastructure -q`
- `invoice`: `./.venv/bin/python -m pytest tests/invoice -q`
- `notification`: `./.venv/bin/python -m pytest tests/notification -q`
- `permanent_documents`: `./.venv/bin/python -m pytest tests/permanent_documents -q`
- `regression`: `./.venv/bin/python -m pytest tests/regression -q`
- `reminders`: `./.venv/bin/python -m pytest tests/reminders -q`
- `reports`: `./.venv/bin/python -m pytest tests/reports -q`
- `search`: `./.venv/bin/python -m pytest tests/search -q`
- `signature_requests`: `./.venv/bin/python -m pytest tests/signature_requests -q`
- `tax_calendar`: `./.venv/bin/python -m pytest tests/tax_calendar -q`
- `timeline`: `./.venv/bin/python -m pytest tests/timeline -q`
- `users`: `./.venv/bin/python -m pytest tests/users -q`
- `utils`: `./.venv/bin/python -m pytest tests/utils -q`
- `vat_reports`: `./.venv/bin/python -m pytest tests/vat_reports -q`
