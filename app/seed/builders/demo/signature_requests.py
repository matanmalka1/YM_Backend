from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from random import Random

from sqlalchemy import func, select

from app.signature_requests.models.signature_request import (
    SignatureRequest,
    SignatureRequestStatus,
    SignatureRequestType,
)
from app.signature_requests.signature_request_audit import (
    ACTION_SIGNATURE_REQUEST_CANCELED,
    ACTION_SIGNATURE_REQUEST_CREATED,
    ACTION_SIGNATURE_REQUEST_DECLINED,
    ACTION_SIGNATURE_REQUEST_EXPIRED,
    ACTION_SIGNATURE_REQUEST_SENT,
    ACTION_SIGNATURE_REQUEST_SIGNED,
    record_signature_external_action,
    record_signature_system_action,
    record_signature_user_action,
)

from ...data.realistic_seed_text import SIGNATURE_COPY
from ..shared.client_refs import get_seed_client_record_id


def _group_by_client(businesses) -> dict[int, list]:
    grouped: dict[int, list] = {}
    for b in businesses:
        grouped.setdefault(get_seed_client_record_id(b), []).append(b)
    return grouped


def _pick_businesses(rng: Random, client_businesses: list, count: int) -> list:
    if count <= 0 or not client_businesses:
        return []
    return [rng.choice(client_businesses) for _ in range(count)]


def _pick_for_client(rng: Random, rows_by_client: dict[int, list], client_id: int):
    rows = rows_by_client.get(client_id, [])
    return rng.choice(rows) if rows else None


def _group_by_client_record(rows) -> dict[int, list]:
    grouped: dict[int, list] = {}
    for row in rows:
        key = get_seed_client_record_id(row)
        grouped.setdefault(key, []).append(row)
    return grouped


def _random_between(rng: Random, start: datetime, end: datetime) -> datetime:
    if end <= start:
        return start
    seconds = max(1, int((end - start).total_seconds()))
    return start + timedelta(seconds=rng.randint(0, seconds))


def _build_timestamps(rng: Random, status: SignatureRequestStatus) -> dict:
    now = datetime.now(UTC)
    created_at = now - timedelta(days=rng.randint(7, 90), hours=rng.randint(0, 23))

    sent_at = _random_between(rng, created_at, now - timedelta(hours=1))
    if sent_at <= created_at:
        sent_at = created_at + timedelta(minutes=1)

    if status == SignatureRequestStatus.EXPIRED:
        expires_at = _random_between(rng, sent_at + timedelta(hours=1), now - timedelta(minutes=1))
        if expires_at <= sent_at:
            expires_at = sent_at + timedelta(hours=1)
    else:
        expires_at = sent_at + timedelta(days=rng.randint(5, 30))
        if status == SignatureRequestStatus.PENDING_SIGNATURE and expires_at <= now:
            expires_at = now + timedelta(days=rng.randint(1, 14))

    event_upper = min(now, expires_at) if expires_at else now
    if event_upper <= sent_at:
        event_upper = sent_at + timedelta(hours=1)

    signed_at = (
        _random_between(rng, sent_at + timedelta(minutes=1), event_upper)
        if status == SignatureRequestStatus.SIGNED
        else None
    )
    declined_at = (
        _random_between(rng, sent_at + timedelta(minutes=1), event_upper)
        if status == SignatureRequestStatus.DECLINED
        else None
    )
    canceled_at = (
        _random_between(rng, sent_at + timedelta(minutes=1), event_upper)
        if status == SignatureRequestStatus.CANCELED
        else None
    )

    return {
        "created_at": created_at,
        "sent_at": sent_at,
        "expires_at": expires_at,
        "signed_at": signed_at,
        "declined_at": declined_at,
        "canceled_at": canceled_at,
    }


