"""Enrichment helpers for VAT work item query results."""

from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.clients.repositories.legal_entity_repository import LegalEntityRepository
from app.users.repositories.user_repository import UserRepository
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.services.vat_report_queries import (
    count_audit_trail,
    get_audit_trail,
    get_work_item,
    list_all_work_items,
    list_client_work_items_paginated,
    list_work_items_by_status,
)


def _build_client_maps(db, client_record_ids: list[int]) -> dict[str, dict]:
    client_records = (
        ClientRecordRepository(db).list_by_ids(client_record_ids) if client_record_ids else []
    )
    legal_entity_ids = list({record.legal_entity_id for record in client_records})
    legal_entity_by_id = {
        entity.id: entity for entity in LegalEntityRepository(db).list_by_ids(legal_entity_ids)
    }
    return {
        "office_client_number_map": {
            record.id: record.office_client_number for record in client_records
        },
        "name_map": {
            record.id: legal_entity_by_id[record.legal_entity_id].official_name
            for record in client_records
            if record.legal_entity_id in legal_entity_by_id
        },
        "id_number_map": {
            record.id: legal_entity_by_id[record.legal_entity_id].id_number
            for record in client_records
            if record.legal_entity_id in legal_entity_by_id
        },
        "status_map": {record.id: record.status for record in client_records},
    }


def get_work_item_enriched(
    work_item_repo: VatWorkItemRepository,
    user_repo: UserRepository,
    item_id: int,
) -> dict:
    """Return work item + client/user enrichment data."""
    item = get_work_item(work_item_repo, item_id)
    user_ids = [uid for uid in [item.assigned_to, item.filed_by] if uid]
    users = user_repo.list_by_ids(user_ids) if user_ids else []
    user_map = {u.id: u.full_name for u in users}
    client_maps = _build_client_maps(work_item_repo.db, [item.client_record_id])
    return {
        "item": item,
        **client_maps,
        "user_map": user_map,
    }


def get_client_items_enriched(
    work_item_repo: VatWorkItemRepository,
    user_repo: UserRepository,
    client_record_id: int,
    page: int,
    page_size: int,
) -> dict:
    """Return client work items + enrichment data."""
    items, total = list_client_work_items_paginated(
        work_item_repo,
        client_record_id,
        page=page,
        page_size=page_size,
    )
    user_ids = list({uid for item in items for uid in [item.assigned_to, item.filed_by] if uid})
    users = user_repo.list_by_ids(user_ids) if user_ids else []
    client_maps = _build_client_maps(work_item_repo.db, [client_record_id])
    return {
        "items": items,
        "total": total,
        **client_maps,
        "user_map": {u.id: u.full_name for u in users},
    }


def get_list_enriched(
    work_item_repo: VatWorkItemRepository,
    user_repo: UserRepository,
    *,
    status_filter,
    page: int,
    page_size: int,
    period: str | None,
    period_type=None,
    client_name: str | None = None,
) -> dict:
    """Return paginated work items + enrichment data."""
    if status_filter:
        items, total = list_work_items_by_status(
            work_item_repo,
            status_filter,
            page=page,
            page_size=page_size,
            period=period,
            period_type=period_type,
            client_name=client_name,
        )
    else:
        items, total = list_all_work_items(
            work_item_repo,
            page=page,
            page_size=page_size,
            period=period,
            period_type=period_type,
            client_name=client_name,
        )
    client_record_ids = list({item.client_record_id for item in items})
    user_ids = list({uid for item in items for uid in [item.assigned_to, item.filed_by] if uid})
    users = user_repo.list_by_ids(user_ids) if user_ids else []
    client_maps = _build_client_maps(work_item_repo.db, client_record_ids)
    return {
        "items": items,
        "total": total,
        **client_maps,
        "user_map": {u.id: u.full_name for u in users},
    }


def get_audit_trail_enriched(
    work_item_repo: VatWorkItemRepository,
    user_repo: UserRepository,
    item_id: int,
    limit: int,
    offset: int,
) -> dict:
    entries = get_audit_trail(work_item_repo, item_id, limit, offset)
    user_ids = list({e.performed_by for e in entries})
    users = user_repo.list_by_ids(user_ids) if user_ids else []
    return {
        "entries": entries,
        "total": count_audit_trail(work_item_repo, item_id),
        "user_map": {u.id: u.full_name for u in users},
    }
