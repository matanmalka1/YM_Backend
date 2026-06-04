"""Shared helpers for annual-report financial line mutations and audit payloads."""

from sqlalchemy.orm import Session

from app.annual_reports.services.messages import (
    CLIENT_CLOSED_FINANCIAL_MUTATION_ERROR,
    CLIENT_FROZEN_FINANCIAL_MUTATION_ERROR,
)
from app.clients.enums import ClientStatus
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import ForbiddenError


def audit_scalar(value):
    return value.value if hasattr(value, "value") else str(value) if value is not None else None


def income_line_snapshot(line) -> dict:
    return {
        "line_id": line.id,
        "source_type": audit_scalar(line.source_type),
        "amount": str(line.amount),
        "description": line.description,
    }


def expense_line_snapshot(line) -> dict:
    return {
        "line_id": line.id,
        "category": audit_scalar(line.category),
        "amount": str(line.amount),
        "recognition_rate": str(line.recognition_rate),
        "external_document_reference": line.external_document_reference,
        "supporting_document_id": line.supporting_document_id,
        "description": line.description,
    }


def assert_client_allows_financial_mutation(db: Session, client_record_id: int) -> None:
    client_record = ClientRecordRepository(db).get_by_id(client_record_id)
    if client_record and client_record.status == ClientStatus.CLOSED:
        raise ForbiddenError(CLIENT_CLOSED_FINANCIAL_MUTATION_ERROR, "CLIENT.CLOSED")
    if client_record and client_record.status == ClientStatus.FROZEN:
        raise ForbiddenError(CLIENT_FROZEN_FINANCIAL_MUTATION_ERROR, "CLIENT.FROZEN")
