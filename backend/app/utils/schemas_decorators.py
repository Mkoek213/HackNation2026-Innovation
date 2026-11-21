from copy import deepcopy
from typing import Optional, Type, Any, Iterable, ClassVar, TypeVar

from pydantic import BaseModel, create_model, field_validator, model_validator, ConfigDict


class UpdateModel(BaseModel):
    """
    Base model for all update schemas.
    Adds validator to check if not nullable fields are not set to "null".
    Adds model_dump_null() to automatically excludes unset and changes "null" literal to None.
    """

    model_config = ConfigDict(extra="forbid")

    __nullable_fields__: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode='after')
    def validate_not_null(self):
        for field_name in self.model_fields_set:
            if field_name in self.__nullable_fields__:
                continue
            if getattr(self, field_name, None) is None:
                raise ValueError(f"\"{field_name}\" cannot be null.")
        return self

    def model_dump_null(self, **kwargs: Any) -> dict[str, Any]:
        """Removes unset by default."""
        kwargs.setdefault("exclude_unset", True)
        return self.model_dump(**kwargs)


T = TypeVar("T", bound=BaseModel)


def _as_set(v: Iterable[str] | str | None) -> frozenset[str]:
    if v is None:
        return frozenset()
    return frozenset({v} if isinstance(v, str) else v)


def update_model(
        omit: Iterable[str] | str | None = None,
        nullable: Iterable[str] | str | None = None,
        required: Iterable[str] | str | None = None,
):
    """
    Omit pydantic fields from model.
    Make pydantic fields nullable.
    Make all fields optional.
    Adds new method dump_model_null().
    Adds validator for Not Null Constraint, if the field is not specified in nullable.
    !!! Deletes config dict and all methods !!!
    !!! Do not use with other decorators !!!
    """

    omitted, nullables, required = _as_set(omit), _as_set(nullable), _as_set(required)

    def dec(cls: type[T]) -> type[T]:
        unknown = (omitted | nullables | required) - set(cls.model_fields.keys())
        if unknown:
            raise ValueError(f"{cls.__name__} does not have fields: {sorted(unknown)}")

        fields: dict[str, tuple[Any, Any]] = {}
        for name, info in cls.model_fields.items():
            if name in omitted:
                continue
            new = deepcopy(info)
            if name in required:
                fields[name] = (info.annotation, new)
                continue
            new.default = None
            new.default_factory = None
            fields[name] = (Optional[info.annotation], new)

        model = create_model(
            cls.__name__,
            __base__=UpdateModel,
            __module__=cls.__module__,
            __doc__=cls.__doc__,
            **fields,
        )
        model.__nullable_fields__ = nullables
        return model

    return dec


def omit(*fields):
    """
    Omit pydantic fields from model.
    Keeps model_validator / field_validator methods (own and inherited).
    !!! Do not use with other decorators !!!
    """

    def dec(_class: Type[BaseModel]):
        for field in fields:
            _class.model_fields.pop(field, None)

        # By the time a @model_validator/@field_validator-decorated method
        # lands in __pydantic_decorators__, pydantic has already unwrapped it
        # back to a plain function -- create_model()'s __validators__ needs
        # it re-wrapped in the original decorator to be recognized.
        decorators = _class.__pydantic_decorators__
        validators: dict[str, Any] = {
            name: model_validator(mode=d.info.mode)(d.func)
            for name, d in decorators.model_validators.items()
        }
        validators.update({
            name: field_validator(*d.info.fields, mode=d.info.mode)(d.func)
            for name, d in decorators.field_validators.items()
        })

        _clone = create_model(
            _class.__name__,
            __config__=_class.model_config,
            __validators__=validators,
            **{
                k: (v.annotation, v)
                for k, v in _class.model_fields.items()},
        )
        setattr(_clone, "__pydantic_parent_namespace__", {})
        return _clone

    return dec
