"""Pydantic validation helpers with friendly executive error reporting."""

from __future__ import annotations

from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class SchemaValidationError(Exception):
    """Raised when input data fails schema validation; carries a readable report."""

    def __init__(self, model: Type[BaseModel], errors: list[dict]) -> None:
        self.model = model
        self.errors = errors
        super().__init__(self._format(model, errors))

    @staticmethod
    def _format(model: Type[BaseModel], errors: list[dict]) -> str:
        lines = [f"Validation failed for {model.__name__}:"]
        for err in errors:
            loc = ".".join(str(p) for p in err.get("loc", ()))
            msg = err.get("msg", "invalid value")
            lines.append(f"  - {loc or '<root>'}: {msg}")
        return "\n".join(lines)


def validate(model: Type[T], data: dict) -> T:
    """Validate `data` against `model`, raising SchemaValidationError on failure."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise SchemaValidationError(model, exc.errors()) from exc
