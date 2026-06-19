from datetime import timedelta
from typing import Any

import jwt

from app.config import settings
from app.core.logging_config import get_logger
from app.users.models.user import User
from app.utils.time_utils import utcnow

logger = get_logger(__name__)

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def _encode_token(user: User, *, token_type: str, expires_delta: timedelta) -> str:
    now = utcnow()
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "tv": user.token_version,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def generate_access_token(user: User) -> str:
    return _encode_token(
        user,
        token_type=ACCESS_TOKEN_TYPE,
        expires_delta=timedelta(minutes=settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def generate_refresh_token(user: User) -> str:
    return _encode_token(
        user,
        token_type=REFRESH_TOKEN_TYPE,
        expires_delta=timedelta(days=settings.AUTH_REFRESH_TOKEN_EXPIRE_DAYS),
    )


def _decode_token(token: str, *, expected_type: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        required_fields = {"sub", "email", "role", "tv", "type", "exp", "iat"}
        if not required_fields.issubset(payload):
            logger.debug("Token missing required fields")
            return None
        if payload.get("type") != expected_type:
            logger.debug("Token has wrong type")
            return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("Token has expired")
        return None
    except jwt.InvalidTokenError as exc:
        logger.debug(f"Invalid token: {exc}")
        return None


def decode_access_token(token: str) -> dict[str, Any] | None:
    return _decode_token(token, expected_type=ACCESS_TOKEN_TYPE)


def decode_refresh_token(token: str) -> dict[str, Any] | None:
    return _decode_token(token, expected_type=REFRESH_TOKEN_TYPE)
