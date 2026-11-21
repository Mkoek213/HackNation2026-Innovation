from __future__ import annotations

from typing import Any, Iterable, Sequence

Loc = Sequence[str | int]


class DomainError(Exception):
    """Base domain error, do not throw directly."""

    status_code: int = 400
    type: str = "domain_error"

    def __init__(
        self,
        msg: str,
        *,
        loc: Loc = (),
        input_: Any = None,
        **ctx: Any,
    ) -> None:
        super().__init__(msg)
        self.msg = msg
        self.loc = tuple(loc)
        self.input = input_
        self.ctx = ctx

    def errors(self) -> list[dict[str, Any]]:
        """List like pydantic validation error."""
        item: dict[str, Any] = {
            "type": self.type,
            "loc": list(self.loc),
            "msg": self.msg,
        }
        if self.input is not None:
            item["input"] = self.input
        if self.ctx:
            item["ctx"] = self.ctx
        return [item]


class DomainErrorGroup(DomainError):
    """Combines errors into one error."""

    def __init__(self, errors: Iterable[DomainError]) -> None:
        self._errors = list(errors)
        if not self._errors:
            raise ValueError("DomainErrorGroup requires at least one error.")
        first = self._errors[0]
        super().__init__(f"{len(self._errors)} validation errors")
        self.status_code = 422
        self.type = first.type

    def errors(self) -> list[dict[str, Any]]:
        return [item for e in self._errors for item in e.errors()]

    def at(self, *prefix: str | int) -> DomainErrorGroup:
        """Adds prefix to error, eg. ('body', 'items', 3)."""
        for e in self._errors:
            e.loc = (*prefix, *e.loc)
        return self


class NotFoundError(DomainError):
    status_code = 404
    type = "not_found"

    def __init__(self, resource: str, key: Any, *, loc: Loc = (), msg: str = None) -> None:
        super().__init__(
            msg=msg or f"{resource} with params {key} was not found.",
            loc=loc,
            input_=key,
            resource=resource,
        )


class ConflictError(DomainError):
    """Conflicts with database state."""

    status_code = 409
    type = "conflict"


class DuplicateError(ConflictError):
    type = "duplicate"

    def __init__(self, resource: str, field: str, value: Any, *, loc: Loc = ()) -> None:
        super().__init__(
            f"{resource} with {field}={value!r} already exists",
            loc=loc or ("body", field),
            input_=value,
            resource=resource,
        )


class ValidationError(DomainError):
    status_code = 422
    type = "domain_validation"


class ForbiddenError(DomainError):
    status_code = 403
    type = "forbidden"


class UnauthorizedError(DomainError):
    status_code = 401
    type = "unauthorized"


class DependencyUnavailable(DomainError):
    status_code = 503
    type = "dependency_unavailable"
