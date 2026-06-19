from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.users.models.user_password_reset_token import PasswordResetToken
from app.utils.time_utils import utcnow


class PasswordResetTokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at,
        requested_ip: str | None,
        user_agent: str | None,
    ) -> PasswordResetToken:
        token = PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            requested_ip=requested_ip,
            user_agent=user_agent,
        )
        self.db.add(token)
        self.db.flush()
        return token

    def invalidate_unused_tokens_for_user(self, user_id: int) -> None:
        self.db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=utcnow())
        )
        self.db.flush()

    def get_valid_by_token_hash(self, token_hash: str) -> PasswordResetToken | None:
        now = utcnow()
        return self.db.scalars(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
        ).first()

    def mark_used(self, token_id: int) -> bool:
        result = self.db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.id == token_id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=utcnow())
        )
        self.db.flush()
        return result.rowcount == 1
