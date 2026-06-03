## Scope

This file owns only:

- A pointer to the canonical binder domain doc and archive.

Source of truth: historical

Historical. Canonical domain doc: `docs/domains/binders.md`. Archived original: `docs/archive/binders-legacy.md`.

# Binder Lifecycle Refactor — Task Spec

Status: completed refactor notes, not an active task list.

Current implementation verified 2026-05-29:

- `Binder` has `location_status` and `capacity_status`; no `Binder.status` field exists.
- `BinderLocationStatus`: `in_office`, `ready_for_handover`, `handed_over`.
- `BinderCapacityStatus`: `open`, `full`.
- `BinderLifecycleLog` stores `field_name`, `old_value`, `new_value`, `changed_by_user_id`, `changed_at`, and `notes`.
- Current lifecycle endpoints exist:
  - `POST /api/v1/binders/{binder_id}/receive-material`
  - `POST /api/v1/binders/{binder_id}/mark-full`
  - `POST /api/v1/binders/{binder_id}/reopen-capacity`
  - `POST /api/v1/binders/{binder_id}/mark-ready-for-handover`
  - `POST /api/v1/binders/{binder_id}/revert-ready-for-handover`
  - `POST /api/v1/binders/{binder_id}/handover-to-client`
- Additional current bulk/intake endpoints also exist: `POST /api/v1/binders/receive`, `POST /api/v1/binders/mark-ready-for-handover-bulk`, and `POST /api/v1/binders/handover-to-client-bulk`.
- This document still contains historical implementation prompts and acceptance criteria below. They are retained as historical notes only.

## Goal

Refactor the binder lifecycle model from one mixed `status` field into two explicit domain fields:

```text
location_status
capacity_status
```

The current `Binder.status` mixes two different concepts:

1. Physical/process location of the binder.
2. Whether the binder can still receive material.

This refactor must make those concepts explicit and enforce all transitions through one backend state machine.

---

## Execution Principle

Start from backend domain correctness.
Do not update the frontend first.
The frontend must follow the finalized backend contract, not invent temporary lifecycle semantics.

After backend implementation, export/regenerate OpenAPI before touching frontend types.

Do not leave TODOs for reconnecting old lifecycle behavior later.
In this breaking refactor, TODOs around old `status` / `ready` / `pickup` / `return` semantics are new legacy and are not acceptable.

---

## Breaking Change Policy

Use clean breaking changes.

The system is still in development.
There are no real production users and no production data that must be preserved.
No backward compatibility is required.

Do not preserve `Binder.status`.
Do not map old statuses.
Do not keep old endpoint names.
Do not keep old status log table.
Do not keep `ready` / `return` / `returned` / `pickup` terminology for binder lifecycle APIs.
Do not keep legacy aliases, wrappers, deprecated fields, or compatibility layers.

Local seed/demo data may break.
Do not add legacy mapping for it.
Update seeders to emit the new fields directly.

---

## New Domain Model

### `location_status`

```text
in_office
ready_for_handover
handed_over
```

Meaning:

```text
in_office          = binder is physically/process-wise in the office
ready_for_handover = binder is prepared for handover to the client
handed_over        = binder was handed over to the client
```

### `capacity_status`

```text
open
full
```

Meaning:

```text
open = binder is not full
full = binder is full
```

Important distinction:

```text
open is only a capacity value.
It does not mean material intake is currently allowed.
```

The only intake-operational state is:

```text
location_status = in_office
capacity_status = open
```

---

## Hebrew Labels

Backend returns values only.
Backend does not return Hebrew labels.
Backend does not know UI translations.

Frontend owns Hebrew labels in one constants file.

```ts
export const BINDER_LOCATION_STATUS_LABELS = {
  in_office: "במשרד",
  ready_for_handover: "מוכן למסירה",
  handed_over: "נמסר ללקוח",
} as const;

export const BINDER_CAPACITY_STATUS_LABELS = {
  open: "פתוח",
  full: "מלא",
} as const;
```

Frontend tests must not rely on Hebrew labels for lifecycle logic.

---

## Final API Endpoints

Remove old lifecycle endpoints and terminology.

Use these endpoints only:

