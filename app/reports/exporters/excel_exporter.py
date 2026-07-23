from __future__ import annotations

from datetime import datetime

from app.reports.report_constants import (
    ADVANCE_PAYMENT_EXPORT_FILENAME_PREFIX,
    ADVANCE_PAYMENT_REPORT_HEADERS,
    ADVANCE_PAYMENT_REPORT_TITLE,
    AGING_EXPORT_FILENAME_PREFIX,
    AGING_EXPORT_HEADER_COLOR,
    AGING_REPORT_HEADERS,
    AGING_REPORT_TITLE,
)
from app.utils.excel import adjust_column_widths, save_workbook_to_temp


def export_aging_report_to_excel(report_data: dict, export_dir: str) -> dict[str, object]:
    """
    Build an Excel file for the aging report.
    Returns download metadata.
    """
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as exc:
        raise ImportError(
            "הספרייה openpyxl נדרשת לצורך ייצוא לאקסל. יש להתקין באמצעות: pip install openpyxl"
        ) from exc

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = AGING_REPORT_TITLE

    header_fill = PatternFill(
        start_color=AGING_EXPORT_HEADER_COLOR,
        end_color=AGING_EXPORT_HEADER_COLOR,
        fill_type="solid",
    )
    header_font = Font(bold=True, color="FFFFFF")
    header_alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells("A1:H1")
    title_cell = ws["A1"]
    title_cell.value = f"דוח חובות ללקוחות - {report_data['report_date']}"
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = header_alignment

    for col, header in enumerate(AGING_REPORT_HEADERS, start=1):
        cell = ws.cell(row=3, column=col)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment

    row = 4
    for item in report_data["items"]:
        ws.cell(row=row, column=1, value=item["client_name"])
        ws.cell(row=row, column=2, value=item["total_outstanding"])
        ws.cell(row=row, column=3, value=item["current"])
        ws.cell(row=row, column=4, value=item["days_30"])
        ws.cell(row=row, column=5, value=item["days_60"])
        ws.cell(row=row, column=6, value=item["days_90_plus"])
        ws.cell(
            row=row,
            column=7,
            value=str(item["oldest_invoice_date"]) if item["oldest_invoice_date"] else "",
        )
        ws.cell(row=row, column=8, value=item["oldest_invoice_days"] or "")
        row += 1

    row += 1
    summary_cell = ws.cell(row=row, column=1)
    summary_cell.value = "סיכום"
    summary_cell.font = Font(bold=True)

    ws.cell(row=row, column=2, value=report_data["total_outstanding"])
    ws.cell(row=row, column=3, value=report_data["summary"]["total_current"])
    ws.cell(row=row, column=4, value=report_data["summary"]["total_30_days"])
    ws.cell(row=row, column=5, value=report_data["summary"]["total_60_days"])
    ws.cell(row=row, column=6, value=report_data["summary"]["total_90_plus"])

    adjust_column_widths(ws)

    return save_workbook_to_temp(
        wb,
        prefix=AGING_EXPORT_FILENAME_PREFIX,
        export_dir=export_dir,
        extra_meta={"format": "excel", "generated_at": datetime.now()},
    )


def export_advance_payment_report_to_excel(report_data: dict, export_dir: str) -> dict[str, object]:
    """
    Build an Excel file for the advance-payment collections report.
    Returns download metadata.
    """
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as exc:
        raise ImportError(
            "הספרייה openpyxl נדרשת לצורך ייצוא לאקסל. יש להתקין באמצעות: pip install openpyxl"
        ) from exc

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = ADVANCE_PAYMENT_REPORT_TITLE
    ws.sheet_view.rightToLeft = True

    header_fill = PatternFill(
        start_color=AGING_EXPORT_HEADER_COLOR,
        end_color=AGING_EXPORT_HEADER_COLOR,
        fill_type="solid",
    )
    header_font = Font(bold=True, color="FFFFFF")
    header_alignment = Alignment(horizontal="center", vertical="center")

    period_label = (
        f"{report_data['month']:02d}/{report_data['year']}"
        if report_data.get("month")
        else str(report_data["year"])
    )
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(ADVANCE_PAYMENT_REPORT_HEADERS))
    title_cell = ws.cell(row=1, column=1)
    title_cell.value = f"{ADVANCE_PAYMENT_REPORT_TITLE} - {period_label}"
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = header_alignment

    for col, header in enumerate(ADVANCE_PAYMENT_REPORT_HEADERS, start=1):
        cell = ws.cell(row=3, column=col)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment

    row = 4
    for item in report_data["items"]:
        ws.cell(row=row, column=1, value=item["office_client_number"])
        ws.cell(row=row, column=2, value=item["client_name"])
        ws.cell(row=row, column=3, value=item["client_id_number"])
        ws.cell(row=row, column=4, value=item["total_expected"])
        ws.cell(row=row, column=5, value=item["total_paid"])
        ws.cell(row=row, column=6, value=item["gap"])
        ws.cell(row=row, column=7, value=item["overdue_count"])
        row += 1

    row += 1
    summary_cell = ws.cell(row=row, column=1)
    summary_cell.value = "סיכום"
    summary_cell.font = Font(bold=True)
    ws.cell(row=row, column=4, value=report_data["total_expected"])
    ws.cell(row=row, column=5, value=report_data["total_paid"])
    ws.cell(row=row, column=6, value=report_data["total_gap"])
    ws.cell(row=row, column=7, value=f'{report_data["collection_rate"]}% גבייה')

    adjust_column_widths(ws)

    return save_workbook_to_temp(
        wb,
        prefix=ADVANCE_PAYMENT_EXPORT_FILENAME_PREFIX,
        export_dir=export_dir,
        extra_meta={"format": "excel", "generated_at": datetime.now()},
    )
