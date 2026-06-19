"""Guards that every endpoint outside the public allowlist truly requires auth.

OpenAPI ``security`` is documentation only; these tests assert the *runtime*
dependency (``get_current_user``, possibly via ``require_role``) is present, and
that the generated spec stays consistent with the allowlist.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi.dependencies.models import Dependant

from app.core.public_endpoints import PUBLIC_ENDPOINTS
from app.main import app
from app.users.api.user_deps import get_current_user

_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _flatten_calls(dependant: Dependant) -> Iterator[object]:
    """Yield every dependency callable in the tree, including nested ones."""
    if dependant.call is not None:
        yield dependant.call
    for sub in dependant.dependencies:
        yield from _flatten_calls(sub)


def _routed_operations() -> Iterator[tuple[str, str, object]]:
    """Yield (method, path, dependant) for each concrete API operation."""
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if dependant is None or methods is None or path is None:
            continue
        for method in methods:
            if method in _HTTP_METHODS:
                yield method, path, dependant


def test_every_non_public_endpoint_requires_auth():
    offenders = []
    for method, path, dependant in _routed_operations():
        if (method, path) in PUBLIC_ENDPOINTS:
            continue
        if get_current_user not in set(_flatten_calls(dependant)):
            offenders.append((method, path))

    assert not offenders, (
        "Endpoints missing an auth dependency (add get_current_user/require_role, "
        f"or allowlist in app/core/public_endpoints.py): {sorted(offenders)}"
    )


def test_public_allowlist_has_no_stale_entries():
    actual = {(method, path) for method, path, _ in _routed_operations()}
    missing = PUBLIC_ENDPOINTS - actual
    assert not missing, f"Allowlist references endpoints that do not exist: {sorted(missing)}"

    now_requires_auth = []
    for method, path, dependant in _routed_operations():
        if (method, path) not in PUBLIC_ENDPOINTS:
            continue
        if get_current_user in set(_flatten_calls(dependant)):
            now_requires_auth.append((method, path))
    assert not now_requires_auth, (
        "Allowlisted endpoints now require auth and should be removed from the "
        f"allowlist: {sorted(now_requires_auth)}"
    )


def test_openapi_security_defaults_and_overrides():
    schema = app.openapi()

    assert schema["security"] == [{"HTTPBearer": []}]
    assert schema["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }

    paths = schema["paths"]

    # Every public operation explicitly opts out.
    for method, path in PUBLIC_ENDPOINTS:
        operation = paths[path][method.lower()]
        assert operation.get("security") == [], (method, path)

    # No non-public operation may carry security: [] (which would silently
    # mark it public in the spec), and protected operations should inherit the
    # global default instead of repeating HTTPBearer per operation.
    public_leaks = []
    repeated_defaults = []
    for path, item in paths.items():
        for method, operation in item.items():
            if method.upper() not in _HTTP_METHODS:
                continue
            if (method.upper(), path) in PUBLIC_ENDPOINTS:
                continue
            if operation.get("security") == []:
                public_leaks.append((method.upper(), path))
            if operation.get("security") == [{"HTTPBearer": []}]:
                repeated_defaults.append((method.upper(), path))
    assert not public_leaks, (
        f"Non-public operations marked security: [] in spec: {sorted(public_leaks)}"
    )
    assert not repeated_defaults, (
        "Protected operations should inherit global HTTPBearer security instead "
        f"of repeating it: {sorted(repeated_defaults)}"
    )
