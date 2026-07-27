## Scope

This file owns only:

- Implemented backend behavior for the annual reports domain.
- Current service, repository, model, and API ownership boundaries for this domain.

This file must not contain:

- Historical implementation plans.
- Future product behavior that is not implemented.
- Cross-domain architecture rules.

Source of truth: mandatory

> **Canonical doc:** [`docs/domains/annual-reports.md`](../../../docs/domains/annual-reports.md)

# Annual Reports Domain

> Last audited: 2026-04-21

## Tests

```bash
JWT_SECRET=test-secret ./.venv/bin/python -m pytest -q tests/annual_reports
```

## Open Tasks

Ordered by severity.

- [x] **[HIGH]** `submission_method` and `extension_reason` not persisted in create/submit — fixed in `create_service.py` and `status_service.py`
- [x] **[HIGH]** `deadline_sync.py` called `db.commit()` inside side-effect — removed; outer transaction commits at request boundary
- [x] **[HIGH]** `amend_report()` bypassed `transition_status()` — now routes through it (row-level lock, audit log)
- [x] **[MEDIUM]** `AnnualReportScheduleEntry` uniqueness on `(annual_report_id, schedule)` enforced in model and migration `0006`
- [x] **[HIGH]** Signature request silently not created when client has no businesses — fixed; SR is no longer business-scoped (`annual_report_status_signature_helper.py:77` passes `business_id=None`)
- [ ] **[HIGH]** `total_liability` in `TaxCalculationResponse` adds VAT balance to income-tax liability — remove from sum; expose VAT balance as separate informational field
- [ ] **[HIGH]** 2026 NI ceiling in `ni_engine.py` is `622_920` — verify against 2026 NII circular
- [ ] **[HIGH]** 2026 tax brackets in `tax_engine.py` — 5th-bracket ceiling appears lower than 2025; verify against 2026 ITA circular
- [ ] **[HIGH]** Readiness check uses stale `tax_due/refund_due` — income/expense mutations already call `_invalidate_tax_if_open` but readiness gate still reads persisted values; ensure gate fails when values are cleared
- [x] **[HIGH]** `VatImportService.auto_populate` aggregates by `client_record_id` — **accepted design.** Annual reports are client-scoped; Business is activity grouping only. Client-wide aggregation is correct. Do not add `business_id`. See `docs/domains/annual-reports.md` Decisions section and `test_vat_auto_populate_aggregates_all_businesses_for_client_year`.
- [x] **[MEDIUM]** `amend_report()` lives in `query_service.py` — fixed; now at `annual_report_status_service.py:300`
- [x] **[MEDIUM]** `business_name` in `AnnualReportResponse` always equals `client.full_name` — fixed; no longer present in any annual-report schema or service
- [ ] **[MEDIUM]** `advances_summary_service.py` and `get_detail_report` independently compute final balance — consolidate. They also disagree in source: `query_service.py:150` uses the SQL aggregate `sum_paid_by_client_year`, while `advances_summary_service.py:48` sums `paid_amount` in Python over a `page_size=10000` read
- [x] **[MEDIUM]** `AnnualReportAnnexData.line_number` — fixed; `UniqueConstraint(schedule_entry_id, line_number)` plus existing `(annual_report_id, schedule)` uniqueness on `annual_report_schedules` gives per-report-per-schedule uniqueness
- [ ] **[MEDIUM]** `DONATION_MINIMUM_ILS = 190` — verify against current ITA Section 46 indexed amount (may be 180 ILS for 2024)
- [ ] **[MEDIUM]** Signature creation runs inside the status transition transaction — failure rolls back the status change; decouple or wrap in try/except
- [ ] **[LOW]** `AnnualReportDetail.updated_at` is `nullable=True` — change to `nullable=False, default=utcnow` with backfill migration
