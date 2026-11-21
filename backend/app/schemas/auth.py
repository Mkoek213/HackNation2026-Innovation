from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(examples=["admin"])
    password: str = Field(examples=["correct horse battery staple"])


class LoginResponse(BaseModel):
    detail: str = Field(examples=["Logged in."])
    # Only populated when auth_token_location is "bearer" or "both".
    access_token: Optional[str] = Field(default=None, examples=[None])
    token_type: Optional[str] = Field(default=None, examples=[None])


class LogoutResponse(BaseModel):
    detail: str = Field(examples=["Logged out."])
