"""Serialization helpers for VAT API responses."""

from app.actions.services.vat_report_actions import get_vat_work_item_actions
from app.users.models.user import UserRole
from app.vat.schemas.vat_report import VatWorkItemListItem, VatWorkItemResponse
from app.vat.services.vat_report_service import VatReportService
from app.vat.vat_report_queries import get_vat_deadline_fields


def serialize_enriched_work_item(
    item,
    *,
    office_client_number_map: dict,
    name_map: dict,
    id_number_map: dict,
    status_map: dict,
    user_map: dict,
    breakdown,
    user_role: UserRole | str | None = None,
) -> VatWorkItemResponse:
    item_data = {
        field_name: getattr(item, field_name)
        for field_name in VatWorkItemResponse.model_fields
        if hasattr(item, field_name)
    }
    data = VatWorkItemResponse.model_validate({**item_data, "breakdown": breakdown})
    data.office_client_number = office_client_number_map.get(item.client_record_id)
    data.client_name = name_map.get(item.client_record_id)
    data.client_id_number = id_number_map.get(item.client_record_id)
    data.client_status = status_map.get(item.client_record_id)
    deadline = get_vat_deadline_fields(item, item.submission_method)
    data.submission_deadline = deadline["submission_deadline"]
    data.statutory_deadline = deadline["statutory_deadline"]
    data.extended_deadline = deadline["extended_deadline"]
    data.days_until_deadline = deadline["days_until_deadline"]
    data.is_overdue = deadline["is_overdue"]
    data.assigned_to_name = user_map.get(item.assigned_to) if item.assigned_to else None
    data.closed_by_name = user_map.get(item.closed_by) if item.closed_by else None
    data.available_actions = get_vat_work_item_actions(item, user_role=user_role)
    data.breakdown = breakdown
    return data


def serialize_enriched_work_item_list(
    item,
    *,
    office_client_number_map: dict,
    name_map: dict,
    id_number_map: dict,
    user_role: UserRole | str | None = None,
) -> VatWorkItemListItem:
    data = VatWorkItemListItem.model_validate(item)
    data.office_client_number = office_client_number_map.get(item.client_record_id)
    data.client_name = name_map.get(item.client_record_id)
    data.client_id_number = id_number_map.get(item.client_record_id)
    deadline = get_vat_deadline_fields(item, item.submission_method)
    data.submission_deadline = deadline["submission_deadline"]
    data.extended_deadline = deadline["extended_deadline"]
    data.days_until_deadline = deadline["days_until_deadline"]
    data.is_overdue = deadline["is_overdue"]
    data.available_actions = get_vat_work_item_actions(item, user_role=user_role)
    return data


def serialize_enriched_work_items(
    items,
    *,
    enriched: dict,
    user_role: UserRole | str | None = None,
) -> list[VatWorkItemListItem]:
    return [
        serialize_enriched_work_item_list(
            item,
            office_client_number_map=enriched["office_client_number_map"],
            name_map=enriched["name_map"],
            id_number_map=enriched["id_number_map"],
            user_role=user_role,
        )
        for item in items
    ]


def serialize_work_item(
    service: VatReportService,
    item_id: int,
    user_role: UserRole | str | None = None,
    *,
    include_deleted: bool = False,
) -> VatWorkItemResponse:
    enriched = service.get_work_item_enriched(item_id, include_deleted=include_deleted)
    return serialize_enriched_work_item(
        enriched["item"],
        office_client_number_map=enriched["office_client_number_map"],
        name_map=enriched["name_map"],
        id_number_map=enriched["id_number_map"],
        status_map=enriched["status_map"],
        user_map=enriched["user_map"],
        breakdown=enriched["breakdown"],
        user_role=user_role,
    )
