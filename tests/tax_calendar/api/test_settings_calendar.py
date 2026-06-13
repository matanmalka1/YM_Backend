from app.tax_calendar.services.bootstrap import (
    DEFAULT_DEADLINE_RULES,
    bootstrap_tax_calendar,
    seed_default_deadline_rules,
)

RULES_PATH = "/api/v1/settings/tax-calendar/rules"
ENTRIES_PATH = "/api/v1/settings/tax-calendar/entries"
SUMMARY_PATH = "/api/v1/settings/tax-calendar/summary"
BOOTSTRAP_PATH = "/api/v1/settings/tax-calendar/bootstrap"

_EXPECTED_RULE_KEYS = {d.rule_type.value for d in DEFAULT_DEADLINE_RULES}


# --- /rules ---


def test_list_rules_response_shape(client, advisor_headers, test_db):
    seed_default_deadline_rules(test_db)
    test_db.commit()

    response = client.get(RULES_PATH, headers=advisor_headers)
    rule = response.json()[0]
    assert set(rule.keys()) >= {
        "id",
        "rule_type",
        "due_day_of_month",
        "offset_months",
        "effective_from",
    }
    assert rule["rule_type"] in _EXPECTED_RULE_KEYS


def test_list_rules_unauthenticated_returns_401(client, test_db):
    response = client.get(RULES_PATH)
    assert response.status_code == 401


def test_list_rules_secretary_returns_403(client, secretary_headers, test_db):
    response = client.get(RULES_PATH, headers=secretary_headers)
    assert response.status_code == 403


# --- /entries ---


def test_list_entries_year_filter(client, advisor_headers, test_db):
    bootstrap_tax_calendar(test_db, start_year=2026, end_year=2027)
    test_db.commit()

    response = client.get(
        f"{ENTRIES_PATH}?tax_year_after=2026&tax_year_before=2026", headers=advisor_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 37
    assert all(e["tax_year"] == 2026 for e in data)


def test_list_entries_unauthenticated_returns_401(client, test_db):
    response = client.get(ENTRIES_PATH)
    assert response.status_code == 401


def test_list_entries_secretary_returns_403(client, secretary_headers, test_db):
    response = client.get(ENTRIES_PATH, headers=secretary_headers)
    assert response.status_code == 403


def test_list_entries_invalid_year_range_returns_400(client, advisor_headers, test_db):
    response = client.get(
        f"{ENTRIES_PATH}?tax_year_after=2027&tax_year_before=2026", headers=advisor_headers
    )
    assert response.status_code == 400


# --- /summary ---


def test_summary_secretary_returns_403(client, secretary_headers, test_db):
    response = client.get(SUMMARY_PATH, headers=secretary_headers)
    assert response.status_code == 403


def test_summary_invalid_year_range_returns_400(client, advisor_headers, test_db):
    response = client.get(
        f"{SUMMARY_PATH}?tax_year_after=2027&tax_year_before=2026", headers=advisor_headers
    )
    assert response.status_code == 400


# --- /bootstrap ---


def test_bootstrap_creates_entries(client, advisor_headers, test_db):
    response = client.post(
        BOOTSTRAP_PATH,
        json={"tax_year_after": 2026, "tax_year_before": 2026},
        headers={**advisor_headers, "X-Idempotency-Key": "tax-calendar-bootstrap-1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tax_year_after"] == 2026
    assert data["tax_year_before"] == 2026
    assert data["entries_created"] == 37
    assert data["total_entries_for_range"] == 37


def test_bootstrap_without_idempotency_key_still_succeeds(client, advisor_headers, test_db):
    response = client.post(
        BOOTSTRAP_PATH,
        json={"tax_year_after": 2026, "tax_year_before": 2026},
        headers=advisor_headers,
    )
    assert response.status_code == 200


def test_bootstrap_secretary_returns_403(client, secretary_headers, test_db):
    response = client.post(
        BOOTSTRAP_PATH,
        json={"tax_year_after": 2026, "tax_year_before": 2026},
        headers={
            **secretary_headers,
            "X-Idempotency-Key": "tax-calendar-bootstrap-secretary",
        },
    )
    assert response.status_code == 403


def test_bootstrap_invalid_year_range_returns_400(client, advisor_headers, test_db):
    response = client.post(
        BOOTSTRAP_PATH,
        json={"tax_year_after": 2027, "tax_year_before": 2026},
        headers={**advisor_headers, "X-Idempotency-Key": "tax-calendar-bootstrap-2"},
    )
    assert response.status_code == 400
