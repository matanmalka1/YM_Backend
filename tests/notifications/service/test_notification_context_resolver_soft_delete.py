"""NotificationContextResolver must preserve pre-refactor read behavior:

1. It reads entities via repositories with include_deleted=True, so a soft-deleted
   binder / charge / VAT item / signature request still renders context rather than
   raising NotFoundError (Session.get() ignored soft-delete before the refactor).
2. The repo reads are identity-map-aware: when the entity is already loaded in the
   session (as the policy check does earlier in the request) no extra SELECT is emitted.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import event

from app.binders.models.binder import (
    Binder,
    BinderCapacityStatus,
    BinderLocationStatus,
)
from app.binders.repositories.binder_repository import BinderRepository
from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.charges.repositories.charge_repository import ChargeRepository
from app.common.enums import IdNumberType, VatType
from app.notifications.notification_context_resolver import NotificationContextResolver
from app.signature_requests.models.signature_request import (
    SignatureRequest,
    SignatureRequestStatus,
    SignatureRequestType,
)
from app.signature_requests.repositories.signature_request_repository import (
    SignatureRequestRepository,
)
from app.utils.time_utils import utcnow
from app.vat.models.vat_work_item import VatWorkItem
from app.vat.repositories.vat_work_item_query_repository import VatWorkItemQueryRepository


def _client(client_factory, suffix: str):
    return client_factory(
        full_name=f"Resolver Client {suffix}",
        id_number=f"RES-{suffix}",
        id_number_type=IdNumberType.INDIVIDUAL,
        email=f"res-{suffix}@example.com",
        vat_reporting_frequency=VatType.MONTHLY,
    )


def _charge(charge_factory, client_record_id: int) -> Charge:
    return charge_factory(
        client_record_id=client_record_id,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        amount=Decimal("120.00"),
        description="חיוב",
        issued_at=utcnow(),
    )


def _binder(binder_factory, client_record_id: int, user_id: int) -> Binder:
    return binder_factory(
        client_record_id=client_record_id,
        binder_number="ZZ-900",
        period_start=dt.date.today() - dt.timedelta(days=10),
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        created_by=user_id,
    )


def _vat_item(vat_work_item_factory, client_record_id: int, user_id: int) -> VatWorkItem:
    return vat_work_item_factory(
        client_record_id=client_record_id,
        created_by=user_id,
        period="2026-01",
        period_type=VatType.MONTHLY,
        due_date_original=dt.date.today(),
        due_date_effective=dt.date.today(),
    )


def _signature(signature_request_factory, client_record_id: int, user_id: int) -> SignatureRequest:
    return signature_request_factory(
        client_record_id=client_record_id,
        created_by=user_id,
        request_type=SignatureRequestType.CUSTOM,
        title="מסמך",
        signer_name="חותם",
        signer_email="signer@example.com",
        status=SignatureRequestStatus.PENDING_SIGNATURE,
        signing_token="tok-soft-del",
        expires_at=utcnow() + dt.timedelta(days=7),
    )


def test_resolver_renders_context_for_soft_deleted_charge(test_db, client_factory, charge_factory):
    client = _client(client_factory, "charge")
    charge = _charge(charge_factory, client.id)
    ChargeRepository(test_db).soft_delete(charge.id)

    ctx = NotificationContextResolver(test_db)._resolve_charge_context(charge.id, client.id)

    assert ctx["charge_description"] == "חיוב"


def test_resolver_renders_context_for_soft_deleted_binder(
    test_db, test_user, client_factory, binder_factory
):
    client = _client(client_factory, "binder")
    binder = _binder(binder_factory, client.id, test_user.id)
    BinderRepository(test_db).soft_delete(binder.id)

    number = NotificationContextResolver(test_db)._resolve_binder_number(binder.id, client.id)

    assert number == "ZZ-900"


def test_resolver_renders_context_for_soft_deleted_vat_item(
    test_db, test_user, client_factory, vat_work_item_factory
):
    client = _client(client_factory, "vat")
    item = _vat_item(vat_work_item_factory, client.id, test_user.id)
    VatWorkItemQueryRepository(test_db).soft_delete(item.id)

    ctx = NotificationContextResolver(test_db)._resolve_vat_context(item.id, client.id)

    assert ctx["period"] == "2026-01"


def test_resolver_renders_context_for_soft_deleted_signature(
    test_db, test_user, client_factory, signature_request_factory
):
    client = _client(client_factory, "sig")
    sig = _signature(signature_request_factory, client.id, test_user.id)
    sig.deleted_at = utcnow()
    test_db.flush()

    ctx = NotificationContextResolver(test_db)._resolve_signature_context(sig.id, client.id)

    assert ctx["document_title"] == "מסמך"


def test_signature_get_by_id_include_deleted(
    test_db, test_user, client_factory, signature_request_factory
):
    client = _client(client_factory, "sig2")
    sig = _signature(signature_request_factory, client.id, test_user.id)
    sig.deleted_at = utcnow()
    test_db.flush()
    repo = SignatureRequestRepository(test_db)

    assert repo.get_by_id(sig.id) is None
    assert repo.get_by_id(sig.id, include_deleted=True) is not None


def test_resolver_charge_read_emits_no_extra_query_when_preloaded(
    test_db, client_factory, charge_factory
):
    """Identity-map regression: a charge already loaded in the session costs no SELECT."""
    client = _client(client_factory, "qc")
    charge = _charge(charge_factory, client.id)  # flushed → present in the identity map

    selects: list[str] = []

    def _track(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().lower().startswith("select"):
            selects.append(statement)

    event.listen(test_db.bind, "after_cursor_execute", _track)
    try:
        NotificationContextResolver(test_db)._resolve_charge_context(charge.id, client.id)
    finally:
        event.remove(test_db.bind, "after_cursor_execute", _track)

    assert selects == [], f"expected no SELECT, got: {selects}"
