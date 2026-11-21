import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.knowledge import Category
from app.modules.tester_tags import TesterRole
from app.schemas.user import Email


class VolunteerInput(BaseModel):
    email: Email
    phone: str = Field(min_length=7, max_length=32, pattern=r"^\+?[0-9 ()\-]+$")
    # Optional: explicit tags carry the matching; automatic topic tagging runs only on a non-empty description.
    description: str = Field(default="", max_length=2000)
    roles: list[TesterRole] = Field(min_length=1, max_length=len(TesterRole), examples=[["szkola"]])
    interests: list[Category] = Field(min_length=1, max_length=len(Category), examples=[["jakosc-zycia"]])
    consent: Literal[True]

    @field_validator("phone", "description", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("roles", "interests")
    @classmethod
    def deduplicate(cls, value):
        return list(dict.fromkeys(value))

    @field_validator("phone")
    @classmethod
    def phone_digits(cls, value):
        if not 7 <= sum(c.isdigit() for c in value) <= 15:
            raise ValueError("Phone must contain 7 to 15 digits")
        return value

    model_config = ConfigDict(extra="forbid")


class VolunteerLabel(BaseModel):
    id: int
    name: str


class VolunteerOption(BaseModel):
    id: str
    label: str


class VolunteerOptions(BaseModel):
    """Fixed lists for the explicit tester tags, with Polish labels."""
    roles: list[VolunteerOption]
    interests: list[VolunteerOption]


class VolunteerModel(BaseModel):
    user_id: int
    email: str
    phone: str
    description: str
    roles: list[str]
    interests: list[str]
    tags: list[VolunteerLabel]
    tagging_status: str
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)
