## Scope

This file owns only:

- Backend-local documentation ownership status.
- Pointers from old backend docs to the root project-wide docs layer.

This file must not contain:

- Project-wide agent behavior, frontend rules, cross-project decision policy, or domain documentation rewrites.

Source of truth: reference

# Backend Docs

## Audit Summary

Last audited against current backend code and `backend/openapi.json`: 2026-05-29.

Verified scope:

- Scoped docs under `backend/docs`, including domain docs, domain-model review docs, history/timeline docs, and the frontend screen spec kept in this backend docs tree.
- Current backend routes under `backend/app/**/api`, schemas under `backend/app/**/schemas`, models under `backend/app/**/models`, services under `backend/app/**/services`, repositories under `backend/app/**/repositories`, and OpenAPI paths where endpoint claims were present.

Canonical within this backend-local audit scope:

- `backend/domains/work-queue.md` — current Work Queue behavior.
- `domain_decisions_v3.md` — current tax-calendar/workflow anchoring decisions where explicitly marked as current.

Historical/reference-only docs:

- `backend/domains/advance_payments_spec.md`
- `backend/domains/annual_reports/annual_reports_summary.md`
- `backend/domains/annual_reports/report_history_financial_decision.md`
- `backend/domains/annual_reports/source-map.md`
- `backend/domains/binder_lifecycle_refactor_spec.md`
- `backend/domains/history-map.md`
- `backend/domains/vat_report/*`
- `domain_model/*`
- `frontend_screen_spec.md`
- `history-vs-timeline.md`

Reference-only docs are not active product or API contracts. If they mention future behavior, treat it as `Future / planned` unless current code and OpenAPI verify it.

## Future Audit Rules

- Follow root documentation precedence from `../../docs/project/documentation-map.md`: ADR > architecture > workflow > project > existing code. Backend docs are domain/reference docs and are lower authority than `../../docs/architecture/*`.
- Do not blindly rewrite a backend doc to match code. If a backend doc agrees with an ADR or architecture rule and current code differs, report the code as suspect instead of editing the doc to match code.
- Treat committed `../openapi.json` as the primary endpoint/schema contract for this docs tree. Compare route and schema claims against OpenAPI first, then use routers/schemas/models/services/repositories for implementation details that OpenAPI does not expose.
- When fixing a factual claim, record the checked source as `path:line` in the audit note or final report where practical.
- Do not choose canonical docs arbitrarily. Canonical means the file already identified by `../../docs/project/documentation-map.md`, the owning architecture doc, or the specific backend-domain doc that the map delegates to. If two backend docs overlap and neither is delegated, mark one reference/historical and point to the delegated or architecture source.
- For `frontend_screen_spec.md`, verify only backend-facing claims such as endpoints, response contracts, and backend permissions. Do not try to validate or normalize UI layout from this backend docs tree.
- Never delete a doc file during an audit. If material is obsolete but useful, keep it in a `Historical notes` or `Archive` section inside the same file; otherwise mark the whole file historical/reference.

Project-wide agent, architecture, workflow, and decision rules are canonical in the sibling docs repo:

- `../../docs/AGENTS.md`
- `../../docs/agent/entry-point.md`
- `../../docs/project/documentation-map.md`
- `../../docs/architecture/`
- `../../docs/workflow/`
- `../../docs/adr/`

Backend-local docs in this directory remain subordinate to root `docs/` authority. The canonical labels above mean they are the current backend-local source for that scoped domain behavior, not project-wide architecture policy.

Do not add project-wide agent behavior, frontend rules, or cross-project decision policy under `backend/docs/`.
