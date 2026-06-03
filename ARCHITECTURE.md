## Scope

This file owns only:

- Backend-local service/repository implementation patterns not covered by canonical rules.

This file must not contain:

- Project-wide architecture rules that override YM_Docs.
- Layer responsibilities, repository inventories, or rules already owned by the canonical docs.
- Frontend rules.
- Product/domain behavior.

Source of truth: reference

Canonical project-wide rules:

- `../docs/architecture/backend.md`
- `../docs/workflow/verification.md`

Related reference:

- `BaseRepository` CRUD primitives are inventoried in `../docs/project/backend-module-map.md`.

# Backend Architecture Reference

Backend-local implementation patterns for new backend work and incremental
refactors. Layer responsibilities, repository/service rules, the raw-SQL ban, and
the domain vertical slice are canonical in `../docs/architecture/backend.md`;
this file only records concrete patterns that the canonical rules do not specify.

## BaseService and transactions

Domain services should inherit from `BaseService` (`app/common/services/base_service.py`),
which exposes `transaction()`, `commit()`, and `rollback()`.

```python
from app.common.services.base_service import BaseService


class SomeService(BaseService):
    ...
```

Services are the only layer that should call `commit()`, `rollback()`, or
`transaction()`, run external side effects after persistence validation, and
orchestrate across repositories.

Recommended write pattern:

```python
def create_item(self, payload: ItemCreate, actor_id: int) -> ItemResponse:
    with self.transaction():
        self._validate_create(payload)
        item = self.item_repo.create(**payload.model_dump(), created_by=actor_id)
    return ItemResponse.model_validate(item)
```

Repositories flush so generated IDs are available inside a service transaction.
They do not commit.

## Read-Side Pattern

Two repository categories are in use:

- `Repository`: write-model repository for one aggregate root.
- `ReadRepository`: optimized read methods that still return ORM models or typed
  projection dataclasses (for example `app/clients/repositories/client_record_read_repository.py`).

For complex views such as `ClientRecord + LegalEntity + Person`, prefer a
specialized read repository plus a typed projection dataclass. Use a specialized
read repository when the query is domain-specific or needs runtime filters,
permissions, pagination, or computed columns.

Use a database view only when the shape is stable, heavily reused outside one
domain, and worth migrating through Alembic. Do not use a DB view for business
logic or derived UX state such as `signals` or `urgency`.

> Target state (not yet in code): a shared `QueryBuilder` (`<aggregate>_query.py`)
> for select builders reused across multiple read repositories.
