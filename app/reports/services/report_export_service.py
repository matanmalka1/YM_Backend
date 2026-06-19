from __future__ import annotations

from app.reports.exporters.excel_exporter import export_aging_report_to_excel
from app.reports.exporters.pdf_exporter import export_aging_report_to_pdf
from app.reports.report_constants import EXPORT_TEMP_DIR


class ExportService:
    """
    Report export service for Excel and PDF.

    Generates downloadable files from report data.
    """

    def __init__(self):
        EXPORT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self.export_dir = str(EXPORT_TEMP_DIR)

    def export_aging_report_to_excel(self, report_data: dict) -> dict[str, object]:
        """Export aging report to Excel format."""
        return export_aging_report_to_excel(report_data, self.export_dir)

    def export_aging_report_to_pdf(self, report_data: dict) -> dict[str, object]:
        """Export aging report to PDF format."""
        return export_aging_report_to_pdf(report_data, self.export_dir)
