from __future__ import annotations

import os
from datetime import datetime

from app.reports.report_constants import (
    AGING_EXPORT_FILENAME_PREFIX,
    AGING_EXPORT_HEADER_COLOR,
    AGING_REPORT_HEADERS,
)


def export_aging_report_to_pdf(report_data: dict, export_dir: str) -> dict[str, object]:
    """
    Build a PDF file for the aging report.
    Returns download metadata.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise ImportError(
            "הספרייה reportlab נדרשת לצורך ייצוא ל-PDF. יש להתקין באמצעות: pip install reportlab"
        ) from exc

    filename = f"{AGING_EXPORT_FILENAME_PREFIX}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = os.path.join(export_dir, filename)

    doc = SimpleDocTemplate(filepath, pagesize=landscape(A4))
    elements = []
    styles = getSampleStyleSheet()

    title = Paragraph(f"<b>דוח חובות ללקוחות - {report_data['report_date']}</b>", styles["Title"])
    elements.append(title)
    elements.append(Spacer(1, 0.5 * cm))

    table_data = [AGING_REPORT_HEADERS]

    for item in report_data["items"]:
        table_data.append(
            [
                item["client_name"],
                f"{item['total_outstanding']:.2f}",
                f"{item['current']:.2f}",
                f"{item['days_30']:.2f}",
                f"{item['days_60']:.2f}",
                f"{item['days_90_plus']:.2f}",
                str(item["oldest_invoice_date"]) if item["oldest_invoice_date"] else "",
                str(item["oldest_invoice_days"]) if item["oldest_invoice_days"] else "",
            ]
        )

    table_data.append(
        [
            "סיכום",
            f"{report_data['total_outstanding']:.2f}",
            f"{report_data['summary']['total_current']:.2f}",
            f"{report_data['summary']['total_30_days']:.2f}",
            f"{report_data['summary']['total_60_days']:.2f}",
            f"{report_data['summary']['total_90_plus']:.2f}",
            "",
            "",
        ]
    )

    table = Table(table_data)
    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor(f"#{AGING_EXPORT_HEADER_COLOR}"),
                ),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )

    elements.append(table)
    doc.build(elements)

    return {
        "filepath": filepath,
        "filename": filename,
        "format": "pdf",
        "generated_at": datetime.now(),
    }