```text
POST /api/v1/binders/{binder_id}/receive-material
POST /api/v1/binders/{binder_id}/mark-full
POST /api/v1/binders/{binder_id}/reopen-capacity
POST /api/v1/binders/{binder_id}/mark-ready-for-handover
POST /api/v1/binders/{binder_id}/revert-ready-for-handover
POST /api/v1/binders/{binder_id}/handover-to-client
```

Do not keep endpoint names such as:

```text
ready
revert-ready
return
return_binder
ready_for_pickup
pickup
returned
```

---

## Available Actions

Backend returns available actions.
Frontend displays actions from backend.
Frontend may hide buttons for UX convenience, but backend is the source of truth.

Final action names:

```ts
export type BinderAction =
  | "receive_material"
  | "mark_full"
  | "reopen_capacity"
  | "mark_ready_for_handover"
  | "revert_ready_for_handover"
  | "handover_to_client";
```

Rule:

```text
get_available_actions(binder) must be derived in backend from the same state machine used by BinderLifecycleService.
Frontend may display/hide actions, but must not duplicate transition authority.
```

---

## Central Architecture Rule

All binder lifecycle and capacity transitions must go through `BinderLifecycleService`.

No router, repository, generic update endpoint, seed/demo helper, or cross-domain service may mutate these fields directly:

```text
location_status
capacity_status
```

Do not expose a generic update endpoint that can modify `location_status` or `capacity_status`.

`BinderLifecycleService` owns:

```text
- state machine validation
- domain error codes
- mutation of location_status / capacity_status
- audit log writing
- side effects such as notifications
```

Recommended service surface:

```python
class BinderLifecycleService:
    def receive_material(...):
        ...

    def mark_full(...):
        ...

    def reopen_capacity(...):
        ...

    def mark_ready_for_handover(...):
        ...

    def revert_ready_for_handover(...):
        ...

    def handover_to_client(...):
        ...
```

---

## State Machine Rules

### Receive material

Allowed only for:

```text
in_office + open
```

Blocked for all other combinations.

Error:

```text
BINDER.NOT_INTAKE_ELIGIBLE
```

---

### Mark full

Allowed only for:

```text
in_office + open
```

Effect:

```text
capacity_status = full
```

Errors:

```text
BINDER.ALREADY_FULL
BINDER.CAPACITY_CHANGE_NOT_ALLOWED
```

Rules:

```text
- if already full: BINDER.ALREADY_FULL
- if location_status is not in_office: BINDER.CAPACITY_CHANGE_NOT_ALLOWED
- do not silently no-op
```

---

### Reopen capacity

Allowed only for:

```text
in_office + full
```

Effect:

```text
capacity_status = open
```

Errors:

```text
BINDER.NOT_FULL
BINDER.CAPACITY_CHANGE_NOT_ALLOWED
```

Rules:

```text
- if already open: BINDER.NOT_FULL
- if location_status is not in_office: BINDER.CAPACITY_CHANGE_NOT_ALLOWED
```

---

### Mark ready for handover

Allowed for:

```text
in_office + open
in_office + full
```

Effect:

```text
location_status = ready_for_handover
capacity_status is preserved
```

Blocked for:

```text
ready_for_handover + *
handed_over + *
```

Error:

```text
BINDER.INVALID_LOCATION_TRANSITION
```

Important:

```text
Do not force capacity_status=full when moving to ready_for_handover.
A binder may be ready for handover even if it is not full.
```

---

### Revert ready for handover

Allowed for:

```text
ready_for_handover + open
ready_for_handover + full
```

Effect:

```text
location_status = in_office
capacity_status is preserved
```

Blocked for:

```text
handed_over + *
```

Error:

```text
BINDER.INVALID_LOCATION_TRANSITION
```

---

### Handover to client

Allowed only for:

```text
ready_for_handover + open
ready_for_handover + full
```

Effect:

```text
location_status = handed_over
capacity_status is preserved
```

Errors:

```text
BINDER.NOT_READY_FOR_HANDOVER
BINDER.ALREADY_HANDED_OVER
```

Rules:

```text
- if not ready_for_handover: BINDER.NOT_READY_FOR_HANDOVER
- if already handed_over: BINDER.ALREADY_HANDED_OVER
```

---

### After handover

