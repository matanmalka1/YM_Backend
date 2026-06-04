from app.businesses import constants
from app.common.enums import EntityType


def test_business_constants_imports_entity_type_from_shared_enum() -> None:
    expected = frozenset(
        {
            EntityType.OSEK_PATUR,
            EntityType.OSEK_MURSHE,
        }
    )

    assert constants._SOLE_TRADER_TYPES == expected
