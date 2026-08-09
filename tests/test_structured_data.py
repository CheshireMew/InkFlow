from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, ConfigDict

from inkflow.structured_data import (
    MAX_JSON_COLLECTION_ITEMS,
    MAX_JSON_DEPTH,
    StructuredResultError,
    parse_json_object,
    parse_model_json,
)


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


def test_model_json_errors_have_stable_categories() -> None:
    with pytest.raises(StructuredResultError) as duplicate:
        parse_model_json('{"value":"a","value":"b"}', Result)
    assert duplicate.value.code == "invalid_json"

    nested = '{"value":' + "[" * MAX_JSON_DEPTH + "0" + "]" * MAX_JSON_DEPTH + "}"
    with pytest.raises(StructuredResultError) as deep:
        parse_json_object(nested, boundary="test JSON")
    assert deep.value.code == "too_deep"

    with pytest.raises(StructuredResultError) as number:
        parse_json_object('{"value":1e999}', boundary="test JSON")
    assert number.value.code == "invalid_json"


def test_json_collection_budget_is_enforced() -> None:
    raw = json.dumps({"items": list(range(MAX_JSON_COLLECTION_ITEMS + 1))})
    with pytest.raises(StructuredResultError) as raised:
        parse_json_object(raw, boundary="test JSON")
    assert raised.value.code == "resource_budget"
