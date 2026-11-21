from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole
from app.utils.schemas_decorators import update_model

#: Validated e-mail address, lowercased so uniqueness is case-insensitive.
Email = Annotated[EmailStr, AfterValidator(str.lower)]


class UserModel(BaseModel):
    id: int = Field(ge=1, examples=[1])
    username: str = Field(examples=["admin"])
    role: UserRole = Field(examples=[UserRole.user])
    email: str | None = Field(default=None, examples=["jan.kowalski@example.com"])

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, examples=["jan.kowalski"])
    password: str = Field(min_length=8, examples=["correct horse battery staple"])
    role: UserRole = Field(default=UserRole.user, examples=[UserRole.user])
    email: Email | None = Field(default=None, examples=["jan.kowalski@example.com"])


@update_model(nullable="email")
class UserUpdate(UserCreate):
    """All fields optional. Password, when given, is re-hashed. Email can be cleared with null."""
    pass


class UserRegister(BaseModel):
    """Self-registration. Demo only: the caller may pick the `admin` role; any other extra field is rejected."""
    username: str = Field(min_length=3, max_length=64, examples=["jan.kowalski"])
    email: Email = Field(examples=["jan.kowalski@example.com"])
    password: str = Field(min_length=8, examples=["correct horse battery staple"])
    role: UserRole = Field(default=UserRole.user, examples=[UserRole.user])

    model_config = ConfigDict(extra="forbid")
