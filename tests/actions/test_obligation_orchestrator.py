import pytest

from app.actions.services import obligation_orchestrator as orchestrator
from app.common.enums import EntityType


def test_derive_client_type_raises_for_missing_or_unknown_entity_type():
    with pytest.raises(ValueError, match="סוג ישות לא נתמך ליצירת דוח שנתי"):
        orchestrator._derive_client_type(None)

    with pytest.raises(ValueError, match="סוג ישות לא נתמך ליצירת דוח שנתי"):
        orchestrator._derive_client_type("unknown")  # type: ignore[arg-type]


def test_derive_client_type_maps_supported_entity_type():
    client_type = orchestrator._derive_client_type(EntityType.OSEK_MURSHE)

    assert client_type.value == "self_employed"
