from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.media_types import PDF_MEDIA_TYPE
from app.reports.advance_payment_report import AdvancePaymentReportService
from app.reports.services.report_export_service import ExportService
from app.reports.services.report_service import AgingReportService

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class ReportExportResult:
    filepath: str
    filename: str
    media_type: str


class ReportsExportService:
    def __init__(self, db: Session):
        self.db = db
        self.report_service = AgingReportService(db)
        self.export_service = ExportService()

    def export_aging_report(
        self,
        *,
        export_format: str,
        as_of_date: date | None = None,
    ) -> ReportExportResult:
        report = self.report_service.generate_aging_report(as_of_date=as_of_date)
        try:
            if export_format == "excel":
                result = self.export_service.export_aging_report_to_excel(report)
                media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            else:
                result = self.export_service.export_aging_report_to_pdf(report)
                media_type = PDF_MEDIA_TYPE
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"ספריית הייצוא אינה מותקנת: {str(exc)}",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"הייצוא נכשל: {str(exc)}",
            ) from exc

        return ReportExportResult(
            filepath=str(result["filepath"]),
            filename=str(result["filename"]),
            media_type=media_type,
        )

    def export_advance_payment_report(
        self,
        *,
        export_format: str,
        year: int,
        month: int | None = None,
    ) -> ReportExportResult:
        report = AdvancePaymentReportService(self.db).get_collections_report(year, month)
        try:
            if export_format == "excel":
                result = self.export_service.export_advance_payment_report_to_excel(report)
                media_type = EXCEL_MEDIA_TYPE
            else:
                result = self.export_service.export_advance_payment_report_to_pdf(report)
                media_type = PDF_MEDIA_TYPE
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"ספריית הייצוא אינה מותקנת: {str(exc)}",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"הייצוא נכשל: {str(exc)}",
            ) from exc

        return ReportExportResult(
            filepath=str(result["filepath"]),
            filename=str(result["filename"]),
            media_type=media_type,
        )
