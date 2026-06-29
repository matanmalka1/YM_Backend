from sqlalchemy.orm import Session

from app.charges.charge_messages import BULK_ACTION_INTERNAL_ERROR
from app.charges.schemas.charge import BulkChargeFailedItem
from app.charges.services.charge_billing_service import BillingService
from app.core.exceptions import AppError


class BulkBillingService:
    """Bulk charge action logic."""

    def __init__(self, db: Session):
        self.billing = BillingService(db)

    def bulk_action(
        self,
        charge_ids: list[int],
        action: str,
        actor_id: int | None = None,
        cancellation_reason: str | None = None,
        actor_name: str | None = None,
    ) -> tuple[list[int], list[BulkChargeFailedItem]]:
        """
        Apply action to multiple charges.

        Returns (succeeded_ids, failed_items). Never raises on partial failure.
        """
        succeeded: list[int] = []
        failed: list[BulkChargeFailedItem] = []

        for charge_id in charge_ids:
            try:
                if action == "issue":
                    self.billing.issue_charge(charge_id, actor_id=actor_id, actor_name=actor_name)
                elif action == "mark-paid":
                    self.billing.mark_charge_paid(
                        charge_id, actor_id=actor_id, actor_name=actor_name
                    )
                elif action == "cancel":
                    self.billing.cancel_charge(
                        charge_id,
                        actor_id=actor_id,
                        reason=cancellation_reason,
                        actor_name=actor_name,
                    )
                succeeded.append(charge_id)
            except AppError as exc:
                failed.append(BulkChargeFailedItem(id=charge_id, error=exc.message))
            except Exception:
                failed.append(BulkChargeFailedItem(id=charge_id, error=BULK_ACTION_INTERNAL_ERROR))

        return succeeded, failed
