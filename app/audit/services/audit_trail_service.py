"""Service layer for read-only entity audit trail queries.

Owns registry orchestration, scope interpretation, role authorization, the
sensitive-data hook, and audit->response mapping. All DB access is delegated to
repositories (the repos do DB only); the registry holds pure descriptors.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.audit.audit_constants import ENTITY_NOT_FOUND_ERROR, INVALID_ENTITY_TYPE_ERROR
from app.audit.audit_entity_registry import (
    AuditEntityDescriptor,
    ScopeStrategy,
    allowed_read_entity_types,
    get_descriptor,
)
from app.audit.audit_scope import (
    RESOLVED_FROM_AUDIT_METADATA,
    RESOLVED_FROM_LIVE,
    AuditScope,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.audit.repositories.audit_entity_audit_log_repository import EntityAuditLogRepository
from app.audit.repositories.audit_scope_repository import AuditScopeRepository
from app.audit.schemas.audit_entity_audit_log import (
    EntityAuditLogResponse,
    EntityAuditTrailResponse,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, ForbiddenError
from app.users.models.user import User, UserRole
from app.users.repositories.user_repository import UserRepository

# Both authenticated roles may read audit history; there is no lower-privilege
# authenticated role in the current model (§3a, §14).
_ALLOWED_AUDIT_ROLES = (UserRole.ADVISOR, UserRole.SECRETARY)


class AuditTrailService:
    def __init__(self, db: Session):
        self.db = db
        self.audit_repo = EntityAuditLogRepository(db)
        self.scope_repo = AuditScopeRepository(db)
        self.user_repo = UserRepository(db)

    # ALLOWED_READ_ENTITY_TYPES is derived from the registry (§3a/§6).
    @property
    def allowed_entity_types(self) -> frozenset[str]:
        return allowed_read_entity_types()

    def get_entity_audit_trail(
        self,
        entity_type: str,
        entity_id: int,
        page: int = 1,
        page_size: int = 20,
        *,
        current_user: User,
        action: str | None = None,
        user_id: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> EntityAuditTrailResponse:
        descriptor = self._require_descriptor(entity_type)

        filters = {
            "action": action,
            "user_id": user_id,
            "created_after": created_after,
            "created_before": created_before,
        }
        entries = self.audit_repo.get_audit_trail(
            entity_type, entity_id, page=page, page_size=page_size, **filters
        )
        total = self.audit_repo.count_audit_trail(entity_type, entity_id, **filters)
        history_exists = self.audit_repo.count_audit_trail(entity_type, entity_id) > 0

        scope = self._resolve_scope(descriptor, entity_id, history_exists)
        # 404 only when neither a live entity nor usable historical audit metadata exists.
        if scope is None:
            raise AppError(
                ENTITY_NOT_FOUND_ERROR, ErrorCode.AUDIT_ENTITY_NOT_FOUND, status_code=404
            )

        self._authorize(current_user)

        items = self._map_items(self._apply_sensitive_hook(descriptor, current_user, entries))
        return EntityAuditTrailResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            entity_deleted=scope.entity_deleted,
        )

    def _require_descriptor(self, entity_type: str) -> AuditEntityDescriptor:
        descriptor = get_descriptor(entity_type)
        if descriptor is None:
            raise AppError(INVALID_ENTITY_TYPE_ERROR, ErrorCode.AUDIT_INVALID_ENTITY_TYPE)
        return descriptor

    def _resolve_scope(
        self,
        descriptor: AuditEntityDescriptor,
        entity_id: int,
        history_exists: bool,
    ) -> AuditScope | None:
        resolution = self.scope_repo.resolve(descriptor, entity_id)
        if resolution.exists:
            return AuditScope(
                client_ids=resolution.client_ids,
                firm_level=resolution.firm_level,
                entity_deleted=resolution.deleted,
                resolved_from=RESOLVED_FROM_LIVE,
            )
        # Live row gone. Hard-deleted history stays readable only if audit rows
        # exist AND their scope is resolvable — otherwise 404. Scope is resolved
        # from ALL of the entity's audit rows (unfiltered), never the current
        # filtered/paged view.
        if not history_exists:
            return None
        all_rows = self.audit_repo.list_by_entity(descriptor.entity_type, entity_id)
        meta_client_ids = self._client_ids_from_metadata(all_rows)
        if descriptor.strategy == ScopeStrategy.SELF:
            client_ids: frozenset[int] = frozenset({entity_id})
        else:
            client_ids = meta_client_ids
        # "Usable history" = firm-level, a self-scoped entity (id is the client),
        # or audit metadata that actually carries a client_record_id.
        usable = (
            resolution.firm_level
            or descriptor.strategy == ScopeStrategy.SELF
            or bool(meta_client_ids)
        )
        if not usable:
            return None
        return AuditScope(
            client_ids=client_ids,
            firm_level=resolution.firm_level,
            entity_deleted=True,
            resolved_from=RESOLVED_FROM_AUDIT_METADATA,
        )

    @staticmethod
    def _client_ids_from_metadata(entries: list[EntityAuditLog]) -> frozenset[int]:
        ids: set[int] = set()
        for entry in entries:
            meta = entry.metadata_json
            if isinstance(meta, dict):
                value = meta.get("client_record_id")
                if isinstance(value, int):
                    ids.add(value)
                elif isinstance(value, str) and value.isdigit():
                    ids.add(int(value))
        return frozenset(ids)

    def _authorize(self, current_user: User) -> None:
        if current_user.role not in _ALLOWED_AUDIT_ROLES:
            raise ForbiddenError(ENTITY_NOT_FOUND_ERROR, ErrorCode.AUDIT_INVALID_ENTITY_TYPE)

    def _apply_sensitive_hook(
        self,
        descriptor: AuditEntityDescriptor,
        current_user: User,
        entries: list[EntityAuditLog],
    ) -> list[EntityAuditLog]:
        """Service-owned sensitive-data hook.

        Sensitive entity types (e.g. signature_request) carry forensic/PII in
        metadata. Under the current two-role model both ADVISOR and SECRETARY
        preserve the SAME allowed forensic fields, so this is a pass-through;
        forbidden data is rejected at write time and stored rows are never
        altered by reads. The hook is the single place a future lower-privilege
        role would redact.
        """
        del current_user  # same visibility for both current roles
        if not descriptor.sensitive:
            return entries
        # sensitive type: forensic fields preserved for both current roles
        return entries

    def _map_items(self, entries: list[EntityAuditLog]) -> list[EntityAuditLogResponse]:
        user_ids = list({e.performed_by for e in entries if e.performed_by is not None})
        users = self.user_repo.list_by_ids(user_ids) if user_ids else []
        user_map = {user.id: user.full_name for user in users}
        items = []
        for entry in entries:
            row = EntityAuditLogResponse.model_validate(entry)
            if entry.performed_by is not None:
                row.performed_by_name = user_map.get(entry.performed_by)
            items.append(row)
        return items
