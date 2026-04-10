from core.llm_generation import parse_json_variants, resolve_model_override
from core.templating import build_render_context, render_prompt_template


def test_render_prompt_template_supports_nested_values_and_json_filter():
    render_context = build_render_context(
        {"input": {"text": "hello", "styles": '["a", "b"]'}},
        {},
    )

    rendered = render_prompt_template(
        "{{ input.text }}{% set styles = input.styles | from_json %}-{{ styles|length }}",
        render_context,
    )

    assert rendered == "hello-2"


def test_resolve_model_override_reads_user_selection():
    render_context = {
        "form": {"llm_model": "DeepSeek R1 (Reasoning)"},
    }

    assert resolve_model_override(render_context) == "deepseek-reasoner"


def test_parse_json_variants_returns_fallback_on_invalid_json():
    content = '```json\n[{"label":"A","content":"x"}]\n```'
    assert parse_json_variants(content) == [{"label": "A", "content": "x"}]

    invalid = "not-json"
    assert parse_json_variants(invalid) == ["not-json"]
