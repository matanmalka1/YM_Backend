"""Canonical frontend deep links for entities surfaced by cross-domain features.

One owner for the URL strings. Before this module the same routes were written in
`app/common/source_types.py` (work queue) and inline in the search service, and had
already drifted apart for annual reports and advance payments.
"""

from __future__ import annotations

from enum import Enum as PyEnum


class LinkedEntity(str, PyEnum):
    """An entity a cross-domain result can point at."""

    CLIENT = "client"
    BINDER = "binder"
    VAT_WORK_ITEM = "vat_work_item"
    ANNUAL_REPORT = "annual_report"
    ADVANCE_PAYMENT = "advance_payment"
    CHARGE = "charge"
    TASK = "task"
    DOCUMENT = "document"
    NOTIFICATION = "notification"


def entity_route(
    entity: LinkedEntity, entity_id: int, *, client_record_id: int | None = None
) -> str:
    """Return the frontend route that opens `entity_id`.

    `client_record_id` is required by the client-scoped screens. An advance payment
    opens the advance-payments detail page — keyed by both client and payment id, but
    reached through the advance-payments list, not the client tab, so its breadcrumb
    matches a charge opening through the charges list. A document is reached through its
    owning client's tab, which loads the single record and opens it regardless of the
    tab's own filters. Annual reports have both a global and a client-scoped detail
    screen; the client-scoped one is used when the caller already knows the owning
    client, so the user stays inside that client's context.
    """
    if entity is LinkedEntity.CLIENT:
        return f"/clients/{entity_id}"
    if entity is LinkedEntity.BINDER:
        return f"/binders?binder_id={entity_id}"
    if entity is LinkedEntity.VAT_WORK_ITEM:
        return f"/tax/vat/{entity_id}"
    if entity is LinkedEntity.ANNUAL_REPORT:
        if client_record_id is None:
            return f"/tax/reports/{entity_id}"
        return f"/clients/{client_record_id}/annual-reports/{entity_id}"
    if entity is LinkedEntity.ADVANCE_PAYMENT:
        _require_client(entity, client_record_id)
        return f"/tax/advance-payments/{client_record_id}/{entity_id}"
    if entity is LinkedEntity.CHARGE:
        return f"/charges/{entity_id}"
    if entity is LinkedEntity.TASK:
        return f"/tasks?task_id={entity_id}"
    if entity is LinkedEntity.DOCUMENT:
        _require_client(entity, client_record_id)
        return f"/clients/{client_record_id}/documents?document_id={entity_id}"
    return f"/notifications?notification_id={entity_id}"


def _require_client(entity: LinkedEntity, client_record_id: int | None) -> None:
    if client_record_id is None:
        raise ValueError(f"{entity.value} links require client_record_id")


__all__ = ["LinkedEntity", "entity_route"]
