"""API tests for the office-wide annual generation endpoints."""

from decimal import Decimal
from itertools import count
from uuid import uuid4

from app.advance_payments.models.advance_payment import AdvancePayment
from app.clients.client_enums import ClientStatus
from app.common.enums import AdvancePaymentFrequency
from app.utils.time_utils import israel_today, utcnow
from tests.helpers.identity import seed_client_identity

_seq = count(1)

PREVIEW_URL = "/api/v1/advance-payments/bulk-generate/preview"
GENERATE_URL = "/api/v1/advance-payments/bulk-generate"

# A future year keeps every period ahead of today, so nothing is skipped for a
# due date that has already passed and the counts stay deterministic.
FUTURE_YEAR = israel_today().year + 1


def _client_record(
    db,
    *,
    frequency=AdvancePaymentFrequency.BIMONTHLY,
    status=ClientStatus.ACTIVE,
    name=None,
    deleted_at=None,
):
    idx = next(_seq)
    record = seed_client_identity(
        db,
        full_name=name or f"Bulk Gen Client {idx}",
        id_number=f"BGN{idx:06d}",
        advance_payment_frequency=frequency,
        advance_rate=Decimal("10"),
        status=status,
        deleted_at=deleted_at,
    )
    db.commit()
    return record


def _generate(client, headers, payload):
    return client.post(
        GENERATE_URL, json=payload, headers={**headers, "X-Idempotency-Key": str(uuid4())}
    )


def test_preview_counts_eligible_and_names_clients_without_frequency(
    client, test_db, advisor_headers
):
    _client_record(test_db)
    _client_record(test_db)
    _client_record(test_db, frequency=None, name="ללא תדירות")

    resp = client.get(PREVIEW_URL, headers=advisor_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["eligible_count"] == 2
    assert data["ineligible"] == [
        {
            "client_record_id": data["ineligible"][0]["client_record_id"],
            "client_name": "ללא תדירות",
            "reason": "frequency_not_set",
        }
    ]


def test_preview_excludes_frozen_closed_and_deleted_clients(client, test_db, advisor_headers):
    _client_record(test_db)
    _client_record(test_db, status=ClientStatus.FROZEN)
    _client_record(test_db, status=ClientStatus.CLOSED)
    _client_record(test_db, deleted_at=utcnow())
    # A frozen client with no frequency must not surface as an exception either:
    # it is out of scope entirely, so reporting it would be noise.
    _client_record(test_db, frequency=None, status=ClientStatus.FROZEN)
    _client_record(test_db, frequency=None, deleted_at=utcnow())

    resp = client.get(PREVIEW_URL, headers=advisor_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["eligible_count"] == 1
    assert data["ineligible"] == []


def test_bulk_generate_skips_soft_deleted_clients(client, test_db, advisor_headers):
    _client_record(test_db)
    _client_record(test_db, deleted_at=utcnow())

    resp = _generate(client, advisor_headers, {"year": FUTURE_YEAR})

    assert resp.status_code == 200
    assert resp.json()["clients_processed"] == 1


def test_bulk_generate_creates_schedules_for_every_eligible_client(
    client, test_db, advisor_headers
):
    first = _client_record(test_db)
    second = _client_record(test_db)
    _client_record(test_db, status=ClientStatus.FROZEN)
    _client_record(test_db, frequency=None)

    resp = _generate(client, advisor_headers, {"year": FUTURE_YEAR})

    assert resp.status_code == 200
    data = resp.json()
    assert data["clients_processed"] == 2
    # Bimonthly: six periods per client, none of them already past.
    assert data["created"] == 12
    assert data["skipped"] == 0
    assert data["failed"] == []
    assert data["next_cursor"] is None

    for record in (first, second):
        rows = (
            test_db.query(AdvancePayment).filter(AdvancePayment.client_record_id == record.id).all()
        )
        assert len(rows) == 6


def test_bulk_generate_skips_periods_that_already_exist(client, test_db, advisor_headers):
    _client_record(test_db)

    first = _generate(client, advisor_headers, {"year": FUTURE_YEAR})
    assert first.json()["created"] == 6

    second = _generate(client, advisor_headers, {"year": FUTURE_YEAR})

    assert second.status_code == 200
    data = second.json()
    assert data["created"] == 0
    assert data["skipped"] == 6


def test_bulk_generate_walks_the_office_in_cursor_chunks(
    client, test_db, advisor_headers, monkeypatch
):
    monkeypatch.setattr(
        "app.advance_payments.services.advance_payment_service.BULK_GENERATE_CLIENT_CHUNK_SIZE",
        2,
    )
    records = [_client_record(test_db) for _ in range(3)]

    first = _generate(client, advisor_headers, {"year": FUTURE_YEAR})
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["clients_processed"] == 2
    assert first_data["next_cursor"] == records[1].id

    second = _generate(
        client, advisor_headers, {"year": FUTURE_YEAR, "cursor": first_data["next_cursor"]}
    )
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["clients_processed"] == 1
    assert second_data["next_cursor"] is None

    assert first_data["created"] + second_data["created"] == 18
    assert test_db.query(AdvancePayment).count() == 18


def test_bulk_generate_marks_the_audit_entries_as_bulk(client, test_db, advisor_headers):
    from app.audit.audit_constants import ACTION_ADVANCE_PAYMENT_CREATED
    from app.audit.models.audit_entity_audit_log import EntityAuditLog

    _client_record(test_db)

    assert _generate(client, advisor_headers, {"year": FUTURE_YEAR}).status_code == 200

    entries = (
        test_db.query(EntityAuditLog)
        .filter(EntityAuditLog.action == ACTION_ADVANCE_PAYMENT_CREATED)
        .all()
    )
    assert entries
    assert all(entry.metadata_json.get("source") == "bulk_generate" for entry in entries)


def test_bulk_generate_is_advisor_only(client, test_db, secretary_headers):
    _client_record(test_db)

    resp = _generate(client, secretary_headers, {"year": FUTURE_YEAR})

    assert resp.status_code == 403
