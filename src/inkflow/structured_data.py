from __future__ import annotations

import json
import math
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 40
MAX_JSON_NODES = 50_000
MAX_JSON_COLLECTION_ITEMS = 10_000
MAX_JSON_STRING_CHARS = 500_000
MAX_JSON_KEY_CHARS = 2_000
MAX_JSON_NUMBER_CHARS = 128


class StructuredResultError(ValueError):
    def __init__(self, code: str, message: str, *, raw_response: str) -> None:
        super().__init__(message)
        self.code = code
        self.raw_response = raw_response


def parse_model_json(raw_response: str, model: type[T]) -> T:
    value = parse_json_object(raw_response, boundary="model JSON")
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        raise StructuredResultError(
            "schema_mismatch",
            f"model JSON does not match the result schema: {exc}",
            raw_response=raw_response,
        ) from exc


def parse_json_object(
    raw_response: str,
    *,
    boundary: str,
    max_bytes: int = MAX_JSON_BYTES,
) -> dict[str, Any]:
    encoded = raw_response.encode("utf-8")
    if len(encoded) > max_bytes:
        raise StructuredResultError(
            "too_large", f"{boundary} response is too large", raw_response=raw_response
        )
    _preflight_depth(raw_response, boundary=boundary)
    try:
        value = json.loads(
            raw_response,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_int=_parse_int,
            parse_float=_parse_float,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise StructuredResultError(
            "invalid_json", f"invalid {boundary}: {exc}", raw_response=raw_response
        ) from exc
    if not isinstance(value, dict):
        raise StructuredResultError(
            "root_not_object", f"{boundary} root must be an object", raw_response=raw_response
        )
    try:
        _validate_resource_budget(value)
    except ValueError as exc:
        raise StructuredResultError(
            "resource_budget", f"invalid {boundary}: {exc}", raw_response=raw_response
        ) from exc
    return value


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


def _parse_int(value: str) -> int:
    if len(value.lstrip("-")) > MAX_JSON_NUMBER_CHARS:
        raise ValueError("JSON integer token is too long")
    return int(value)


def _parse_float(value: str) -> float:
    if len(value) > MAX_JSON_NUMBER_CHARS:
        raise ValueError("JSON number token is too long")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number: {value}")
    return parsed


def _preflight_depth(raw: str, *, boundary: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    string_chars = 0
    for char in raw:
        if in_string:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
                string_chars = 0
            else:
                string_chars += 1
                if string_chars > MAX_JSON_STRING_CHARS:
                    raise StructuredResultError(
                        "string_too_long",
                        f"{boundary} contains a string that is too long",
                        raw_response=raw,
                    )
            continue
        if char == '"':
            in_string = True
            string_chars = 0
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise StructuredResultError(
                    "too_deep", f"{boundary} is too deeply nested", raw_response=raw
                )
        elif char in "]}":
            depth -= 1


def _validate_resource_budget(value: Any) -> None:
    nodes = 0
    stack = [value]
    while stack:
        current = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise ValueError("JSON contains too many values")
        if isinstance(current, dict):
            if len(current) > MAX_JSON_COLLECTION_ITEMS:
                raise ValueError("JSON object contains too many members")
            for key, item in current.items():
                if len(key) > MAX_JSON_KEY_CHARS:
                    raise ValueError("JSON object key is too long")
                stack.append(item)
        elif isinstance(current, list):
            if len(current) > MAX_JSON_COLLECTION_ITEMS:
                raise ValueError("JSON array contains too many items")
            stack.extend(current)
        elif isinstance(current, str) and len(current) > MAX_JSON_STRING_CHARS:
            raise ValueError("JSON string is too long")
