"""Guards that every endpoint with an ID-like path param documents a 404.

API TODO #25. Endpoints that take an entity identifier in the path can return
404 at runtime; the OpenAPI spec must document it (model: ``ErrorEnvelope``) so
the generated frontend client and API docs cover the not-found case. Add the
404 via ``app.core.openapi_responses.not_found_response(description=...)`` on the route
decorator.

The check drives off ``app.openapi()`` path templates, NOT ``route.path``:
FastAPI normalizes path converters in the spec (``/reminders/{reminder_id:int}``
in ``route.path`` becomes ``/reminders/{reminder_id}`` in OpenAPI), and only the
normalized form matches ``ID_PARAM`` — so iterating OpenAPI is what keeps such
routes in scope.

``ALLOWED_NO_404`` is intentionally empty: there are currently no legitimate
exceptions. If one is ever added it MUST carry an inline comment explaining why
that endpoint cannot return 404.
"""

from __future__ import annotations

import re

from app.main import app

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

# Matches {id} or any {<name>_id} path-parameter segment in an OpenAPI template.
ID_PARAM = re.compile(r"\{(?:id|[A-Za-z0-9_]+_id)\}")

# (method, path) operations allowed to omit a documented 404. Keep empty;
# every entry must justify, inline, why the endpoint cannot return 404.
ALLOWED_NO_404: set[tuple[str, str]] = set()


def test_id_endpoints_document_404():
    spec = app.openapi()
    offenders: list[tuple[str, str]] = []

    for path, item in spec["paths"].items():
        if not ID_PARAM.search(path):
            continue
        for method, operation in item.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            if (method.upper(), path) in ALLOWED_NO_404:
                continue
            if "404" not in (operation.get("responses") or {}):
                offenders.append((method.upper(), path))

    assert not offenders, (
        "Endpoints with an ID-like path param are missing a documented 404. "
        "Add responses=not_found_response(description=...) from "
        f"app.core.openapi_responses to each route decorator: {sorted(offenders)}"
    )
