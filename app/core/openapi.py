"""Custom OpenAPI schema builder.

Makes ``HTTPBearer`` the global default security scheme so every operation is
documented as requiring a bearer token unless it explicitly opts out with
``security: []``. Public endpoints (see ``app/core/public_endpoints.py``) are
opted out here.

It also documents the two auth-driven error statuses globally instead of
per-route (#53):

- ``401`` on every non-public operation (a bearer token is always required).
- ``403`` on every operation whose route declares a ``require_role(...)``
  dependency.

Both reference the shared ``ErrorEnvelope`` schema. Per-route ``responses=``
only document the body-driven statuses (``400``/``404``/``409``/``500``).

Note: this is documentation only. Runtime auth is enforced by the
``get_current_user`` dependency, guarded by
``tests/core/test_endpoint_auth_guard.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

from app.core.public_endpoints import PUBLIC_ENDPOINTS

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi.dependencies.models import Dependant

_ERROR_ENVELOPE_REF = {"$ref": "#/components/schemas/ErrorEnvelope"}
_ERROR_RESPONSE_DESCRIPTIONS = {
    "400": "Bad request",
    "401": "Authentication required",
    "403": "Forbidden",
    "404": "Resource not found",
    "409": "Conflict",
    "500": "Internal server error",
}


def _error_response_doc(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": _ERROR_ENVELOPE_REF}},
    }


def _normalize_error_response_descriptions(responses: dict[str, Any]) -> None:
    for status_code, description in _ERROR_RESPONSE_DESCRIPTIONS.items():
        if status_code in responses:
            responses[status_code]["description"] = description


def _has_role_dependency(dependant: Dependant) -> bool:
    """True if this route (recursively) declares a ``require_role`` dependency."""
    for sub in dependant.dependencies:
        if getattr(sub.call, "__requires_role__", False):
            return True
        if _has_role_dependency(sub):
            return True
    return False


def _role_gated_operations(app: FastAPI) -> set[tuple[str, str]]:
    """Set of ``(METHOD, path)`` whose route is guarded by ``require_role``."""
    gated: set[tuple[str, str]] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not _has_role_dependency(route.dependant):
            continue
        for method in route.methods or set():
            gated.add((method.upper(), route.path))
    return gated


def build_openapi(app: FastAPI) -> dict[str, Any]:
    """Build (and cache) the OpenAPI schema with a global HTTPBearer default."""
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )

    # Global default: every operation requires a bearer token unless it opts out.
    schema["security"] = [{"HTTPBearer": []}]
    components = schema.setdefault("components", {})
    components.setdefault("securitySchemes", {})["HTTPBearer"] = {
        "type": "http",
        "scheme": "bearer",
    }

    role_gated = _role_gated_operations(app)
    has_error_envelope = "ErrorEnvelope" in components.get("schemas", {})

    http_methods = {"GET", "POST", "PUT", "PATCH", "DELETE"}
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            method_upper = method.upper()
            if method_upper not in http_methods:
                continue
            is_public = (method_upper, path) in PUBLIC_ENDPOINTS
            if is_public:
                operation["security"] = []
            elif operation.get("security") == [{"HTTPBearer": []}]:
                operation.pop("security")

            # Document auth-driven error statuses globally (only when the shared
            # ErrorEnvelope schema is present so the $ref resolves).
            if not has_error_envelope:
                continue
            responses = operation.setdefault("responses", {})
            if not is_public:
                responses.setdefault("401", _error_response_doc("Authentication required"))
            if (method_upper, path) in role_gated:
                responses.setdefault("403", _error_response_doc("Forbidden"))
            _normalize_error_response_descriptions(responses)

    app.openapi_schema = schema
    return schema
