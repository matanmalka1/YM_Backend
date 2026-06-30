"""Scope value objects for audit reads (pure data — no SQL, no model imports)."""

from __future__ import annotations

from dataclasses import dataclass

RESOLVED_FROM_LIVE = "live_table"
RESOLVED_FROM_AUDIT_METADATA = "audit_metadata"


@dataclass(frozen=True)
class EntityScopeResolution:
    """Repository output: live-table existence + owning client(s) for one entity."""

    exists: bool
    deleted: bool
    client_ids: frozenset[int]
    firm_level: bool


@dataclass(frozen=True)
class AuditScope:
    """Service-interpreted scope for an audit read."""

    client_ids: frozenset[int]
    firm_level: bool
    entity_deleted: bool
    resolved_from: str  # RESOLVED_FROM_LIVE | RESOLVED_FROM_AUDIT_METADATA
