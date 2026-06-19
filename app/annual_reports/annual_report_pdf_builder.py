"""PDF builder helpers for annual report export."""

from __future__ import annotations

import io
import os
from datetime import datetime

from app.annual_reports.services.annual_report_labels import (
    CLIENT_TYPE_LABELS as _CLIENT_TYPE_LABELS,
)
from app.annual_reports.services.annual_report_labels import (
    EXPENSE_LABELS as _EXPENSE_LABELS,
)
from app.annual_reports.services.annual_report_labels import (
    INCOME_LABELS as _INCOME_LABELS,
)
from app.annual_reports.services.annual_report_labels import (
    STATUS_LABELS as _STATUS_LABELS,
)

# ── Palette ───────────────────────────────────────────────────────────────────
_C_HEADER = "#1E3A5F"  # deep navy — table header bg
_C_ACCENT = "#2E6DA4"  # mid blue — section label bar
_C_TOTAL_BG = "#DDE8F0"  # light blue — total/summary rows
_C_ALT = "#F4F7FB"  # very light blue — alternating rows
_C_BORDER = "#B0C4D8"  # soft blue-grey grid
_C_TEXT_LIGHT = "#FFFFFF"
_C_TEXT_DARK = "#1A1A2E"
_C_FOOTER_BG = "#F0F0F0"


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"₪{value:,.2f}"


_HEBREW_FONT_CANDIDATES = [
    os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "static",
            "fonts",
            "NotoSansHebrew.ttf",
        )
    ),
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/ArialHB.ttc",
    "/System/Library/Fonts/SFHebrew.ttf",
]


def _get_font() -> str:
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        for path in _HEBREW_FONT_CANDIDATES:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont("Hebrew", path))
                return "Hebrew"
    except Exception:
        pass
    return "Helvetica"


def _r(text: str) -> str:
    """Reorder Hebrew text to visual LTR order for reportlab (no shaping engine)."""
    try:
        from bidi.algorithm import get_display

        return get_display(text)
    except Exception:
        return text


