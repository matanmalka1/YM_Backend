"""Shared helpers for annual-report mutations and audit payloads."""

from decimal import Decimal
from enum import Enum

from sqlalchemy.orm import Session

from app.annual_reports.annual_report_messages import (
    ANNUAL_REPORT_CLIENT_NOT_FOUND,
    CLIENT_CLOSED_FINANCIAL_MUTATION_ERROR,
    CLIENT_FROZEN_FINANCIAL_MUTATION_ERROR,
)
from app.clients.client_enums import ClientStatus
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.common.enums import ObligationStatus
from app.common.obligation_lifecycle import LOCKED_MESSAGE
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, ForbiddenError, NotFoundError


def audit_scalar(field_name: str, value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported audit scalar for field '{field_name}': {type(value).__name__}")


def income_line_snapshot(line) -> dict:
    return {
        "line_id": line.id,
        "source_type": audit_scalar("source_type", line.source_type),
        "amount": audit_scalar("amount", line.amount),
        "description": audit_scalar("description", line.description),
    }


def expense_line_snapshot(line) -> dict:
    return {
        "line_id": line.id,
        "category": audit_scalar("category", line.category),
        "amount": audit_scalar("amount", line.amount),
        "recognition_rate": audit_scalar("recognition_rate", line.recognition_rate),
        "external_document_reference": audit_scalar(
            "external_document_reference", line.external_document_reference
        ),
        "supporting_document_id": audit_scalar(
            "supporting_document_id", line.supporting_document_id
        ),
        "description": audit_scalar("description", line.description),
    }


def assert_report_unlocked(report) -> None:
    """D-13: nothing on a submitted report changes — every change is an amendment.

    Answers a different question from :func:`assert_client_allows_financial_mutation`:
    that one asks about the *client's* standing, this one about the *report's* own
    lifecycle. Mutation paths need both.
    """
    if report.status == ObligationStatus.SUBMITTED:
        raise AppError(LOCKED_MESSAGE, ErrorCode.OBLIGATION_LOCKED)


def assert_client_allows_financial_mutation(db: Session, client_record_id: int) -> None:
    client_record = ClientRecordRepository(db).get_by_id(client_record_id)
    if client_record is None:
        raise NotFoundError(
            ANNUAL_REPORT_CLIENT_NOT_FOUND.format(client_record_id=client_record_id),
            ErrorCode.CLIENT_RECORD_NOT_FOUND,
        )
    if client_record.status == ClientStatus.CLOSED:
        raise ForbiddenError(CLIENT_CLOSED_FINANCIAL_MUTATION_ERROR, ErrorCode.CLIENT_CLOSED)
    if client_record.status == ClientStatus.FROZEN:
        raise ForbiddenError(CLIENT_FROZEN_FINANCIAL_MUTATION_ERROR, ErrorCode.CLIENT_FROZEN)