Never move the same binder back to `in_office` for new material.

If new material arrives after handover:

```text
create a new binder
```

Do not reuse the handed-over binder.
This prevents physical/process history from becoming misleading.

---

## Intake Eligibility

Only this state is eligible for material intake:

```text
location_status = in_office
capacity_status = open
```

All intake lookup queries must use this exact definition.

Do not treat `capacity_status=open` as intake eligibility by itself.

Recommended naming:

```text
intake_eligible_binder
```

Avoid undefined names like:

```text
active binder
```

unless explicitly defined as `in_office + open`.

---

## Domain Error Codes

Use fixed domain error codes.
Frontend and tests must assert error codes, not Hebrew text.

```text
BINDER.NOT_INTAKE_ELIGIBLE
Raised when trying to receive material into a binder that is not:
location_status=in_office and capacity_status=open

BINDER.ALREADY_FULL
Raised when trying to mark a binder as full while capacity_status=full

BINDER.NOT_FULL
Raised when trying to reopen capacity while capacity_status=open

BINDER.CAPACITY_CHANGE_NOT_ALLOWED
Raised when trying to change capacity_status while location_status is not in_office

BINDER.INVALID_LOCATION_TRANSITION
Raised for unsupported location_status transitions

BINDER.NOT_READY_FOR_HANDOVER
Raised when trying to hand over a binder that is not ready_for_handover

BINDER.ALREADY_HANDED_OVER
Raised when trying to modify lifecycle state of a handed_over binder where the action is not explicitly allowed
```

---

## Audit Log

Replace old status logging.

Remove old `BinderStatusLog` shape:

```text
old_status
new_status
```

Replace with:

```text
BinderLifecycleLog:
- binder_id
- field_name: location_status | capacity_status
- old_value
- new_value
- changed_by_user_id
- changed_at
- notes/reason if available
```

Every transition must write an audit log entry for each changed field.

Examples:

```text
mark_full:
field_name = capacity_status
old_value = open
new_value = full

mark_ready_for_handover:
field_name = location_status
old_value = in_office
new_value = ready_for_handover
```

Do not log generic `status changed` events.
They are not precise enough.

---

## Repository Rules

Repository is technical only.

Allowed responsibilities:

```text
- get_by_id_for_update
- save/update fields only when called explicitly by service
- append audit log
- queries/filtering/counters
```

Forbidden responsibilities:

```text
- transition validation
- permission logic
- allowed action logic
- if status then...
- can transition...
```

No repository method should mutate `location_status` or `capacity_status` as an independent business decision.

---

## API Response Contract

Binder responses must return:

```json
{
  "location_status": "in_office",
  "capacity_status": "open"
}
```

Do not return:

```json
{
  "status": "..."
}
```

Do not accept `status` in payloads or filters.

OpenAPI must not expose old binder `status` fields, old status enums, old lifecycle routes, or old log schemas.

---

## Frontend Requirements

Remove:

```text
status
BINDER_STATUS_VALUES
BINDER_STATUS_LABELS
canMarkReady(status)
ready/return/pickup terminology
```

Add/use:

```text
location_status
capacity_status
BINDER_LOCATION_STATUS_LABELS
BINDER_CAPACITY_STATUS_LABELS
available_actions
```

UI should show two badges:

```text
מיקום: במשרד / מוכן למסירה / נמסר ללקוח
קיבולת: פתוח / מלא
```

Filters should be split:

```text
מיקום
קיבולת
```

Frontend must not be the source of truth for lifecycle permission.
It renders backend `available_actions`.
Backend still enforces every transition.

---

## Useful Views

Recommended backend/frontend views:

```text
intake: in_office + open
full in office: in_office + full
waiting for handover: ready_for_handover + *
handed over: handed_over + *
```

---

## Database / Migration

Use clean breaking migration.

Recommended migration direction:

```text
- drop binders.status
- drop old binder status enum
- drop/replace old binder_status_logs table
- create enum binder_location_status
- create enum binder_capacity_status
- add binders.location_status not null default 'in_office'
- add binders.capacity_status not null default 'open'
- create binder_lifecycle_logs
```

No legacy data mapping is required.

Seed/demo data must be updated to write:

```text
location_status
capacity_status
```

directly.

