from typing import Annotated, Protocol, cast

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.logging_config import set_actor_context
from app.database import get_db
from app.users.models.user import UserRole
from app.users.repositories.user_repository import AuthSubject, UserRepository
from app.users.services.user_token_service import decode_access_token

security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthSubject:
    """Extract and validate current user from JWT token."""
    token = credentials.credentials if credentials else None

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="חסר טוקן אימות",
        )

    payload = decode_access_token(token)

    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="הטוקן אינו תקין או שפג תוקפו",
        )

    try:
        user_id = int(payload["sub"])
        token_version = int(payload["tv"])
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="פורמט הטוקן אינו תקין",
        ) from exc

    user_repo = UserRepository(db)
    user = user_repo.get_auth_subject_by_id(user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="המשתמש לא נמצא או שאינו פעיל",
        )

    if token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="הטוקן אינו תקין או שפג תוקפו",
        )

    set_actor_context(user_id=user.id, role=user.role.value)
    return user


class RoleDependency(Protocol):
    __requires_role__: bool

    def __call__(
        self,
        current_user: Annotated[AuthSubject, Depends(get_current_user)],
    ) -> AuthSubject: ...


def require_role(*allowed_roles: UserRole):
    """Dependency factory for role-based access control."""

    def role_checker(
        current_user: Annotated[AuthSubject, Depends(get_current_user)],
    ) -> AuthSubject:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="אין הרשאות מתאימות",
            )
        return current_user

    role_dependency = cast(RoleDependency, role_checker)
    role_dependency.__requires_role__ = True
    return role_dependency


# Common dependencies
CurrentUser = Annotated[AuthSubject, Depends(get_current_user)]
DBSession = Annotated[Session, Depends(get_db)]
