import datetime as dt
import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

from app.models.contact import CONTACT_EMAIL_MAX_LENGTH, CONTACT_MESSAGE_MAX_LENGTH, CONTACT_NAME_MAX_LENGTH
from app.schemas.user import Email


def _strip(value):
    return value.strip() if isinstance(value, str) else value


def _single_line(value: str) -> str:
    # The name goes into the e-mail subject, so it must not carry line breaks or other control characters.
    if re.search(r"[\x00-\x1f\x7f]", value):
        raise ValueError("Name must be a single line of text.")
    return value


Name = Annotated[str, BeforeValidator(_strip), Field(min_length=2, max_length=CONTACT_NAME_MAX_LENGTH),
                 AfterValidator(_single_line)]
Message = Annotated[str, BeforeValidator(_strip), Field(min_length=10, max_length=CONTACT_MESSAGE_MAX_LENGTH)]


class ContactCreate(BaseModel):
    name: Name = Field(examples=["Anna Nowak"])
    email: Annotated[Email, Field(max_length=CONTACT_EMAIL_MAX_LENGTH)] = Field(examples=["anna.nowak@example.com"])
    message: Message = Field(examples=["Chcielibyśmy porozmawiać o wdrożeniu innowacji w naszej gminie."])
    consent: Literal[True] = Field(description="Consent to processing the data to answer the message.")

    model_config = ConfigDict(extra="forbid")


class ContactReceipt(BaseModel):
    """Confirmation for the sender; it never reveals whether mail delivery succeeded."""
    id: int = Field(ge=1, examples=[1])
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class ContactModel(ContactReceipt):
    name: str
    email: str
    message: str
    user_id: int | None = Field(default=None, examples=[None])
    delivered: bool
