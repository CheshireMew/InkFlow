from __future__ import annotations

import json
import math
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 40


class StructuredResultError(ValueError):
    def __init__(self, message: str, *, raw_response: str) -> None:
        super().__init__(message)
        self.raw_response = raw_response


def parse_model_json(raw_response: str, model: type[T]) -> T:
    encoded = raw_response.encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise StructuredResultError("model JSON response is too large", raw_response=raw_response)
    try:
        value = json.loads(
            raw_response,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise StructuredResultError(
            f"invalid model JSON: {exc}", raw_response=raw_response
        ) from exc
    if not isinstance(value, dict):
        raise StructuredResultError("model JSON root must be an object", raw_response=raw_response)
    if _depth(value) > MAX_JSON_DEPTH:
        raise StructuredResultError("model JSON is too deeply nested", raw_response=raw_response)
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        raise StructuredResultError(
            f"model JSON does not match the result schema: {exc}", raw_response=raw_response
        ) from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    if value in {"NaN", "Infinity", "-Infinity"} or not math.isfinite(float(value)):
        raise ValueError(f"non-finite JSON number: {value}")


def _depth(value: Any) -> int:
    if isinstance(value, dict):
        return 1 + max((_depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(item) for item in value), default=0)
    return 0
