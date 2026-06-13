"""rename reminderactiontype enum values to snake_case

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-13

ReminderActionType was the only UPPER_CASE enum among 52 (docs/api-todo.md
#68). Renames CREATE_TASK/SEND_NOTIFICATION/CREATE_TASK_AND_NOTIFY values to
create_task/send_notification/create_task_and_notify to match the
snake_case convention used by every other enum (e.g. ReminderStatus).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RENAMES = [
    ("CREATE_TASK", "create_task"),
    ("SEND_NOTIFICATION", "send_notification"),
    ("CREATE_TASK_AND_NOTIFY", "create_task_and_notify"),
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for old, new in _RENAMES:
        op.execute(f"ALTER TYPE reminderactiontype RENAME VALUE '{old}' TO '{new}'")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for old, new in _RENAMES:
        op.execute(f"ALTER TYPE reminderactiontype RENAME VALUE '{new}' TO '{old}'")
