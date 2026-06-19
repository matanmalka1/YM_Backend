from app.common.enums import EntityType

_SOLE_TRADER_TYPES: frozenset[EntityType] = frozenset(
    {
        EntityType.OSEK_PATUR,
        EntityType.OSEK_MURSHE,
    }
)
