"""DB access for resolving an audited entity's live existence + owning client(s).

This is the only place audit scope resolution touches the database (the registry
holds pure descriptors and the service orchestrates). Cross-domain models are
imported for scoping joins only, which the architecture allows. Lookups use
``Session.get`` / unfiltered selects so they include soft-deleted rows — audit
history must stay readable after deletion and never applies the active-client
filter.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.audit_entity_registry import (
    AuditEntityDescriptor,
    ScopeStrategy,
    get_descriptor,
)
from app.audit.audit_scope import EntityScopeResolution
from app.charges.models.charge import Charge
from app.clients.models.client_record import ClientRecord
from app.legal_entities.models.legal_entity import LegalEntity
from app.legal_entities.models.person_legal_entity_link import PersonLegalEntityLink
from app.vat.models.vat_work_item import VatWorkItem


class AuditScopeRepository:
    def __init__(self, db: Session):
        self.db = db

    def resolve(self, descriptor: AuditEntityDescriptor, entity_id: int) -> EntityScopeResolution:
        if descriptor.strategy == ScopeStrategy.FIRM_LEVEL:
            row = self._get(descriptor.model, entity_id)
            return EntityScopeResolution(
                exists=row is not None,
                deleted=self._is_deleted(row),
                client_ids=frozenset(),
                firm_level=True,
            )

        row = self._get(descriptor.model, entity_id)
        if row is None:
            return EntityScopeResolution(False, False, frozenset(), False)

        return EntityScopeResolution(
            exists=True,
            deleted=self._is_deleted(row),
            client_ids=self._client_ids(descriptor, row),
            firm_level=False,
        )

    def _get(self, model: type[Any], entity_id: int) -> Any | None:
        # Session.get is identity-map-aware and returns soft-deleted rows too.
        return self.db.get(model, entity_id)

    @staticmethod
    def _is_deleted(row: Any | None) -> bool:
        return row is not None and getattr(row, "deleted_at", None) is not None

    def _client_ids(self, descriptor: AuditEntityDescriptor, row: Any) -> frozenset[int]:
        strategy = descriptor.strategy
        if strategy == ScopeStrategy.SELF:
            return frozenset({row.id})
        if strategy == ScopeStrategy.CLIENT_COLUMN:
            value = getattr(row, "client_record_id", None)
            return frozenset({value}) if value is not None else frozenset()
        if strategy == ScopeStrategy.VIA_LEGAL_ENTITY:
            return self._clients_for_legal_entity(row.legal_entity_id)
        if strategy == ScopeStrategy.LEGAL_ENTITY:
            return self._clients_for_legal_entity(row.id)
        if strategy == ScopeStrategy.PERSON_LINK:
            return self._clients_for_legal_entity(row.legal_entity_id)
        if strategy == ScopeStrategy.PERSON:
            return self._clients_for_person(row.id)
        if strategy == ScopeStrategy.VIA_CHARGE:
            return self._client_via(Charge, row.charge_id)
        if strategy == ScopeStrategy.VIA_WORK_ITEM:
            return self._client_via(VatWorkItem, row.work_item_id)
        if strategy == ScopeStrategy.VIA_BINDER:
            from app.binders.models.binder import Binder

            return self._client_via(Binder, row.binder_id)
        if strategy == ScopeStrategy.NOTE:
            # entity_notes are polymorphic (entity_type/entity_id) — resolve via
            # the target entity's own descriptor.
            return self._client_ids_for_target(getattr(row, "entity_type", None), row.entity_id)
        if strategy == ScopeStrategy.REMINDER:
            # reminders carry source_domain/source_id — resolve via the source.
            return self._client_ids_for_target(
                getattr(row, "source_domain", None), getattr(row, "source_id", None)
            )
        return frozenset()

    def _client_ids_for_target(
        self, target_entity_type: str | None, target_entity_id: int | None
    ) -> frozenset[int]:
        """Resolve the owning client(s) of a polymorphic target (note/reminder).

        Looks the target up in the registry and resolves only the direct
        (non-polymorphic) strategies to avoid recursion; unknown/indirect targets
        yield an empty set (best-effort — scope is context, not authorization).
        """
        if not target_entity_type or target_entity_id is None:
            return frozenset()
        descriptor = get_descriptor(target_entity_type)
        if descriptor is None or descriptor.strategy in (
            ScopeStrategy.NOTE,
            ScopeStrategy.REMINDER,
        ):
            return frozenset()
        row = self._get(descriptor.model, target_entity_id)
        if row is None:
            return frozenset()
        return self._client_ids(descriptor, row)

    def _client_via(self, parent_model: type[Any], parent_id: int | None) -> frozenset[int]:
        if parent_id is None:
            return frozenset()
        parent = self.db.get(parent_model, parent_id)
        value = getattr(parent, "client_record_id", None) if parent is not None else None
        return frozenset({value}) if value is not None else frozenset()

    def _clients_for_legal_entity(self, legal_entity_id: int | None) -> frozenset[int]:
        if legal_entity_id is None:
            return frozenset()
        ids = self.db.scalars(
            select(ClientRecord.id).where(ClientRecord.legal_entity_id == legal_entity_id)
        ).all()
        return frozenset(ids)

    def _clients_for_person(self, person_id: int) -> frozenset[int]:
        ids = self.db.scalars(
            select(ClientRecord.id)
            .join(LegalEntity, ClientRecord.legal_entity_id == LegalEntity.id)
            .join(
                PersonLegalEntityLink,
                PersonLegalEntityLink.legal_entity_id == LegalEntity.id,
            )
            .where(PersonLegalEntityLink.person_id == person_id)
        ).all()
        return frozenset(ids)