def create_signature_requests(
    db, rng: Random, cfg, businesses, clients, users, annual_reports, documents
):
    requests: list[SignatureRequest] = []
    clients_by_id = {client.id: client for client in clients}
    reports_by_client = _group_by_client_record(annual_reports)
    documents_by_client = _group_by_client_record(documents)
    existing_count = int(
        db.execute(select(func.count()).select_from(SignatureRequest)).scalar_one()
    )
    current_year = cfg.reference_date.year
    _FINAL_STATUSES = [
        SignatureRequestStatus.SIGNED,
        SignatureRequestStatus.DECLINED,
        SignatureRequestStatus.EXPIRED,
        SignatureRequestStatus.CANCELED,
    ]
    type_cycle = list(SignatureRequestType)
    status_cycle = list(SignatureRequestStatus)
    type_idx = 0
    status_idx = 0

    for client_businesses in _group_by_client(businesses).values():
        client_record_id = get_seed_client_record_id(client_businesses[0])
        client = clients_by_id.get(client_record_id)
        if not client:
            continue
        for business in _pick_businesses(rng, client_businesses, cfg.signature_requests_per_client):
            report = _pick_for_client(rng, reports_by_client, client.id)
            document = _pick_for_client(rng, documents_by_client, client.id)
            if status_idx < len(status_cycle):
                status = status_cycle[status_idx]
                status_idx += 1
            else:
                status = rng.choice(status_cycle)
            timestamps = _build_timestamps(rng, status)
            if timestamps["created_at"].year < current_year and status not in _FINAL_STATUSES:
                status = rng.choice(_FINAL_STATUSES)
                timestamps = _build_timestamps(rng, status)
            serial = existing_count + len(requests) + 1
            if type_idx < len(type_cycle):
                request_type = type_cycle[type_idx]
                type_idx += 1
            else:
                request_type = rng.choice(type_cycle)
            title_prefix, request_description = SIGNATURE_COPY[request_type]
            canceled_by = (
                rng.choice(users).id if status == SignatureRequestStatus.CANCELED else None
            )
            signing_token = f"seed-sign-{serial:010d}"
            if status in (
                SignatureRequestStatus.SIGNED,
                SignatureRequestStatus.DECLINED,
                SignatureRequestStatus.EXPIRED,
                SignatureRequestStatus.CANCELED,
            ):
                signing_token = None

            req = SignatureRequest(
                client_record_id=get_seed_client_record_id(business),
                business_id=business.id,
                created_by=rng.choice(users).id,
                annual_report_id=report.id if report else None,
                document_id=document.id if document else None,
                request_type=request_type,
                title=f"{title_prefix} - {client.full_name}",
                description=request_description,
                content_hash=None,
                storage_key=document.storage_key if document else None,
                signer_name=client.full_name,
                signer_email=client.email,
                signer_phone=client.phone,
                status=status,
                signing_token=signing_token,
                created_at=timestamps["created_at"],
                sent_at=timestamps["sent_at"],
                expires_at=timestamps["expires_at"],
                signed_at=timestamps["signed_at"],
                declined_at=timestamps["declined_at"],
                canceled_at=timestamps["canceled_at"],
                canceled_by=canceled_by,
                decline_reason="הלקוח ביקש לעדכן נוסח לפני חתימה"
                if status == SignatureRequestStatus.DECLINED
                else None,
                signer_ip_address="127.0.0.1" if status == SignatureRequestStatus.SIGNED else None,
                signer_user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
                if status == SignatureRequestStatus.SIGNED
                else None,
                signed_document_key=f"signed/signature_request_{serial}.pdf"
                if status == SignatureRequestStatus.SIGNED
                else None,
            )
            db.add(req)
            requests.append(req)
    db.flush()
    return requests


def create_signature_audit_events(db, rng: Random, requests: Iterable[SignatureRequest]) -> None:
    for req in requests:
        events: list[tuple[str, datetime, str]] = [
            (ACTION_SIGNATURE_REQUEST_CREATED, req.created_at, "advisor")
        ]
        if req.sent_at:
            events.append((ACTION_SIGNATURE_REQUEST_SENT, req.sent_at, "advisor"))
        if req.signed_at:
            events.append((ACTION_SIGNATURE_REQUEST_SIGNED, req.signed_at, "signer"))
        if req.declined_at:
            events.append((ACTION_SIGNATURE_REQUEST_DECLINED, req.declined_at, "signer"))
        if req.canceled_at:
            events.append((ACTION_SIGNATURE_REQUEST_CANCELED, req.canceled_at, "advisor"))
        if req.status == SignatureRequestStatus.EXPIRED and req.expires_at:
            events.append((ACTION_SIGNATURE_REQUEST_EXPIRED, req.expires_at, "system"))

        for action, ts, actor_type in events:
            if actor_type == "advisor":
                record_signature_user_action(
                    db,
                    req,
                    actor_id=req.created_by,
                    actor_display_name="מערכת חתימות דיגיטליות",
                    action=action,
                    performed_at=ts,
                    reason=req.decline_reason
                    if action == ACTION_SIGNATURE_REQUEST_CANCELED
                    else None,
                )
            elif actor_type == "signer":
                record_signature_external_action(
                    db,
                    req,
                    action=action,
                    ip_address=req.signer_ip_address,
                    user_agent=req.signer_user_agent,
                    note=req.decline_reason
                    if action == ACTION_SIGNATURE_REQUEST_DECLINED
                    else None,
                    performed_at=ts,
                )
            else:
                note = "בקשת החתימה פגה"
                record_signature_system_action(
                    db,
                    req,
                    action=action,
                    note=note,
                    reason=note,
                    performed_at=ts,
                )
    db.flush()
