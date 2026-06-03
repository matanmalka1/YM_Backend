## Scope

This file owns only:

- Implemented backend behavior for the actions metadata and execution registry.
- Current service, repository, model, and API ownership boundaries for this domain.

This file must not contain:

- Historical implementation plans.
- Future product behavior that is not implemented.
- Cross-domain architecture rules.

Source of truth: mandatory

> **Note:** No canonical doc exists yet for the actions domain in `docs/domains/`.

# Actions Module

> Last audited: 2026-04-23

Defines executable UI actions shared across domains (businesses, binders, charges, VAT work items, annual reports).
Also owns cross-domain application workflows that do not belong to a single domain.

## Scope

This module provides:

- Canonical dashboard action builder (`build_action`)
- Canonical confirm builder (`build_confirm`)
- Domain action factories for binders, businesses, charges, VAT work items, and annual reports
- Role-aware action filtering (for example advisor-only actions)
- Confirm-dialog metadata and optional payload contracts for frontend executors
- `obligation_orchestrator.py` — cross-domain workflow that generates tax calendar entries and annual reports for a client (idempotent; used on client create/update and business create)
- `ObligationResult` / `generate_client_obligations_result(...)` — explicit partial-success breakdown for obligation generation

## Domain Model

This module does not define database tables.

Primary output model for domain actions is `ActionDescriptor`:

- `key` (action key)
- `label` (Hebrew user label)
- `type` (`link|mutation|modal`)
- `method` (validated HTTP method: `get|post|put|patch|delete`)
- `endpoint` (relative API endpoint)
- `payload_schema` (payload behavior hint)
- `confirm` plus flat `confirm_title` / `confirm_message`

Confirm metadata is also typed (`ActionConfirm`) and currently supports:

- `title`
- `message`
- `confirm_label`
- `cancel_label`
- `inputs` (optional; currently validated for supported input types only)

Common action producers:

- `get_binder_actions(binder)`
- `get_business_actions(business, user_role=None)`
- `get_charge_actions(charge)`
- `get_annual_report_actions(report_id, status)`
- `generate_client_obligations_result(...)`

Implementation references:

- Registry: `app/actions/action_registry.py`
- Descriptor schema/builders: `app/core/action_schemas.py`, `app/core/action_builders.py`
- Shared helpers: `app/actions/action_helpers.py`
- Binder actions: `app/actions/binder_actions.py`
- Business actions: `app/actions/business_actions.py`
- Charge actions: `app/actions/charge_actions.py`
- Tax/annual actions: `app/actions/report_deadline_actions.py`
- Obligation workflow: `app/actions/obligation_orchestrator.py`

## API

This module has no FastAPI router and no direct HTTP endpoints.

It is consumed internally by other modules that attach `available_actions` to response payloads.

## Behavior Notes

- `build_action` is the dashboard quick-action constructor and validates supported HTTP methods.
- `build_confirm` is the canonical constructor for confirm dialogs and centralizes common confirm metadata.
- Binder actions:
  - `in_office` => `ready`
  - `ready_for_handover` => `return` (`payload_schema="requires_input"`)
- Business actions:
  - endpoints are built only from `client_id`; missing `client_id` fails fast
  - `active` => `freeze` (advisor only)
  - `frozen` => `activate`
- Charge actions:
  - `draft` => `issue_charge`, `cancel_charge`
  - `issued` => `mark_paid`, `cancel_charge`
- Annual report actions:
  - `submitted` => `amend`
  - statuses outside final states include `submit`
- Domain descriptors are intentionally transport-oriented (`method` + `endpoint` + optional confirm metadata) so frontend can execute actions generically.
- `obligation_orchestrator.py` fails fast on unsupported `entity_type`; it does not default annual reports to `INDIVIDUAL`.
- `generate_client_obligations(...)` preserves the legacy `int` return API for existing callers.
- `generate_client_obligations_result(..., best_effort=True)` exposes the intentional partial-success design explicitly via:
  - `deadlines_created`
  - `reports_created`
  - `errors`

## Error Envelope

This module itself does not raise HTTP/domain envelopes because it does not expose routes.

Validation and error envelopes are handled by the endpoint that executes each action target.

## Cross-Domain Integration

- `businesses` APIs attach `available_actions` via `get_business_actions`.
- `binders` list services attach binder actions via `get_binder_actions`.
- `charge` and dashboard quick-actions use `get_charge_actions`.
- TaxCalendar responses expose grouped obligation state; annual reports attach report-specific actions separately.
- `annual_reports` response projection attaches actions via `get_annual_report_actions`.
- Timeline events are informational only and do not attach action descriptors.

## Tests

Actions behavior is covered by direct and domain tests, including:

- `tests/actions/test_action_registry.py`
- `tests/actions/test_business_actions.py`
- `tests/actions/test_obligation_orchestrator.py`
- `tests/actions/test_report_deadline_actions.py`
- `tests/actions/test_binder_actions.py`
- `tests/businesses/api/test_businesses.py`
- `tests/binders/api/test_binders.py`
- `tests/timeline/service/test_timeline_event_builders.py`
- `tests/timeline/service/test_timeline_event_builders_additional.py`
- `tests/timeline/service/test_timeline_tax_builders.py`

Run related suites:

```bash
JWT_SECRET=test-secret pytest -q tests/actions tests/businesses tests/binders tests/timeline
```
