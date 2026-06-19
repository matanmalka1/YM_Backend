from fastapi import APIRouter, Request

from app.core.openapi_responses import bad_request_response, error_responses
from app.middleware.rate_limiting import get_email_key, limiter
from app.users.api.user_deps import DBSession
from app.users.schemas.user_auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)
from app.users.services.user_password_reset_service import PasswordResetService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit("3/hour", key_func=get_email_key("auth_forgot_password"))
def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: DBSession,
) -> ForgotPasswordResponse:
    requested_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    message = PasswordResetService(db).request_password_reset(
        payload.email,
        requested_ip=requested_ip,
        user_agent=user_agent,
    )
    return ForgotPasswordResponse(message=message)


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    responses=error_responses(
        bad_request_response(description="אסימון האיפוס אינו תקין או שהסיסמה החדשה חלשה")
    ),
)
@limiter.limit("10/minute")
def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: DBSession,
) -> ResetPasswordResponse:
    message = PasswordResetService(db).reset_password(payload.token, payload.new_password)
    return ResetPasswordResponse(message=message)
