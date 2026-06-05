"""Tests for the shared idempotency dependency."""

import threading
from io import BytesIO

import openpyxl
import pytest
from fastapi import HTTPException

from app.infrastructure.idempotency.dependency import IdempotencyGuard
from app.infrastructure.idempotency.model import IdempotencyKey, IdempotencyStatus


def _workbook_bytes(rows: list[list[str]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _import_payload() -> bytes:
    return _workbook_bytes(
        [
            ["full_name", "business_name", "id_number"],
            ["Idempotency Test", "Idempotency Biz", "880000001"],
        ]
    )


def _upload_file(payload: bytes) -> dict:
    return {
        "file": (
            "clients.xlsx",
            payload,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }


IMPORT_PATH = "/api/v1/clients/import"


# ── HTTP-level integration tests ─────────────────────────────────────────────


def test_idempotency_missing_header_returns_422(client, advisor_headers, test_db):
    response = client.post(
        IMPORT_PATH,
        headers=advisor_headers,
        files=_upload_file(_import_payload()),
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"] == [
        {
            "field": "X-Idempotency-Key",
            "message": "Field required",
            "type": "missing",
        }
    ]


def test_idempotency_duplicate_request_returns_cached_response(client, advisor_headers, test_db):
    payload = _import_payload()
    headers = {**advisor_headers, "X-Idempotency-Key": "idem-dup-1"}

    first = client.post(IMPORT_PATH, headers=headers, files=_upload_file(payload))
    assert first.status_code == 200
    first_body = first.json()

    second = client.post(IMPORT_PATH, headers=headers, files=_upload_file(payload))
    assert second.status_code == 200
    assert second.json() == first_body


def test_idempotency_different_body_same_key_returns_409(client, advisor_headers, test_db):
    headers = {**advisor_headers, "X-Idempotency-Key": "idem-conflict-1"}

    first_payload = _workbook_bytes(
        [
            ["full_name", "business_name", "id_number"],
            ["Conflict A", "Conflict Biz A", "880000002"],
        ]
    )
    second_payload = _workbook_bytes(
        [
            ["full_name", "business_name", "id_number"],
            ["Conflict B", "Conflict Biz B", "880000003"],
        ]
    )

    first = client.post(IMPORT_PATH, headers=headers, files=_upload_file(first_payload))
    assert first.status_code == 200

    second = client.post(IMPORT_PATH, headers=headers, files=_upload_file(second_payload))
    assert second.status_code == 409
    assert second.json()["error"]["message"] == "מפתח אידמפוטנטיות כבר נוצל עם בקשה אחרת"


# ── Unit-level guard tests (reservation + concurrency) ──────────────────────


def test_guard_in_progress_row_blocks_fn_execution(test_db, test_user):
    """Pre-seeded IN_PROGRESS row → second caller gets 409 and fn is NEVER invoked."""
    import hashlib

    payload = b"same-body"
    request_hash = hashlib.sha256(payload).hexdigest()
    test_db.add(
        IdempotencyKey(
            key="K-blocked",
            route="/fake",
            user_id=test_user.id,
            request_hash=request_hash,
            status=IdempotencyStatus.IN_PROGRESS,
        )
    )
    test_db.commit()

    calls = []

    def fn():
        calls.append(1)
        return {"ok": True}

    guard = IdempotencyGuard(key="K-blocked", route="/fake", user_id=test_user.id, db=test_db)
    with pytest.raises(HTTPException) as exc:
        guard.execute(payload=payload, fn=fn)
    assert exc.value.status_code == 409
    assert exc.value.detail == "בקשה זהה כבר בעיבוד"
    assert calls == []


def test_guard_concurrent_reservation_runs_fn_once(test_db, test_user):
    """Two threads racing on the same key → fn runs at most once."""
    import hashlib

    payload = b"concurrent-body"
    request_hash = hashlib.sha256(payload).hexdigest()

    # Simulate the race: thread A successfully reserves, then thread B tries.
    # We emulate the "B arrives mid-flight" by reserving for A, NOT completing,
    # then invoking B's execute. With a real PG concurrent flow the PK conflict
    # path is identical to the IN_PROGRESS branch tested here.
    guard_a = IdempotencyGuard(key="K-race", route="/fake", user_id=test_user.id, db=test_db)

    # Reserve for A by calling execute with a fn that holds via a flag.
    call_count = {"n": 0}
    proceed = threading.Event()
    started = threading.Event()
    a_result = {}

    def slow_fn():
        call_count["n"] += 1
        started.set()
        proceed.wait(timeout=2.0)
        return {"ok": "A"}

    def run_a():
        a_result["value"] = guard_a.execute(payload=payload, fn=slow_fn)

    thread_a = threading.Thread(target=run_a)
    thread_a.start()
    assert started.wait(timeout=2.0), "thread A never entered fn"

    # While A is mid-flight (row exists, status=IN_PROGRESS), B attempts the same key.
    # B must use its own session against the same DB so flush sees A's reservation.
    from sqlalchemy.orm import sessionmaker

    SessionB = sessionmaker(bind=test_db.get_bind(), autocommit=False, autoflush=False)
    db_b = SessionB()

    def fn_b():
        call_count["n"] += 1
        return {"ok": "B"}

    guard_b = IdempotencyGuard(key="K-race", route="/fake", user_id=test_user.id, db=db_b)
    with pytest.raises(HTTPException) as exc:
        guard_b.execute(payload=payload, fn=fn_b)
    assert exc.value.status_code == 409

    proceed.set()
    thread_a.join(timeout=2.0)
    db_b.close()

    assert call_count["n"] == 1, f"fn should run exactly once, got {call_count['n']}"
    assert a_result["value"] == {"ok": "A"}
