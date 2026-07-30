from app.annual_reports.api import annual_report_routes_financials as financials_api


def test_create_income_line_accepts_zero_amount(
    client, advisor_headers, annual_report_service_factory
):
    report = annual_report_service_factory()

    resp = client.post(
        f"/api/v1/annual-reports/{report.id}/income",
        headers=advisor_headers,
        json={"source_type": "salary", "amount": 0, "description": "Zeroed correction"},
    )

    assert resp.status_code == 201
    assert resp.json()["amount"] == "0.00"


def test_auto_populate_response_contract_includes_skips_and_breakdown(
    client, advisor_headers, monkeypatch
):
    calls = []

    class _FakeVatImportService:
        def __init__(self, db):
            pass

        def auto_populate(self, report_id, force=False, actor_id=None, actor_name=None):
            calls.append(
                {
                    "report_id": report_id,
                    "force": force,
                    "actor_id": actor_id,
                    "actor_name": actor_name,
                }
            )
            return {
                "annual_report_id": report_id,
                "income_lines_created": 0,
                "expense_lines_created": 1,
                "income_total": "0.00",
                "expense_total": "1200.00",
                "lines_deleted": 0,
                "skipped_items": [
                    {
                        "item_type": "income",
                        "source": "business",
                        "amount": "-50.00",
                        "reason": "negative_total",
                        "annual_category": None,
                    }
                ],
                "warnings": ["VAT import skipped negative business income total."],
                "expense_breakdown": [
                    {
                        "annual_category": "vehicle",
                        "amount": "1200.00",
                        "source_vat_categories": {
                            "fuel": "800.00",
                            "vehicle_maintenance": "400.00",
                        },
                    }
                ],
            }

    monkeypatch.setattr(financials_api, "VatImportService", _FakeVatImportService)

    response = client.post(
        "/api/v1/annual-reports/123/auto-populate?force=true",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["report_id"] == 123
    assert calls[0]["force"] is True
    assert isinstance(calls[0]["actor_id"], int)
    payload = response.json()
    assert payload["skipped_items"] == [
        {
            "item_type": "income",
            "source": "business",
            "amount": "-50.00",
            "reason": "negative_total",
            "annual_category": None,
        }
    ]
    assert payload["expense_breakdown"][0]["source_vat_categories"] == {
        "fuel": "800.00",
        "vehicle_maintenance": "400.00",
    }
