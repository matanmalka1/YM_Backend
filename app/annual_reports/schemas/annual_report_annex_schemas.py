"""Per-schedule Pydantic validators for annual report annex data.

Each schedule maps to a Pydantic model that validates the `data` JSON field
stored in AnnualReportAnnexData. Validators are intentionally permissive — all
fields are optional so existing data is never rejected during incremental rollout.

SCHEDULE_VALIDATORS is the single lookup used by annex_service.py.
If a schedule has no validator defined, the data dict passes through unchanged.
"""

from decimal import Decimal

from pydantic import BaseModel


class ScheduleAData(BaseModel):
    """נספח א — חישוב הכנסה מעסק"""

    gross_income: Decimal | None = None
    cost_of_goods: Decimal | None = None
    gross_profit: Decimal | None = None
    operating_expenses: Decimal | None = None
    net_income: Decimal | None = None


class ScheduleBData(BaseModel):
    """נספח ב — הכנסות מדמי שכירות"""

    property_address: str | None = None
    rental_income: Decimal | None = None
    depreciation_claimed: Decimal | None = None
    maintenance_expenses: Decimal | None = None
    net_rental_income: Decimal | None = None


class ScheduleGimmelData(BaseModel):
    """נספח ג — רווח הון מניירות ערך סחירים"""

    security_name: str | None = None
    quantity: Decimal | None = None
    purchase_price: Decimal | None = None
    sale_price: Decimal | None = None
    gain_loss: Decimal | None = None


class ScheduleDaletData(BaseModel):
    """נספח ד — הכנסות מחו\"ל והמס ששולם שם"""

    country: str | None = None
    income_type: str | None = None
    gross_income: Decimal | None = None
    foreign_tax_paid: Decimal | None = None
    net_income: Decimal | None = None


class Form150Data(BaseModel):
    """טופס 150 — החזקה בחבר בני אדם תושב חוץ."""

    foreign_entity_name: str | None = None
    country: str | None = None
    holding_percentage: Decimal | None = None
    control_rights: str | None = None


class Form1504Data(BaseModel):
    """טופס 1504 — דיווח שותף בשותפות."""

    partnership_name: str | None = None
    partnership_id_number: str | None = None
    share_percentage: Decimal | None = None
    income_share: Decimal | None = None


class Form6111Data(BaseModel):
    """טופס 6111 — קידוד דוחות כספיים."""

    turnover_amount: Decimal | None = None
    accounting_method: str | None = None
    bookkeeping_basis: str | None = None


class Form1344Data(BaseModel):
    """טופס 1344 — דיווח על הפסדים רלוונטיים."""

    loss_type: str | None = None
    originating_year: int | None = None
    loss_amount: Decimal | None = None
    utilized_amount: Decimal | None = None


class Form1399Data(BaseModel):
    """טופס 1399 — הודעה על מכירת נכס ורווח הון."""

    asset_description: str | None = None
    sale_date: str | None = None
    proceeds_amount: Decimal | None = None
    cost_amount: Decimal | None = None
    capital_gain: Decimal | None = None


class Form1350Data(BaseModel):
    """טופס 1350 — משיכות בעל מניות מהותי."""

    company_name: str | None = None
    withdrawal_amount: Decimal | None = None
    withdrawal_date: str | None = None
    balance_at_year_end: Decimal | None = None


class Form1327Data(BaseModel):
    """טופס 1327 — דוח נאמנות."""

    trust_name: str | None = None
    trustee_name: str | None = None
    israel_income: Decimal | None = None
    foreign_income: Decimal | None = None


class Form1342Data(BaseModel):
    """טופס 1342 — פירוט נכסים שנתבע בגינם פחת."""

    asset_description: str | None = None
    asset_cost: Decimal | None = None
    depreciation_rate: Decimal | None = None


class Form1343Data(BaseModel):
    """טופס 1343 — ניכוי נוסף בשל פחת."""

    asset_description: str | None = None
    qualifying_amount: Decimal | None = None
    extra_deduction_amount: Decimal | None = None


class Form1348Data(BaseModel):
    """טופס 1348 — הצהרת אי-תושבות ישראל."""

    foreign_residency_country: str | None = None
    days_in_israel: int | None = None
    tie_breaker_basis: str | None = None


class Form858Data(BaseModel):
    """טופס 858 — יחידות השתתפות בשותפות נפט."""

    partnership_name: str | None = None
    units_held: Decimal | None = None
    income_share: Decimal | None = None
    expense_share: Decimal | None = None


SCHEDULE_VALIDATORS: dict[str, type[BaseModel]] = {
    "schedule_a": ScheduleAData,
    "schedule_b": ScheduleBData,
    "schedule_gimmel": ScheduleGimmelData,
    "schedule_dalet": ScheduleDaletData,
    "form_150": Form150Data,
    "form_1504": Form1504Data,
    "form_6111": Form6111Data,
    "form_1344": Form1344Data,
    "form_1399": Form1399Data,
    "form_1350": Form1350Data,
    "form_1327": Form1327Data,
    "form_1342": Form1342Data,
    "form_1343": Form1343Data,
    "form_1348": Form1348Data,
    "form_858": Form858Data,
}
