from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status

from app.config import settings
from app.core.openapi_responses import bad_request_response, error_responses, unauthorized_response
from app.middleware.rate_limiting import get_email_key, limiter
from app.users.api.user_auth_cookies import clear_refresh_cookie, set_refresh_cookie
from app.users.user_constants import REFRESH_COOKIE_NAME
from app.users.api.user_deps import CurrentUser, DBSession
from app.users.schemas.user_auth import (
    AuthTokenResponse,
    LoginRequest,
    RefreshResponse,
    UserResponse,
)
from app.users.services.user_auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=AuthTokenResponse,
    responses=error_responses(
        bad_request_response(description="פרטי ההתחברות אינם תקינים"),
        unauthorized_response(description="שם משתמש או סיסמה שגויים"),
    ),
)
@limiter.limit(settings.AUTH_LOGIN_RATE_LIMIT, key_func=get_email_key("auth_login"))
def login(request: Request, payload: LoginRequest, db: DBSession, response: Response):
    auth_service = AuthService(db)

    bundle = auth_service.login(payload.email, payload.password)

    if not bundle:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="אימייל או סיסמה שגויים",
        )

    set_refresh_cookie(response, bundle.refresh_token)

    return AuthTokenResponse(
        access_token=bundle.access_token,
        user=UserResponse(
            id=bundle.user.id,
            full_name=bundle.user.full_name,
            role=bundle.user.role,
            email=bundle.user.email,
        ),
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    responses=error_responses(
        unauthorized_response(description="אסימון הרענון אינו תקין או שפג תוקפו")
    ),
)
def refresh(
    db: DBSession,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
):
    auth_service = AuthService(db)
    access_token = auth_service.refresh_access_token(refresh_token)
    return RefreshResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        full_name=current_user.full_name,
        role=current_user.role,
        email=current_user.email,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: DBSession,
    response: Response,
    current_user: CurrentUser,
):
    auth_service = AuthService(db)
    auth_service.logout_user(user_id=current_user.id, email=current_user.email)
    clear_refresh_cookie(response)