---

## DB Schema Acceptance

No database column, enum, index, constraint, or table name may use old binder lifecycle terminology.

Remove old names:

```text
ready_for_pickup_at
returned_at
binder_status_logs
idx_binder_status
binderstatus enum
binder_status enum
```

Use new names:

```text
ready_for_handover_at
handed_over_at
binder_lifecycle_logs
idx_binder_location_status
idx_binder_capacity_status
binder_location_status enum
binder_capacity_status enum
```

---

## Indexes / Querying

Add indexes based on actual query patterns:

```text
location_status
capacity_status
(location_status, capacity_status) if used for intake/full/waiting views
```

All queries that find a binder for material intake must use:

```text
location_status = in_office
capacity_status = open
```

No query may treat `capacity_status=open` as enough for intake eligibility.

---

## Cross-Domain Consumers

Update all consumers outside the binder model itself.

Examples:

```text
- Dashboard
- quick actions
- Work Queue
- Timeline events
- Notifications
- reminder templates
- docs
```

Requirements:

```text
- Dashboard and quick actions do not use status, ready_for_pickup, pickup, returned, or return_binder.
- Work queue uses location_status and capacity_status only.
- Timeline events use ready_for_handover / handover_to_client terminology.
- Notifications use handover terminology only.
- No notification/template/reminder references pickup terminology.
```

---

## Naming Cleanup

Remove/rename old lifecycle names:

```text
return_binder
ready_for_pickup_at
pickup_person_name
pickup_reminder
returned_at
ready_for_pickup
pickup
returned
```

Use new names:

```text
ready_for_handover_at
handed_over_at
handover_recipient_name
handover_reminder
ready_for_handover
handover_to_client
handed_over
```

---

## Docs

Update docs where relevant:

```text
- binders domain docs
- API docs
- state machine docs
- frontend labels/actions docs if they exist
```

Docs must include one state machine table as the source of truth.

Docs must explicitly state:

```text
open is capacity only.
intake eligibility is only in_office + open.
```

---

## Implementation Order

Follow this order:

```text
1. Backend model + enums
2. Alembic migration / DB schema cleanup
3. BinderLifecycleService state machine
4. Repository cleanup
5. Router endpoints
6. Schemas + OpenAPI
7. Backend tests
8. Seed/demo update
9. Frontend API types/constants
10. Frontend screens/actions/filters
11. Cross-domain cleanup
12. Docs
13. Static hardening checks
```

Do not start with frontend.
Backend domain correctness comes first.

---

## Acceptance Criteria

### Backend

```text
- Binder model has no status field.
- BinderStatus enum is deleted.
- Binder has location_status and capacity_status only.
- API responses do not include status.
- API payloads/filters do not accept status.
- Old ready/return/pickup endpoints do not exist.
- New lifecycle endpoints exist and call BinderLifecycleService only.
- No direct mutation of location_status/capacity_status outside BinderLifecycleService.
- available_actions is returned from backend and derived from the same state machine.
- BinderLifecycleLog replaces old BinderStatusLog.
- Every lifecycle/capacity transition writes an audit log entry.
- Domain errors return fixed error codes.
```

### Frontend

```text
- No usage of binder.status remains.
- No BINDER_STATUS_* constants remain.
- UI shows two badges: location_status and capacity_status.
- Filters are split into location and capacity.
- Actions are rendered from available_actions.
- Hebrew labels live in one constants file.
- Frontend logic/tests do not rely on Hebrew labels.
```

### Migration / Data

```text
- Clean breaking migration drops old status column.
- Old status log table is removed/replaced.
- New enums/tables/columns are created.
- Seed/demo data writes location_status and capacity_status directly.
- No legacy status mapping exists.
```

### Tests

```text
- transition success cases covered
- invalid transition error codes covered
- available_actions per state covered
- audit logs covered
- API contract does not expose/accept status
- frontend logic does not rely on Hebrew labels
```

---

## Backend Sanity Checks

Run binder tests:

```bash
JWT_SECRET=test-secret pytest -q tests/binders
```

Export OpenAPI by starting the server in the background and stopping it afterwards:

