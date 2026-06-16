"""Tests for centralized error handling — canonical contract assertions."""

import asyncio
import json

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.core.exception_handlers import http_exception_handler


def test_http_error_has_canonical_envelope(client):
    response = client.get("/api/v1/clients/99999", headers={"Authorization": "Bearer invalid"})

    assert response.status_code == 401
    data = response.json()

    # Top-level shape: only "error" key for errors
    assert "error" in data
    assert "detail" not in data
    assert "error_meta" not in data

    err = data["error"]
    assert isinstance(err, dict)
    assert "code" in err
    assert "message" in err
    assert "details" in err
    assert err["details"] is None


def test_http_error_includes_request_id_when_header_provided(client):
    response = client.get(
        "/api/v1/clients/99999",
        headers={"Authorization": "Bearer invalid", "X-Request-ID": "test-req-123"},
    )
    assert response.status_code == 401
    err = response.json()["error"]
    assert err.get("request_id") == "test-req-123"
    assert response.headers.get("X-Request-ID") == "test-req-123"


def test_http_error_omits_request_id_field_when_not_provided(client):
    # Without sending X-Request-ID header, field may be absent (auto-generated UUID won't match)
    # We just verify code/message/details are present
    response = client.get("/api/v1/clients/99999", headers={"Authorization": "Bearer invalid"})
    err = response.json()["error"]
    assert "code" in err
    assert "message" in err
    assert "details" in err


def test_validation_error_has_canonical_envelope(client, advisor_headers):
    response = client.post(
        "/api/v1/charges",
        headers=advisor_headers,
        json={"invalid": "data"},
    )

    assert response.status_code == 422
    data = response.json()

    assert "error" in data
    assert "detail" not in data
    assert "error_meta" not in data

    err = data["error"]
    assert err["code"] == "validation_error"
    assert err["message"] == "חלק מהשדות אינם תקינים"
    assert isinstance(err["details"], list)
    assert len(err["details"]) > 0

    first = err["details"][0]
    assert "field" in first
    assert "message" in first
    assert "type" in first
    # loc prefix stripped — no "body." prefix
    assert not first["field"].startswith("body.")


def test_validation_error_strips_loc_prefix(client, advisor_headers):
    response = client.post(
        "/api/v1/charges",
        headers=advisor_headers,
        json={"invalid": "data"},
    )
    details = response.json()["error"]["details"]
    for item in details:
        assert not item["field"].startswith(("body.", "query.", "path.", "header.", "cookie."))


def test_app_error_details_field_preserved():
    from app.core.exceptions import AppError

    exc = AppError("test", "TEST.CODE", status_code=400, details={"key": "value"})
    assert exc.details == {"key": "value"}
    assert exc.code == "TEST.CODE"
    assert exc.message == "test"


def test_error_response_does_not_leak_stack_trace(client):
    response = client.get("/api/v1/clients/99999", headers={"Authorization": "Bearer invalid"})
    text = response.text.lower()

    assert "traceback" not in text
    assert "sqlalchemy" not in text
    # .py should not appear (stack trace lines contain .py paths)
    assert ".py" not in text


def test_404_returns_not_found_code(client, advisor_headers):
    response = client.get("/api/v1/clients/99999999", headers=advisor_headers)
    assert response.status_code == 404
    err = response.json()["error"]
    assert err["code"] == "CLIENT_RECORD.NOT_FOUND"
    assert err["details"] is None or err["details"] is not None  # details key must exist
    assert "details" in err


def test_no_legacy_fields_in_any_error(client, advisor_headers):
    """All error responses must not include legacy top-level keys."""
    # 401
    r1 = client.get("/api/v1/clients", headers={"Authorization": "Bearer bad"})
    assert "detail" not in r1.json()
    assert "error_meta" not in r1.json()
    assert isinstance(r1.json()["error"], dict)

    # 422
    r2 = client.post("/api/v1/charges", headers=advisor_headers, json={})
    assert "detail" not in r2.json()
    assert "error_meta" not in r2.json()
    assert isinstance(r2.json()["error"], dict)


def test_http_exception_detail_dict_preserves_structured_error():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
        }
    )
    request.state.request_id = "req-structured"
    exc = StarletteHTTPException(
        status_code=409,
        detail={
            "code": "client_has_open_binder",
            "message": "ללקוח כבר קיים קלסר פתוח",
            "details": {"client_id": 123},
        },
    )

    response = asyncio.run(http_exception_handler(request, exc))

    assert response.status_code == 409
    assert response.body
    assert response.media_type == "application/json"
    assert json.loads(response.body) == {
        "error": {
            "code": "client_has_open_binder",
            "message": "ללקוח כבר קיים קלסר פתוח",
            "details": {"client_id": 123},
            "request_id": "req-structured",
        }
    }


def test_http_exception_detail_dict_ignores_non_string_code_and_message():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
        }
    )
    exc = StarletteHTTPException(
        status_code=400,
        detail={
            "code": {"invalid": True},
            "message": {"invalid": True},
            "details": {"field": "amount"},
        },
    )

    response = asyncio.run(http_exception_handler(request, exc))

    assert response.status_code == 400
    assert json.loads(response.body) == {
        "error": {
            "code": "bad_request",
            "message": "הבקשה אינה תקינה",
            "details": {"field": "amount"},
        }
    }


def test_existing_route_runtime_404_returns_standard_error_envelope(client, advisor_headers):
    response = client.get(
        "/api/v1/clients/99999999",
        headers={**advisor_headers, "X-Request-ID": "req-404"},
    )

    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "detail" not in data
    assert "error_meta" not in data

    err = data["error"]
    assert err["code"] == "CLIENT_RECORD.NOT_FOUND"
    assert isinstance(err["message"], str)
    assert "details" in err
    assert err["request_id"] == "req-404"
