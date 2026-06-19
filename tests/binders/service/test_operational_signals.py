from datetime import date

from app.businesses.services.business_signals_service import SignalsService
from tests.helpers.identity import seed_business, seed_client_identity


def test_operational_signals_missing_documents(test_db, test_user):
    """Test operational signals report missing documents."""
    client = seed_client_identity(
        test_db,
        full_name="Signals Test Client",
        id_number="888888888",
    )
    business = seed_business(
        test_db,
        legal_entity_id=client.legal_entity_id,
        business_name="Signals Business",
        opened_at=date.today(),
        created_by=test_user.id,
    )
    test_db.commit()
    test_db.refresh(business)
    business.client_id = client.id

    service = SignalsService(test_db)
    signals = service.compute_business_operational_signals(business.id)

    assert signals["business_id"] == business.id
    assert len(signals["missing_documents"]) == 3