```bash
APP_ENV=development ENV_FILE=.env.development python -m app.main &
SERVER_PID=$!

for i in {1..20}; do
  if curl -sf http://localhost:8000/openapi.json > openapi.json; then
    break
  fi
  sleep 1
done

kill $SERVER_PID
```

Manual review aid only:

```bash
rg "status|ready_for_pickup|pickup|returned|return_binder" app/binders tests/binders openapi.json
```

Important:

```text
The broad "status" search is a manual review aid only.
It is not a strict pass/fail check because status is a generic term.
```

Strict backend legacy checks:

```bash
rg "ready_for_pickup|pickup|returned|return_binder|BinderStatus|BinderStatusLog" app tests docs --glob '!docs/binder_lifecycle_refactor_spec.md'
rg "old_status|new_status|binder_status_logs|ready_for_pickup_at|returned_at" app tests docs alembic --glob '!docs/binder_lifecycle_refactor_spec.md'
rg "ready_for_pickup|pickup|returned|return_binder|BinderStatus|BinderStatusLog|old_status|new_status|binder_status_logs|ready_for_pickup_at|returned_at" openapi.json
```

Strict pass/fail legacy checks must use binder-specific old lifecycle terms only:

```text
ready_for_pickup|pickup|returned|return_binder|BinderStatus|BinderStatusLog|old_status|new_status|binder_status_logs|ready_for_pickup_at|returned_at
```

---

## Frontend Sanity Checks

From frontend directory:

```bash
cd ../frontend
npm run typecheck
npm run test -- binders
```

Manual review aid only because `status` is generic:

```bash
rg "status|BINDER_STATUS|ready_for_pickup|pickup|returned|return_binder" src/features/binders
```

Strict frontend legacy checks:

```bash
rg "ready_for_pickup|pickup|returned|return_binder|BINDER_STATUS|ready_for_pickup_at|returned_at" src/features/binders
```

---

## Final Notes

Do not skip the strict `rg` checks at the end.
Most leftover legacy semantics will be found there.

The goal is not only to change the database model.
The goal is to remove the old lifecycle language and enforce one explicit state machine across backend, API, frontend, tests, seed/demo data, docs, and cross-domain consumers.

---

## Prompt For A New Codex Conversation

Historical notes. Do not use this as a current implementation prompt unless first re-audited against code and OpenAPI.

Use this prompt in a fresh conversation to implement the refactor:

