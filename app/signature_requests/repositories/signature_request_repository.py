"""Repository entry point for SignatureRequest persistence."""

from sqlalchemy.orm import Session

from app.signature_requests.repositories.signature_request_crud import (
    SignatureRequestCrudMixin,
)


class SignatureRequestRepository(SignatureRequestCrudMixin):
    def __init__(self, db: Session):
        self.db = db


__all__ = ["SignatureRequestRepository"]
