from datetime import date
from random import Random
from types import SimpleNamespace

from app.legal_entities.models.legal_entity import LegalEntity
from app.common.enums import AdvancePaymentFrequency
from app.seed.builders.clients import create_clients


def test_demo_seed_clients_get_advance_payment_frequency(test_db, test_user):
    cfg = SimpleNamespace(clients=4, reference_date=date(2026, 5, 7))

    pairs = create_clients(test_db, Random(42), cfg, [test_user])

    assert len(pairs) == 4
    frequencies = [
        test_db.get(LegalEntity, client.legal_entity_id).advance_payment_frequency
        for client, _business in pairs
    ]
    assert all(freq in set(AdvancePaymentFrequency) for freq in frequencies)