```text
Implement the binder lifecycle refactor from docs/binder_lifecycle_refactor_spec.md.

Start from backend domain correctness.
Do not update the frontend first.
The frontend must follow the finalized backend contract, not invent temporary lifecycle semantics.

After backend implementation, export/regenerate OpenAPI before touching frontend types.

Use clean breaking changes.
Do not preserve Binder.status.
Do not map old statuses.
Do not keep old endpoint names.
Do not keep old status log table.
Do not keep ready/return/returned/pickup terminology for binder lifecycle APIs.
Do not keep legacy aliases, wrappers, deprecated fields, or compatibility layers.
Do not leave TODOs for reconnecting old lifecycle behavior later.

Replace Binder.status with:

location_status:
- in_office
- ready_for_handover
- handed_over

capacity_status:
- open
- full

open is only a capacity value.
The only intake-operational state is:
location_status=in_office + capacity_status=open.

All lifecycle and capacity transitions must go through BinderLifecycleService.
No router, repository, generic update endpoint, seed/demo helper, or cross-domain service may mutate location_status or capacity_status directly, except through BinderLifecycleService.
Do not expose a generic update endpoint that can modify location_status or capacity_status.

BinderLifecycleService must own:
- state machine validation
- fixed domain error codes
- mutation of location_status / capacity_status
- audit log writing
- side effects such as notifications

Required service methods:
- receive_material(...)
- mark_full(...)
- reopen_capacity(...)
- mark_ready_for_handover(...)
- revert_ready_for_handover(...)
- handover_to_client(...)

Final endpoints:
- POST /api/v1/binders/{binder_id}/receive-material
- POST /api/v1/binders/{binder_id}/mark-full
- POST /api/v1/binders/{binder_id}/reopen-capacity
- POST /api/v1/binders/{binder_id}/mark-ready-for-handover
- POST /api/v1/binders/{binder_id}/revert-ready-for-handover
- POST /api/v1/binders/{binder_id}/handover-to-client

Final available_actions:
- receive_material
- mark_full
- reopen_capacity
- mark_ready_for_handover
- revert_ready_for_handover
- handover_to_client

get_available_actions(binder) must be derived in backend from the same state machine used by BinderLifecycleService.
Frontend may display/hide actions, but must not duplicate transition authority.

Backend returns values only.
Backend does not return Hebrew labels.
Backend does not know UI translations.

Frontend owns Hebrew labels in one constants file:
- location_status.in_office = במשרד
- location_status.ready_for_handover = מוכן למסירה
- location_status.handed_over = נמסר ללקוח
- capacity_status.open = פתוח
- capacity_status.full = מלא

Domain error codes:
- BINDER.NOT_INTAKE_ELIGIBLE
- BINDER.ALREADY_FULL
- BINDER.NOT_FULL
- BINDER.CAPACITY_CHANGE_NOT_ALLOWED
- BINDER.INVALID_LOCATION_TRANSITION
- BINDER.NOT_READY_FOR_HANDOVER
- BINDER.ALREADY_HANDED_OVER

Transition rules:

receive material:
- allowed only for in_office + open
- blocked for all other combinations
- error: BINDER.NOT_INTAKE_ELIGIBLE

mark full:
- allowed only for in_office + open
- sets capacity_status = full
- if already full: BINDER.ALREADY_FULL
- if not in_office: BINDER.CAPACITY_CHANGE_NOT_ALLOWED
- do not silently no-op

reopen capacity:
- allowed only for in_office + full
- sets capacity_status = open
- if already open: BINDER.NOT_FULL
- if not in_office: BINDER.CAPACITY_CHANGE_NOT_ALLOWED

mark ready for handover:
- allowed for in_office + open
- allowed for in_office + full
- sets location_status = ready_for_handover
- preserves capacity_status
- blocked for ready_for_handover or handed_over
- error: BINDER.INVALID_LOCATION_TRANSITION

revert ready for handover:
- allowed for ready_for_handover + open/full
- sets location_status = in_office
- preserves capacity_status
- blocked for handed_over
- error: BINDER.INVALID_LOCATION_TRANSITION

handover to client:
- allowed only for ready_for_handover + open/full
- sets location_status = handed_over
- preserves capacity_status
- if not ready_for_handover: BINDER.NOT_READY_FOR_HANDOVER
- if already handed_over: BINDER.ALREADY_HANDED_OVER

after handover:
- never move the same binder back to in_office for new material
- if new material arrives, create a new binder

Replace BinderStatusLog with BinderLifecycleLog:
- binder_id
- field_name: location_status | capacity_status
- old_value
- new_value
- changed_by_user_id
- changed_at
- notes/reason if available

Every transition must write an audit log entry for each changed field.

Repository rules:
- persistence/query helpers only
- no transition logic
- no permission logic
- no allowed action logic

DB schema:
- no column, enum, index, constraint, or table name may use old binder lifecycle terminology
- remove ready_for_pickup_at, returned_at, binder_status_logs, idx_binder_status, binderstatus/binder_status enum
- use ready_for_handover_at, handed_over_at, binder_lifecycle_logs, idx_binder_location_status, idx_binder_capacity_status, binder_location_status enum, binder_capacity_status enum

Update:
- backend models
- Alembic migration
- repositories
- BinderLifecycleService
- routers
- schemas/OpenAPI
- available_actions
- audit logging
- backend tests
- seed/demo data
- frontend API contracts/types
- frontend constants
- frontend screens/actions/filters
- cross-domain consumers
- docs

Implementation order:
1. Backend model + enums
2. Alembic migration / DB schema cleanup
3. BinderLifecycleService state machine
4. Repository cleanup
5. Router endpoints
6. Schemas + OpenAPI
7. Backend tests
8. Seed/demo update
9. Frontend API types/constants
10. Frontend screens/actions/filters
11. Cross-domain cleanup
12. Docs
13. Static hardening checks

Run the acceptance checks and sanity checks from docs/binder_lifecycle_refactor_spec.md before finishing.
Treat old lifecycle terminology matches as blockers, except where the spec explicitly marks a command as a manual review aid or excludes the spec file itself.
```
