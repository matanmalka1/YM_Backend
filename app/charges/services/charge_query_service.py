from datetime import date

from sqlalchemy.orm import Session

from app.actions.services.charge_actions import get_charge_actions
from app.businesses.repositories.business_repository import BusinessRepository
from app.charges.models.charge import Charge
from app.charges.repositories.charge_repository import ChargeRepository
from app.charges.schemas.charge import (
    ChargeListItem,
    ChargeListResponse,
    ChargeListStats,
    ChargeStatusStat,
)
from app.clients.repositories.client_record_read_repository import (
    get_full_record,
    get_full_records_bulk,
)
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.users.models.user import UserRole


class ChargeQueryService:
    def __init__(self, db: Session):
        self.db = db
        self.charge_repo = ChargeRepository(db)
        self.business_repo = BusinessRepository(db)
        self.client_repo = ClientRecordRepository(db)

    def enrich_charge_context(self, charge: Charge) -> tuple[str | None, str | None, int | None]:
        client_record = self.client_repo.get_by_id(charge.client_record_id)
        client = get_full_record(self.db, charge.client_record_id)
        client_name = client["full_name"] if client else None
        office_number = client_record.office_client_number if client_record else None
        if charge.business_id is not None:
            businesses = self.business_repo.list_by_ids([charge.business_id])
            if businesses:
                return client_name, businesses[0].full_name, office_number
        return client_name, None, office_number

    def list_charges(
        self,
        business_id: int | None = None,
        client_record_id: int | None = None,
        status: str | None = None,
        charge_type: str | None = None,
        period: str | None = None,
        issued_after: date | None = None,
        issued_before: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[
        list[Charge],
        int,
        dict[int, str | None],
        dict[int, str | None],
        dict[int, int | None],
    ]:
        client_record = (
            self.client_repo.get_by_id(client_record_id)
            if client_record_id is not None
            else None
        )
        if client_record is not None:
            items = self.charge_repo.list_charges_by_client_record(
                client_record_id=client_record.id,
                business_id=business_id,
                status=status,
                charge_type=charge_type,
                period=period,
                issued_after=issued_after,
                issued_before=issued_before,
                page=page,
                page_size=page_size,
            )
            total = self.charge_repo.count_charges_by_client_record(
                client_record_id=client_record.id,
                business_id=business_id,
                status=status,
                charge_type=charge_type,
                period=period,
                issued_after=issued_after,
                issued_before=issued_before,
            )
        else:
            items = self.charge_repo.list_charges(
                client_record_id=client_record_id,
                business_id=business_id,
                status=status,
                charge_type=charge_type,
                period=period,
                issued_after=issued_after,
                issued_before=issued_before,
                page=page,
                page_size=page_size,
            )
            total = self.charge_repo.count_charges(
                client_record_id=client_record_id,
                business_id=business_id,
                status=status,
                charge_type=charge_type,
                period=period,
                issued_after=issued_after,
                issued_before=issued_before,
            )

        business_ids = list({c.business_id for c in items if c.business_id is not None})
        businesses = self.business_repo.list_by_ids(business_ids) if business_ids else []
        business_name_by_id = {c.id: c.full_name for c in businesses}
        client_record_ids = list({c.client_record_id for c in items})
        client_records = (
            self.client_repo.list_by_ids(client_record_ids)
            if client_record_ids
            else []
        )
        record_by_id = {record.id: record for record in client_records}
        clients = get_full_records_bulk(self.db, client_record_ids)
        client_name_map = {
            c.id: clients.get(c.client_record_id, {}).get("full_name") for c in items
        }
        business_name_map = {c.id: business_name_by_id.get(c.business_id) for c in items}
        office_client_number_map = {
            c.id: record_by_id[c.client_record_id].office_client_number
            if c.client_record_id in record_by_id
            else None
            for c in items
        }

        return (
            items,
            total,
            client_name_map,
            business_name_map,
            office_client_number_map,
        )

    def list_charges_paginated(
        self,
        business_id: int | None = None,
        client_record_id: int | None = None,
        status: str | None = None,
        charge_type: str | None = None,
        period: str | None = None,
        issued_after: date | None = None,
        issued_before: date | None = None,
        page: int = 1,
        page_size: int = 20,
        user_role: UserRole | None = None,
    ) -> ChargeListResponse:
        items, total, client_name_map, business_name_map, office_client_number_map = (
            self.list_charges(
                business_id=business_id,
                client_record_id=client_record_id,
                status=status,
                charge_type=charge_type,
                period=period,
                issued_after=issued_after,
                issued_before=issued_before,
                page=page,
                page_size=page_size,
            )
        )

        def _enrich(charge: Charge) -> ChargeListItem:
            item = ChargeListItem.model_validate(charge)
            item.client_name = client_name_map.get(charge.id)
            item.business_name = business_name_map.get(charge.id)
            item.office_client_number = office_client_number_map.get(charge.id)
            item.available_actions = get_charge_actions(charge, user_role=user_role)
            return item

        client_record = (
            self.client_repo.get_by_id(client_record_id)
            if client_record_id is not None
            else None
        )
        raw = self.charge_repo.stats_by_status(
            client_record_id=client_record.id if client_record else None,
            charge_type=charge_type,
            business_id=business_id,
            period=period,
            issued_after=issued_after,
            issued_before=issued_before,
        )

        def _stat(key: str) -> ChargeStatusStat:
            d = raw.get(key, {})
            return ChargeStatusStat(count=d.get("count", 0), amount=d.get("amount", "0"))

        stats = ChargeListStats(
            draft=_stat("draft"),
            issued=_stat("issued"),
            paid=_stat("paid"),
            canceled=_stat("canceled"),
        )
        return ChargeListResponse(
            items=[_enrich(c) for c in items],
            page=page,
            page_size=page_size,
            total=total,
            stats=stats,
        )
