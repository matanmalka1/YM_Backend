"""VAT export: PDF format."""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal

from bidi.algorithm import get_display

from app.vat.schemas.vat_client_summary_schema import VatPeriodRow


def _fmt(amount: Decimal | None) -> str:
    if amount is None:
        return "—"
    return f"{amount:.2f}"


def _hebrew(text: str) -> str:
    """Convert Hebrew text to RTL display format for ReportLab."""
    return get_display(text)


def export_vat_to_pdf(
    client_name: str,
    client_record_id: int,
    year: int,
    periods: list[VatPeriodRow],
    export_dir: str,
) -> dict[str, object]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise ImportError(
            "הספרייה reportlab נדרשת. יש להתקין באמצעות: pip install reportlab"
        ) from exc

    font_name = "Assistant"
    font_name_bold = "Assistant-Bold"
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        font_regular = os.path.join(project_root, "assets", "fonts", "Assistant-Regular.ttf")
        font_bold = os.path.join(project_root, "assets", "fonts", "Assistant-Bold.ttf")
        pdfmetrics.registerFont(TTFont(font_name, font_regular))
        pdfmetrics.registerFont(TTFont(font_name_bold, font_bold))
    except Exception as e:
        raise ImportError(
            f"Cannot load Hebrew fonts from {font_regular} or {font_bold}. "
            "Ensure assets/fonts/ directory contains Assistant-Regular.ttf and Assistant-Bold.ttf"
        ) from e

    filename = f"vat_{client_record_id}_{year}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = os.path.join(export_dir, filename)

    doc = SimpleDocTemplate(filepath, pagesize=landscape(A4))
    styles = getSampleStyleSheet()

    # Define custom styles for hierarchy
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontName=font_name_bold,
        fontSize=18,
        textColor=colors.HexColor("#366092"),
        alignment=2,  # Right align for RTL
    )
    subtitle_style = ParagraphStyle(
        "CustomSubtitle",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=12,
        textColor=colors.HexColor("#666666"),
        alignment=2,  # Right align for RTL
    )
    elements = []

    # Header Section: Client info (right) and Report type (left)
    header_data = [
        [
            Paragraph(
                f"<b>{_hebrew('דוח תקציר מע״מ')}</b><br/>{_hebrew(f'שנה: {year}')}",
                subtitle_style,
            ),
            Paragraph(f"<b>{_hebrew(client_name)}</b>", title_style),
        ]
    ]
    header_table = Table(header_data, colWidths=[12 * cm, 15 * cm])
    header_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, 0), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#366092")),
            ]
        )
    )
    elements.append(header_table)
    elements.append(Spacer(1, 0.4 * cm))

    table_data = [
        [_hebrew(col) for col in ["תקופה", "סטטוס", "עסקאות", "תשומות", "נטו", "סופי", "הוגש"]]
    ]
    totals = {"output": Decimal(0), "input": Decimal(0), "net": Decimal(0)}

    for p in periods:
        status_str = p.status.value if hasattr(p.status, "value") else str(p.status)
        filed = p.closed_at.strftime("%d/%m/%Y") if p.closed_at else "—"
        final = _fmt(p.final_vat_amount)
        table_data.append(
            [
                p.period,
                _hebrew(status_str),
                _fmt(p.total_output_vat),
                _fmt(p.total_input_vat),
                _fmt(p.net_vat),
                final,
                filed,
            ]
        )
        totals["output"] += p.total_output_vat
        totals["input"] += p.total_input_vat
        totals["net"] += p.net_vat

    table_data.append(
        [
            _hebrew("סה״כ"),
            "",
            _fmt(totals["output"]),
            _fmt(totals["input"]),
            _fmt(totals["net"]),
            "",
            "",
        ]
    )

    table = Table(
        table_data,
        colWidths=[2.2 * cm, 2.2 * cm, 3 * cm, 3 * cm, 2.8 * cm, 2.8 * cm, 3 * cm],
    )

    # Advanced table styling
    table_style_list = [
        # Header row styling
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#366092")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), font_name_bold),
        ("FONTSIZE", (0, 0), (-1, 0), 11),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("LEFTPADDING", (0, 0), (-1, 0), 10),
        ("RIGHTPADDING", (0, 0), (-1, 0), 10),
        ("ALIGN", (0, 0), (1, 0), "CENTER"),
        ("ALIGN", (2, 0), (-1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        # Data rows: zebra striping
        ("BACKGROUND", (0, 1), (-1, -2), colors.white),
        (
            "ROWBACKGROUNDS",
            (0, 1),
            (-1, -2),
            [colors.white, colors.HexColor("#F4F7F9")],
        ),
        ("FONTNAME", (0, 1), (-1, -2), font_name),
        ("FONTSIZE", (0, 1), (-1, -2), 10),
        ("TOPPADDING", (0, 1), (-1, -2), 8),
        ("BOTTOMPADDING", (0, 1), (-1, -2), 8),
        ("LEFTPADDING", (0, 1), (-1, -2), 10),
        ("RIGHTPADDING", (0, 1), (-1, -2), 10),
        # Data alignment: period and status centered, amounts right-aligned
        ("ALIGN", (0, 1), (1, -2), "CENTER"),
        ("ALIGN", (2, 1), (-1, -2), "RIGHT"),
        ("VALIGN", (0, 1), (-1, -2), "MIDDLE"),
        # Totals row styling
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E6EEF5")),
        ("FONTNAME", (0, -1), (-1, -1), font_name_bold),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("TOPPADDING", (0, -1), (-1, -1), 10),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
        ("LEFTPADDING", (0, -1), (-1, -1), 10),
        ("RIGHTPADDING", (0, -1), (-1, -1), 10),
        ("ALIGN", (0, -1), (1, -1), "CENTER"),
        ("ALIGN", (2, -1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, -1), (-1, -1), "MIDDLE"),
        ("LINEABOVE", (0, -1), (-1, -1), 2, colors.HexColor("#366092")),
        # Borders: horizontal only, no vertical borders, light grey
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#366092")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#D1D1D1")),
    ]

    table.setStyle(TableStyle(table_style_list))
    elements.append(table)
    elements.append(Spacer(1, 0.3 * cm))
    footer_style = ParagraphStyle(
        "CustomFooter",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=8,
        textColor=colors.HexColor("#999999"),
        alignment=2,  # Right align for RTL
    )
    elements.append(
        Paragraph(
            f"{_hebrew('נוצר')}: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            footer_style,
        )
    )

    doc.build(elements)
    return {
        "filepath": filepath,
        "filename": filename,
        "format": "pdf",
        "generated_at": datetime.now(),
    }
