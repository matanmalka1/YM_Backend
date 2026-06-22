## Scope

This file owns only:
- A reference-only index of backend-local docs that still live under `backend/docs/`.
- Pointers to canonical documentation in the sibling `docs/` repo.

This file must not contain:
- Project-wide agent behavior, frontend rules, cross-project decision policy, or canonical domain rules.

Source of truth: reference

# Backend Docs

Backend-local docs in this directory are historical/reference unless a current canonical doc explicitly delegates to them.

Canonical docs live in the sibling docs repo:

- Domain behavior: `../../docs/domains/`
- Domain index: `../../docs/domains/README.md`
- Documentation ownership map: `../../docs/project/documentation-map.md`
- Backend architecture/rules: `../../docs/backend/`
- Cross-stack architecture: `../../docs/architecture/`
- Workflow and verification: `../../docs/workflow/`
- ADRs: `../../docs/adr/`

## Backend-Local Reference Files

- `domain_decisions_v3.md` — historical/current decision notes for tax-calendar/workflow anchoring. Use only as reference; canonical current behavior belongs in `../../docs/domains/*`, `../../docs/project/tax-rules-config.md`, and current code.
- `domain_model/README.md` — reference pointer for domain-model review material.
- `domain_model/DOMAIN_MODEL_REVIEW_SUMMARY.md` — review notes and open gaps; not canonical product behavior.
- `frontend_screen_spec.md` — legacy unverified frontend screen inventory kept in backend docs for reference only. Current frontend rules live in `../../docs/frontend/`; current product behavior lives in `../../docs/domains/`.

Reference-only docs are not active product or API contracts. If they mention future behavior, treat it as `Future / planned` unless current code, OpenAPI, and the canonical docs verify it.

Do not add project-wide agent behavior, frontend rules, or cross-project decision policy under `backend/docs/`.
