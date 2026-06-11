from app.main import app


def test_audit_trail_endpoints_do_not_use_history_paths():
    paths = set(app.openapi()["paths"])

    forbidden_paths = [
        path
        for path in paths
        if "/history" in path
        and any(token in path for token in ("binders", "annual-reports", "vat", "users"))
    ]

    assert forbidden_paths == []
    assert "/api/v1/binders/{binder_id}/audit" in paths
    assert "/api/v1/annual-reports/{report_id}/audit" in paths
