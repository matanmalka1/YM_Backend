"""Correcting a closed annual report, by creating a second row for it (D-10, D-21).

Annual reports had the opposite mechanism to VAT's: ``amend_report`` reopened the
same row back to ``in_preparation``, so "closed" only ever meant "closed for
now". That endpoint was already removed in W2 — it became unreachable under the
shared graph, which forbids leaving ``submitted`` (§4.1.5) — leaving the domain
with no correction path at all. This is the replacement.

The copy is deep: the detail row, the income and expense lines, the credit-point
reasons, and the schedule entries with their annex data. All of it is "the
material", and D-21 is explicit that the material already exists — only the
figures are wrong.
"""

from app.annual_reports.annual_report_messages import ANNUAL_REPORT_NOT_FOUND
from app.annual_reports.models.annual_report_model import AnnualReport
from app.audit.audit_constants import ACTION_ANNUAL_REPORT_AMENDED, ENTITY_ANNUAL_REPORT
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.common.enums import ObligationStatus
from app.common.obligation_chain import assert_amendable, copy_for_amendment, select_chain
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError

#: Annual's own closing and deadline facts.
#:
#: ``filing_deadline`` goes for the same reason as VAT's due dates: an amendment
#: is not a new obligation and carries no deadline (D-14). ``deadline_type`` is
#: kept — it records *which regime applied to the period*, which is still true
#: of the correction, and it is NOT NULL.
#:
#: The **tax result** goes too, and that is a judgement rather than a rule.
#: ``tax_due`` / ``refund_due`` are the answer computed from the lines, and the
#: whole reason an amendment exists is that the answer was wrong. Carrying it
#: over would also satisfy the closing gate — which requires a persisted tax
#: result — so a correction could be closed on the figures it was opened to
#: correct, without anyone recomputing.
_ANNUAL_CLOSING_FACTS = frozenset(
    {
        "filing_deadline",
        "custom_deadline_note",
        "extension_reason",
        "submission_method",
        "ita_reference",
        "assessment_amount",
        "tax_due",
        "refund_due",
    }
)


def create_amendment(
    report_repo,
    *,
    report_id: int,
    actor_id: int,
    actor_display_name: str | None = None,
) -> AnnualReport:
    """Open a correction of a closed annual report."""
    original = report_repo.get_by_id_for_update(report_id)
    if original is None:
        raise NotFoundError(
            ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
            ErrorCode.ANNUAL_REPORT_NOT_FOUND,
        )

    assert_amendable(original)

    amendment = report_repo.create_amendment(
        original,
        fields={
            **copy_for_amendment(original, also_exclude=_ANNUAL_CLOSING_FACTS),
            # D-21: the material already exists, so nothing is being waited for.
            "status": ObligationStatus.IN_PROGRESS,
            "created_by": actor_id,
        },
    )

    EntityAuditWriter(report_repo.db).record_action(
        ENTITY_ANNUAL_REPORT,
        amendment.id,
        actor_id,
        ACTION_ANNUAL_REPORT_AMENDED,
        new_value={"amends_id": original.id, "tax_year": amendment.tax_year},
        actor_display_name=actor_display_name,
        metadata_json={
            "client_record_id": amendment.client_record_id,
            "tax_year": amendment.tax_year,
        },
    )

    return amendment


def list_chain(report_repo, *, report_id: int) -> list[AnnualReport]:
    """Every report for this tax year, oldest first — the correction history."""
    report = report_repo.get(report_id)
    if report is None:
        raise NotFoundError(
            ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
            ErrorCode.ANNUAL_REPORT_NOT_FOUND,
        )
    return list(
        report_repo.db.scalars(
            select_chain(
                AnnualReport,
                client_record_id=report.client_record_id,
                period_column=AnnualReport.tax_year,
                period_value=report.tax_year,
            )
        ).all()
    )