def build_pdf(report, client_name: str, summary, tax, detail) -> bytes:  # noqa: ANN001
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    PAGE_W = A4[0] - 3 * cm  # usable width (1.5 cm margins each side)
    COL_LABEL = PAGE_W * 0.62
    COL_VAL = PAGE_W * 0.38

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.5 * cm,
    )
    font = _get_font()

    def _ps(name, size=9, color="#1A1A2E", leading=13, **kw) -> ParagraphStyle:
        return ParagraphStyle(
            name,
            fontName=font,
            fontSize=size,
            textColor=colors.HexColor(color),
            leading=leading,
            alignment=2,
            **kw,
        )  # 2 = TA_RIGHT

    s_title = _ps("title", size=16, color=_C_HEADER, spaceAfter=2)
    s_meta = _ps("meta", size=9, color="#555555", spaceAfter=1)
    s_section = _ps("section", size=10, color=_C_HEADER, spaceAfter=3)
    s_cell = _ps("cell", size=9, color=_C_TEXT_DARK)
    s_cell_hd = _ps("cell_hd", size=9, color=_C_TEXT_LIGHT)
    s_cell_tot = _ps("cell_tot", size=9, color=_C_TEXT_DARK)
    s_footer = _ps("footer", size=7.5, color="#666666")
    s_amt = _ps("amt", size=9, color=_C_TEXT_DARK)

    def p(text: str, style: ParagraphStyle) -> Paragraph:
        return Paragraph(_r(text), style)

    def amount(text: str, style: ParagraphStyle = s_amt) -> Paragraph:
        return Paragraph(text, style)

    _NUMERIC_STARTS = ("₪", "—", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9")

    def _val_cell(text: str, style) -> Paragraph:
        if not text or text[0] in _NUMERIC_STARTS:
            return amount(text, style)
        return p(text, style)

    def make_table(rows: list[list]) -> Table:
        n = len(rows)
        para_rows = []
        for i, row in enumerate(rows):
            is_hd = i == 0
            is_tot = i == n - 1
            st_lbl = s_cell_hd if is_hd else (s_cell_tot if is_tot else s_cell)
            st_amt = s_cell_hd if is_hd else (s_cell_tot if is_tot else s_amt)
            val_cell = p(row[1], st_amt) if is_hd else _val_cell(row[1], st_amt)
            para_rows.append([val_cell, p(row[0], st_lbl)])
        t = Table(para_rows, colWidths=[COL_VAL, COL_LABEL])
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_C_HEADER)),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, n - 1), (-1, n - 1), colors.HexColor(_C_TOTAL_BG)),
            ("TOPPADDING", (0, 1), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor(_C_BORDER)),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(_C_BORDER)),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ]
        for i in range(1, n - 1):
            if i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor(_C_ALT)))
        t.setStyle(TableStyle(style_cmds))
        return t

    def section_heading(title: str) -> list:
        bar = Table([[p(title, s_section)]], colWidths=[PAGE_W])
        bar.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_C_ACCENT)),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                ]
            )
        )
        return [bar, Spacer(1, 0.15 * cm)]

    elems: list = []
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    form_label = _CLIENT_TYPE_LABELS.get(report.client_type or "", report.client_type or "")
    status_val = report.status.value if hasattr(report.status, "value") else str(report.status)
    status_label = _STATUS_LABELS.get(status_val, status_val)

    elems.append(p("יועץ מס — טיוטה לעיון בלבד", s_title))
    elems.append(
        p(
            f"לקוח: {client_name}  |  שנת מס: {report.tax_year}  |  טופס: {form_label}",
            s_meta,
        )
    )
    elems.append(p(f"הופק: {now_str}", s_meta))
    elems.append(
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor(_C_ACCENT), spaceAfter=8)
    )

    elems += section_heading("פרטי הדוח")
    rows1 = [["שדה", "ערך"], ["סוג לקוח", form_label], ["סטטוס", status_label]]
    if report.ita_reference:
        rows1.append(["מספר תיק רשות המסים", report.ita_reference])
    elems.append(make_table(rows1))
    elems.append(Spacer(1, 0.35 * cm))

    elems += section_heading("הכנסות")
    rows2 = [["מקור הכנסה", "סכום"]]
    for line in summary.income_lines:
        src = line.source_type if isinstance(line.source_type, str) else line.source_type.value
        rows2.append([_INCOME_LABELS.get(src, src), _fmt(line.amount)])
    rows2.append(['סה"כ הכנסות', _fmt(summary.total_income)])
    elems.append(make_table(rows2))
    elems.append(Spacer(1, 0.35 * cm))

    elems += section_heading("הוצאות")
    rows3 = [["קטגוריה", "סכום מוכר"]]
    for line in summary.expense_lines:
        cat = line.category if isinstance(line.category, str) else line.category.value
        rows3.append([_EXPENSE_LABELS.get(cat, cat), _fmt(line.recognized_amount)])
    rows3.append(['סה"כ הוצאות מוכרות', _fmt(summary.recognized_expenses)])
    elems.append(make_table(rows3))
    elems.append(Spacer(1, 0.35 * cm))

    elems += section_heading("חישוב מס")
    eff = f"{tax.effective_rate:.1f}%" if tax.effective_rate is not None else "—"
    rows4 = [
        ["פריט", "סכום"],
        ["הכנסה חייבת", _fmt(tax.taxable_income)],
        ["ניכוי פנסיה", _fmt(tax.pension_deduction)],
        ["מס לפני זיכויים", _fmt(tax.tax_before_credits)],
        ["זיכוי נקודות זיכוי", _fmt(tax.credit_points_value)],
        ["זיכוי תרומות", _fmt(tax.donation_credit)],
        ["זיכויים אחרים", _fmt(tax.other_credits)],
        ["מס לאחר זיכויים", _fmt(tax.tax_after_credits)],
        ["שיעור מס אפקטיבי", eff],
    ]
    elems.append(make_table(rows4))
    elems.append(Spacer(1, 0.35 * cm))

    ni = tax.national_insurance
    elems += section_heading("ביטוח לאומי")
    rows5 = [
        ["פריט", "סכום"],
        ["חלק בסיסי", _fmt(ni.base_amount)],
        ["חלק גבוה", _fmt(ni.high_amount)],
        ['סה"כ ביטוח לאומי', _fmt(ni.total)],
    ]
    elems.append(make_table(rows5))
    elems.append(Spacer(1, 0.35 * cm))

    refund = report.refund_due if report else None
    due = report.tax_due if report else None
    elems += section_heading("סיכום")
    rows6 = [
        ["פריט", "סכום"],
        ["החזר מס", _fmt(float(refund) if refund is not None else None)],
        ["חוב מס", _fmt(float(due) if due is not None else None)],
        ['סה"כ חבות (מס + ביטוח לאומי)', _fmt(tax.total_liability)],
    ]
    elems.append(make_table(rows6))
    elems.append(Spacer(1, 0.5 * cm))

    footer_table = Table(
        [[p("מסמך זה הופק לצרכי עיון בלבד ואינו תחליף לדיווח רשמי", s_footer)]],
        colWidths=[PAGE_W],
    )
    footer_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_C_FOOTER_BG)),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(_C_BORDER)),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    elems.append(footer_table)

    doc.build(elems)
    return buf.getvalue()


__all__ = ["build_pdf"]
