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
    # Binder lifecycle audit moved to the generic /audit/binder/{id} route (Phase 5);
    # the per-domain binder audit route is removed.
    assert "/api/v1/binders/{binder_id}/audit" not in paths
    assert "/api/v1/annual-reports/{report_id}/audit" not in paths
