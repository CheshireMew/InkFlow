import json
from typing import Any

from jinja2 import Environment


class DictObj:
    """Allow dot access for nested dictionaries in templates."""

    def __init__(self, data: dict[str, Any]):
        for key, value in data.items():
            if isinstance(value, dict):
                setattr(self, key, DictObj(value))
            else:
                setattr(self, key, value)

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)


def build_render_context(inputs: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    render_context: dict[str, Any] = {}

    for key, value in inputs.items():
        render_context[key] = DictObj(value) if isinstance(value, dict) else value

    for step_id, output_data in outputs.items():
        render_context[step_id] = DictObj(output_data) if isinstance(output_data, dict) else output_data

    return render_context


def render_prompt_template(prompt_template: str, render_context: dict[str, Any]) -> str:
    env = Environment()
    env.filters["from_json"] = json.loads
    return env.from_string(prompt_template).render(**render_context)
