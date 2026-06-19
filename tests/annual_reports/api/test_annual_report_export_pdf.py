from app.annual_reports.api import annual_report_routes_export as export_api


class _FakePdfService:
    def __init__(self, db):
        self.db = db

    def generate(self, report_id):
        return (b"%PDF-1.4\n", 2026)


def test_export_pdf_endpoint_returns_stream(client, advisor_headers, monkeypatch):
    monkeypatch.setattr(export_api, "AnnualReportPdfService", _FakePdfService)

    resp = client.get("/api/v1/annual-reports/123/export/pdf", headers=advisor_headers)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert "annual_report_123_2026.pdf" in resp.headers["content-disposition"]
