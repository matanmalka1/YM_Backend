## Scope
This file owns only:
- Tracked system gaps and task notes at the time they were recorded.

This file must not contain:
- Canonical architecture rules.
- Product/domain source-of-truth behavior.
- Permanent workflow rules.

Source of truth: reference

# TODO - Verified System Gaps

Last verified from code, migrations, and tests: 2026-06-07.

## Critical

- [ ] Add reconciliation for `entity_type` changes.
  - Current state: advisor-only guard exists, but existing `AnnualReport.client_type`, `AnnualReport.form_type`, and `VatWorkItem.period_type` snapshots are not reconciled or flagged.
  - Relevant code: `app/clients/services/client_update_service.py`, `app/annual_reports/models/annual_report_model.py`, `app/vat_reports/models/vat_work_item.py`

- [ ] Add downstream lifecycle handling for client soft-delete.
  - Current state: `delete_client()` soft-deletes only `ClientRecord`; close/freeze has partial downstream handling, delete does not.
  - Must decide per domain: cancel, close, archive, preserve read-only, or block delete.
  - Relevant code: `app/clients/services/client_lifecycle_service.py`

- [ ] Implement and schedule reminder execution.
  - Current state: `ReminderExecutorService._execute()` always fails reminders as unsupported, and app lifespan schedules only signature-request expiry.
  - Relevant code: `app/reminders/services/reminder_executor_service.py`, `app/core/background_jobs.py`, `app/lifespan.py`

- [ ] Add client-scoped reminder cancellation.
  - Current state: `Reminder` has no explicit `client_record_id` / `business_id`, and there is no `cancel_scheduled_by_client` service path.
  - Relevant code: `app/reminders/models/reminder.py`, `app/reminders/repositories/reminder_repository.py`

## Cross-Domain: Sorting & Search

- [ ] Add sort_by / order to all data tables (cross-domain).
  - Current state: most domains sort by a hardcoded column (usually `created_at DESC`). Only `clients` has sort params today.
  - Plan: establish a single convention (query params `sort_by` + `order=asc|desc`) and apply uniformly across all list endpoints + DataTable column headers in the frontend.
  - Domains to cover: charges (`amount`, `issued_at`, `status`, `created_at`), vat_reports, annual_reports, binders, reminders, notifications, signature_requests, and any other paginated list.
  - Scope: every affected repo, router, frontend hook, and `DataTable` column header — requires a design pass before implementation.

- [ ] Add free-text search to charges list (low priority).
  - Current state: no search param in repo or router.
  - Scope: ILIKE on joined client name + charge description; `app/charge/repositories/charge_repository.py`, `app/charge/api/charge.py`, frontend filter field.

## Cross-Domain: Pagination Audit

- [x] Document bounded-but-unpaginated lists.
  - Severity: Low.
  - Done: added docstrings/comments documenting the bound on `GET /advance-payments/overview/batches` (one row per month with a batch; <=12 with `year`), `GET /settings/tax-calendar/rules` (all config rows, no cap), and the dashboard attention fetch/cap constants. Recent activity was already documented.
  - Note: the original "push urgency filtering into the DB" recommendation does not apply — work-queue items are aggregated in-memory from multiple sources, so urgency filtering and sorting are necessarily Python-side. `list_items` already returns items globally sorted by urgency+due_date before the over-fetch and display cap, so the cap is correct in the common case.

## High

- [ ] Complete invoice provider integration.
  - Current state: invoice attach API now exists (`POST /api/v1/invoices`, `GET /api/v1/invoices/charge/{charge_id}`, schemas `InvoiceAttachRequest`/`InvoiceResponse`), but there is still no provider client or call from `BillingService.issue_charge()`.
  - Relevant code: `app/invoice/services/invoice_service.py`, `app/charge/services/billing_service.py`, `app/config.py`

- [ ] Add frontend client for invoice attach/get endpoints.
  - Current state (2026-06-10): backend exposes `POST /api/v1/invoices` and `GET /api/v1/invoices/charge/{charge_id}`; `openapi.json` + frontend `generated.ts` baseline regenerated, but no app code consumes them yet. The only invoice references in the charges feature are the `invoice_issued` notification trigger, a different concept.
  - Scope: add `contracts.ts` types + React Query hook (likely `frontend/src/features/charges/api/`), wire into charge UI (e.g. `ChargeDetailDrawer`).

- [ ] Add batched alert counts for client sidebar navigation.
  - Current state: notification/work-queue summaries exist per client, but no batched endpoint exists for all sidebar clients.
  - Docs: tracked as future/planned in `docs/domains/clients.md`, `docs/domains/notifications.md`, and `docs/domains/work-queue.md`.
  - Relevant code: `app/notification/api/notifications.py`, `app/work_queue/api/routes.py`, `../frontend/src/components/layout/ClientSidebar/ClientSidebar.tsx`

## Product Scope Gaps

- [ ] Add bookkeeping core if this system must become a full accounting-office platform.
  - Missing domains: journal entries, ledger, trial balance, bank reconciliation.

- [ ] Add payroll workflows if the office manages payroll.
  - Missing domains: employees, payslips, employer reports, payroll payments.

- [ ] Add withholding-report workflows.
  - Missing first-class workflows: 102, 126, 856.

- [ ] Add capital statement / wealth declaration workflow.

- [ ] Add direct authority filing/integration layer.
  - Missing live filing/status integrations with Israeli authorities.


# DO NOT Execute unless explicitly TOLD
- [ ] Add client self-service portal.
  - Missing client login, document upload by client, task/status visibility, and approval flows outside public signature links.
