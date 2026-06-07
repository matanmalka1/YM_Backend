## Scope
This file owns only:
- Tracked system gaps and task notes at the time they were recorded.

This file must not contain:
- Canonical architecture rules.
- Product/domain source-of-truth behavior.
- Permanent workflow rules.

Source of truth: reference

# TODO - Verified System Gaps

Last verified from code, migrations, and tests: 2026-05-17.

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

- [ ] Add sort_by / sort_order to all data tables (cross-domain).
  - Current state: most domains sort by a hardcoded column (usually `created_at DESC`). Only `clients` has sort params today.
  - Plan: establish a single convention (query params `sort_by` + `sort_order=asc|desc`) and apply uniformly across all list endpoints + DataTable column headers in the frontend.
  - Domains to cover: charges (`amount`, `issued_at`, `status`, `created_at`), vat_reports, annual_reports, binders, reminders, notifications, signature_requests, and any other paginated list.
  - Scope: every affected repo, router, frontend hook, and `DataTable` column header — requires a design pass before implementation.

- [ ] Add free-text search to charges list (low priority).
  - Current state: no search param in repo or router.
  - Scope: ILIKE on joined client name + charge description; `app/charge/repositories/charge_repository.py`, `app/charge/api/charge.py`, frontend filter field.

## Cross-Domain: Pagination Audit

- [ ] Document bounded-but-unpaginated lists.
  - Severity: Low.
  - Current state: some endpoints intentionally return small bounded lists but do not document the bound.
  - Scope: `GET /advance-payments/overview/batches`, `GET /settings/tax-calendar/rules`, dashboard attention and recent activity widgets.
  - Recommended fix: add code comments or endpoint notes documenting the bound; for dashboard attention, push urgency filtering into the DB before applying the display cap.

## High

- [ ] Complete invoice provider integration.
  - Current state: invoice references can be attached internally, but there is no invoice API, provider client, or call from `BillingService.issue_charge()`.
  - Relevant code: `app/invoice/services/invoice_service.py`, `app/charge/services/billing_service.py`, `app/config.py`

- [ ] Add batched alert counts for client sidebar navigation.
  - Current state: notification/work-queue summaries exist per client, but no batched endpoint exists for all sidebar clients.
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
