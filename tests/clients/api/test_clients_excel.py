import io

from openpyxl import Workbook
from sqlalchemy import func, select

from app.clients.api import client_routes_excel as clients_excel_api
from app.clients.models.client_record import ClientRecord

IDEMPOTENCY_HEADER = {"X-Idempotency-Key": "clients-import-test-key"}


def _workbook_bytes(rows: list[list[str | None]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def test_export_clients_excel(client, advisor_headers):
    response = client.get("/api/v1/clients/export", headers=advisor_headers)

    assert response.status_code == 200
    assert (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        in response.headers["content-type"]
    )
    assert "attachment; filename=" in response.headers.get("content-disposition", "")


def test_template_download(client, advisor_headers):
    response = client.get("/api/v1/clients/template", headers=advisor_headers)

    assert response.status_code == 200
    assert (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        in response.headers["content-type"]
    )


def test_import_clients_excel_advisor_only(client, advisor_headers, secretary_headers):
    payload = _workbook_bytes(
        [
            ["full_name", "business_name", "id_number", "phone", "email"],
            [
                "Excel User",
                "Excel User Business",
                "710000001",
                "0500000000",
                "excel@example.com",
            ],
        ]
    )

    denied = client.post(
        "/api/v1/clients/import",
        headers={**secretary_headers, **IDEMPOTENCY_HEADER},
        files={
            "file": (
                "clients.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert denied.status_code == 403

    ok = client.post(
        "/api/v1/clients/import",
        headers={**advisor_headers, **IDEMPOTENCY_HEADER},
        files={
            "file": (
                "clients.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["created"] == 1
    assert body["total_rows"] == 1
    assert body["errors"] == []


def test_import_clients_excel_returns_row_errors(client, advisor_headers):
    payload = _workbook_bytes(
        [
            ["full_name", "business_name", "id_number", "phone", "email"],
            ["", "", "", None, None],
            ["Duplicate One", "Duplicate One Business", "720000001", None, None],
            ["Duplicate Two", "Duplicate Two Business", "720000001", None, None],
        ]
    )

    response = client.post(
        "/api/v1/clients/import",
        headers={**advisor_headers, **IDEMPOTENCY_HEADER},
        files={
            "file": (
                "clients.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 1
    assert body["total_rows"] == 3
    assert len(body["errors"]) == 1
    assert {err["row"] for err in body["errors"]} == {4}


def test_import_clients_excel_creates_client_from_template_headers(
    client, test_db, advisor_headers
):
    payload = _workbook_bytes(
        [
            [
                "Full Name",
                "Business Name",
                "ID Number",
                "Phone (optional)",
                "Email (optional)",
            ],
            [
                "יוסי כהן",
                "יוסי כהן ייעוץ",
                "123456789",
                "0501234567",
                "yossi@example.com",
            ],
        ]
    )

    response = client.post(
        "/api/v1/clients/import",
        headers={**advisor_headers, **IDEMPOTENCY_HEADER},
        files={
            "file": (
                "clients.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["created"] == 1
    assert test_db.scalar(select(func.count(ClientRecord.id))) == 1


def test_import_clients_excel_rejects_large_content_length(client, advisor_headers):
    payload = _workbook_bytes(
        [
            ["full_name", "business_name", "id_number"],
            ["Big", "Big Business", "730000001"],
        ]
    )

    response = client.post(
        "/api/v1/clients/import",
        headers={
            **advisor_headers,
            **IDEMPOTENCY_HEADER,
            "Content-Length": str(11 * 1024 * 1024),
        },
        files={
            "file": (
                "clients.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 413


def test_import_clients_excel_invalid_file(client, advisor_headers):
    response = client.post(
        "/api/v1/clients/import",
        headers={**advisor_headers, **IDEMPOTENCY_HEADER},
        files={"file": ("bad.xlsx", b"not-an-excel", "application/octet-stream")},
    )

    assert response.status_code == 400


def test_import_clients_excel_rejects_large_body_without_content_length(
    client, advisor_headers, monkeypatch
):
    monkeypatch.setattr(clients_excel_api, "MAX_UPLOAD_SIZE", 32)
    payload = b"x" * 40

    response = client.post(
        "/api/v1/clients/import",
        headers={**advisor_headers, **IDEMPOTENCY_HEADER},
        files={
            "file": (
                "clients.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 413


def test_import_clients_excel_requires_idempotency_key(client, advisor_headers):
    payload = _workbook_bytes(
        [
            ["full_name", "business_name", "id_number"],
            ["Missing Key", "Missing Key Business", "770000001"],
        ]
    )

    response = client.post(
        "/api/v1/clients/import",
        headers=advisor_headers,
        files={
            "file": (
                "clients.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"] == [
        {
            "field": "X-Idempotency-Key",
            "message": "Field required",
            "type": "missing",
        }
    ]
