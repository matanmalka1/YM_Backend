"""Backward-compatible import for the VAT work-item repository.

The implementation lives in ``vat_work_item_write_repository``. Some tests and
older callers still import the historical module path.
"""

from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)

__all__ = ["VatWorkItemRepository"]
