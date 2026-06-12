"""#53: global 401/403 error-doc injection in build_openapi.

401 is documented on every non-public operation; 403 on every role-gated
operation. Both reference the shared ErrorEnvelope schema. Per-route responses=
only carry body-driven statuses (400/404/409/500).
"""

from app.core.openapi import _role_gated_operations
from app.core.public_endpoints import PUBLIC_ENDPOINTS
from app.main import app

_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_ENVELOPE_REF = "#/components/schemas/ErrorEnvelope"

# Public endpoints that legitimately document 401 per-route because invalid
# credentials / tokens are their documented failure mode.
_PUBLIC_WITH_EXPLICIT_401 = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
}


def _iter_operations():
    spec = app.openapi()
    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if method.upper() in _HTTP_METHODS:
                yield method.upper(), path, operation


def test_non_public_operations_document_401():
    missing = [
        (m, p)
        for m, p, op in _iter_operations()
        if (m, p) not in PUBLIC_ENDPOINTS and "401" not in (op.get("responses") or {})
    ]
    assert not missing


def test_public_operations_do_not_document_401_unless_explicit():
    violations = [
        (m, p)
        for m, p, op in _iter_operations()
        if (m, p) in PUBLIC_ENDPOINTS
        and (m, p) not in _PUBLIC_WITH_EXPLICIT_401
        and "401" in (op.get("responses") or {})
    ]
    assert not violations


def test_role_gated_operations_document_403():
    role_gated = _role_gated_operations(app)
    missing = [
        (m, p)
        for m, p, op in _iter_operations()
        if (m, p) in role_gated and "403" not in (op.get("responses") or {})
    ]
    assert not missing


def test_non_role_gated_operations_do_not_document_403():
    role_gated = _role_gated_operations(app)
    violations = [
        (m, p)
        for m, p, op in _iter_operations()
        if (m, p) not in role_gated and "403" in (op.get("responses") or {})
    ]
    assert not violations


def test_documented_401_and_403_use_error_envelope():
    bad = []
    for m, p, op in _iter_operations():
        for status_code in ("401", "403"):
            response = (op.get("responses") or {}).get(status_code)
            if not response:
                continue
            ref = (
                response.get("content", {})
                .get("application/json", {})
                .get("schema", {})
                .get("$ref")
            )
            if ref != _ENVELOPE_REF:
                bad.append((m, p, status_code))
    assert not bad
