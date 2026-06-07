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

- [ ] Paginate permanent document lists for client document tabs.
  - Severity: High.
  - Current state: `GET /documents/client/{id}` returns all client documents via `PermanentDocumentRepository.list_by_client_record()` with no `page`, `page_size`, or `total`.
  - Risk: long-running clients can accumulate hundreds of documents across years, businesses, and document types.
  - Scope: `app/permanent_documents/api/permanent_documents.py`, `app/permanent_documents/repositories/permanent_document_repository.py`, `app/permanent_documents/schemas/permanent_document.py`, `../frontend/src/features/documents/hooks/useClientDocumentsTab.ts`.
  - Recommended fix: add `page` / `page_size`, return `items`, `total`, `page`, `page_size`, and add frontend pagination controls.

- [ ] Add pagination to VAT compliance report.
  - Severity: High.
  - Current state: `GET /reports/vat-compliance` returns every VAT-active client for a year; report repositories load all rows with `.all()`.
  - Risk: firms with 100-200+ VAT clients return and render the whole report in one request.
  - Scope: `app/reports/api/reports.py`, `app/reports/services/vat_compliance_report.py`, `../frontend/src/features/reports/components/VatComplianceReportView.tsx`.
  - Recommended fix: add backend `page` / `page_size`, push filtering into DB where practical, return a paginated envelope, and add frontend pagination controls.

- [ ] Add pagination to aging report.
  - Severity: High.
  - Current state: `GET /reports/aging` returns all aging rows up to the internal `AGING_CHARGE_FETCH_LIMIT = 2000` cap.
  - Risk: a firm with many open charges renders a large card grid in one shot and the backend silently truncates at the internal cap.
  - Scope: `app/reports/api/reports.py`, `app/reports/services/reports_service.py`, `../frontend/src/features/reports/components/AgingReportTable.tsx`.
  - Recommended fix: replace the silent internal cap with explicit `page` / `page_size`, return a paginated envelope, and add frontend pagination controls or virtualization.

- [ ] Paginate binder intake history.
  - Severity: High.
  - Current state: `GET /binders/{id}/intakes` returns all intakes for a binder; intake material repository calls are unbounded.
  - Risk: long-lived binders can accumulate many intake events and materials.
  - Scope: `app/binders/api/binders_history.py`, `app/binders/repositories/binder_intake_repository.py`, `app/binders/repositories/binder_intake_material_repository.py`.
  - Recommended fix: add capped pagination or `limit` / `offset` consistent with existing audit history patterns.

- [ ] Paginate binder lifecycle history.
  - Severity: Medium.
  - Current state: `GET /binders/{id}/history` returns all lifecycle log rows via `BinderLifecycleLogRepository.list_by_binder()`.
  - Risk: frequently received and returned binders can build long audit histories.
  - Scope: `app/binders/api/binders_history.py`, `app/binders/repositories/binder_lifecycle_log_repository.py`.
  - Recommended fix: add capped pagination or `limit` / `offset` with a default around 50 and max around 200.

- [ ] Bound tax-calendar settings entries.
  - Severity: Medium.
  - Current state: `GET /settings/tax-calendar/entries` returns a bare list; `start_year` and `end_year` filters are optional.
  - Risk: unfiltered admin requests return every materialized entry across all years.
  - Scope: `app/tax_calendar/api/settings.py`, `app/tax_calendar/repositories/settings_repository.py`.
  - Recommended fix: require at least one year bound or convert to a paginated response envelope.

- [ ] Add a year range to VAT client summary periods.
  - Severity: Medium.
  - Current state: `GET /vat/clients/{id}/summary` fetches every `VatWorkItem` period for the client across all years.
  - Risk: monthly-reporting clients grow linearly with age.
  - Scope: `app/vat_reports/repositories/vat_client_summary_repository.py`, `app/vat_reports/services/vat_client_summary_service.py`, VAT client summary API/frontend callers.
  - Recommended fix: add `year`, `from_year`, or `to_year` filters, default to a bounded recent window, and document the endpoint contract. This is a range-filter issue, not ordinary pagination.

- [ ] Add visible pagination or load-more UI to client signature requests.
  - Severity: High.
  - Current state: `SignatureRequestsCard` uses `useClientSignatureRequests()` defaults (`page=1`, `pageSize=10`) and ignores `total`.
  - Risk: clients with more than 10 signature requests are silently truncated in the UI.
  - Scope: `../frontend/src/features/signatureRequests/components/SignatureRequestsCard.tsx`, `../frontend/src/features/signatureRequests/hooks/useClientSignatureRequests.ts`.
  - Recommended fix: add load-more or pagination controls and expose `total > items.length` clearly.

- [ ] Bound or paginate permanent document version history.
  - Severity: Medium.
  - Current state: `DocumentVersionsPanel` fetches and renders every version for a document type.
  - Risk: frequently replaced recurring documents can produce long inline version lists.
  - Scope: `app/permanent_documents/api/permanent_documents.py`, permanent document query repository/service, `../frontend/src/features/documents/components/DocumentVersionsPanel.tsx`.
  - Recommended fix: add a server-side limit such as the latest 10 versions plus an optional show-all/load-more flow.

- [ ] Document bounded-but-unpaginated lists.
  - Severity: Low.
  - Current state: some endpoints intentionally return small bounded lists but do not document the bound.
  - Scope: `GET /advance-payments/overview/batches`, `GET /settings/tax-calendar/rules`, dashboard attention and recent activity widgets.
  - Recommended fix: add code comments or endpoint notes documenting the bound; for dashboard attention, push urgency filtering into the DB before applying the display cap.

- [ ] Clean up API contract drift discovered during pagination audit.
  - Severity: Medium.
  - Current state: `GET /work-queue` uses `limit` / `offset`; `GET /binders` and `GET /clients/{id}/correspondence` use `sort_dir` instead of standard `order`.
  - Scope: `app/work_queue/api/routes.py`, `app/binders/api/binders_list_get.py`, `app/binders/repositories/binder_repository.py`, `app/correspondence/api/correspondence.py`, frontend callers.
  - Recommended fix: migrate callers to standard `page`, `page_size`, and `order`, then remove non-standard aliases.

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
