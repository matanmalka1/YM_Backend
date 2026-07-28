"""Enrichment for grouped VAT work item endpoints."""

from datetime import date

from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.common.enums import ObligationStatus, VatType
from app.users.models.user import UserRole
from app.vat.api.vat_serializers import serialize_enriched_work_item_list
from app.vat.repositories import (
    vat_work_item_grouped_repository as grouped_repo,
)
from app.vat.vat_report_enrichment import _build_client_maps


def get_groups(
    db,
    *,
    period_type: VatType | None = None,
    client_record_id: int | None = None,
    client_name: str | None = None,
    status: ObligationStatus | None = None,
    year: int | None = None,
) -> list[dict]:
    client_record_ids = _resolve_client_ids(db, client_record_id, client_name)
    if client_name and not client_record_ids:
        return []
    return grouped_repo.list_due_date_groups(
        db,
        period_type=period_type,
        client_record_ids=client_record_ids,
        status=status,
        year=year,
    )


def get_group_items_enriched(
    db,
    *,
    group_key: str,
    page: int,
    page_size: int,
    client_record_id: int | None = None,
    client_name: str | None = None,
    status: ObligationStatus | None = None,
    user_role: UserRole | str | None = None,
) -> dict:
    due_date = _parse_due_date_group_key(group_key)
    if due_date is None:
        return {"items": [], "total": 0, "period": group_key}

    client_record_ids = _resolve_client_ids(db, client_record_id, client_name)
    if client_name and not client_record_ids:
        return {"items": [], "total": 0, "period": group_key}

    items, total = grouped_repo.list_by_due_date_paginated(
        db,
        due_date,
        page=page,
        page_size=page_size,
        client_record_ids=client_record_ids,
        status=status,
    )
    client_record_id_list = list({item.client_record_id for item in items})
    client_maps = _build_client_maps(db, client_record_id_list)

    serialized = [
        serialize_enriched_work_item_list(
            item,
            office_client_number_map=client_maps["office_client_number_map"],
            name_map=client_maps["name_map"],
            id_number_map=client_maps["id_number_map"],
            user_role=user_role,
        )
        for item in items
    ]
    return {"items": serialized, "total": total, "period": group_key}


def _resolve_client_ids(
    db,
    client_record_id: int | None,
    client_name: str | None,
) -> list[int] | None:
    if client_record_id is not None:
        if client_name:
            records, _ = ClientRecordRepository(db).search(
                search=client_name, page=1, page_size=500
            )
            if client_record_id not in {r.id for r in records}:
                return []
        return [client_record_id]
    if not client_name:
        return None
    records, _ = ClientRecordRepository(db).search(search=client_name, page=1, page_size=500)
    return [r.id for r in records]


def _parse_due_date_group_key(group_key: str) -> date | None:
    try:
        return date.fromisoformat(group_key)
    except ValueError:
        return None
