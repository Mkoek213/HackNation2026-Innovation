from typing import Annotated

from pydantic import BeforeValidator, BaseModel, ConfigDict, Field

from app.utils.schemas_decorators import update_model


def _strip(value):
    return value.strip() if isinstance(value, str) else value


#: Display name, stripped before the field's length check so " Edukacja" cannot duplicate
#: "Edukacja" and a blank name is rejected. Length limits stay on each Field: inside the
#: alias they would also be applied to null in the @update_model() copies.
Name = Annotated[str, BeforeValidator(_strip)]


class SubtagModel(BaseModel):
    id: int = Field(ge=1, examples=[1])
    tag_id: int = Field(ge=1, examples=[1])
    name: str = Field(examples=["Jakość powietrza w szkołach"])
    description: str | None = Field(default=None, examples=["Izolacja społeczna osób starszych."])

    model_config = ConfigDict(from_attributes=True)


class SubtagCreate(BaseModel):
    name: Name = Field(min_length=1, max_length=128, examples=["Jakość powietrza w szkołach"])
    description: str | None = Field(default=None, max_length=4000, examples=["Izolacja społeczna osób starszych."])

    model_config = ConfigDict(extra="forbid")


@update_model(nullable="description")
class SubtagUpdate(SubtagCreate):
    """All fields optional. Description can be cleared with null."""
    pass


class TagModel(BaseModel):
    id: int = Field(ge=1, examples=[1])
    name: str = Field(examples=["Edukacja"])
    description: str | None = Field(default=None, examples=["Problemy i potrzeby osób starszych."])

    model_config = ConfigDict(from_attributes=True)


class TagWithSubtags(TagModel):
    subtags: list[SubtagModel] = Field(default_factory=list)


class TagCreate(BaseModel):
    name: Name = Field(min_length=1, max_length=128, examples=["Edukacja"])
    description: str | None = Field(default=None, max_length=4000, examples=["Problemy i potrzeby osób starszych."])

    model_config = ConfigDict(extra="forbid")


@update_model(nullable="description")
class TagUpdate(TagCreate):
    """All fields optional. Description can be cleared with null."""
    pass
