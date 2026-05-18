"""Auth request/response shapes."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    """Create a brand new tenant + owner user."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=120)
    tenant_name: str = Field(min_length=1, max_length=160)
    tenant_slug: str = Field(
        min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$",
        description="URL-safe slug, e.g. 'kiliagon'",
    )
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    tenant_id: str
    tenant_slug: str
    expires_in_days: int = 30


class MeResponse(BaseModel):
    user_id: str
    email: str
    name: str | None
    role: str
    tenant_id: str
    tenant_slug: str
    tenant_name: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    password: str = Field(min_length=8, max_length=120)


class MessageResponse(BaseModel):
    message: str
