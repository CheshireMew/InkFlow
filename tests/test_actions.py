import pytest
from fastapi import HTTPException

from core.exceptions import InkFlowError, LLMError
from routers.actions import ExecuteActionRequest, run_action
from steps.base import BaseStep, StepResult


@pytest.mark.asyncio
async def test_run_action_maps_missing_step_to_404():
    with pytest.raises(HTTPException) as exc_info:
        await run_action(ExecuteActionRequest(tool="missing_step"))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "StepNotFoundError"


@pytest.mark.asyncio
async def test_run_action_maps_domain_error_to_400(monkeypatch):
    class ExplodingStep(BaseStep):
        step_type = "exploding"

        async def execute(self, context):
            raise InkFlowError("bad request", code="BAD_REQUEST")

    monkeypatch.setattr("routers.actions.get_step_class", lambda _tool: ExplodingStep)

    with pytest.raises(HTTPException) as exc_info:
        await run_action(ExecuteActionRequest(tool="exploding"))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_run_action_maps_llm_error_to_502(monkeypatch):
    class ExplodingStep(BaseStep):
        step_type = "exploding_llm"

        async def execute(self, context):
            raise LLMError("upstream failed", code="LLM_BAD_GATEWAY")

    monkeypatch.setattr("routers.actions.get_step_class", lambda _tool: ExplodingStep)

    with pytest.raises(HTTPException) as exc_info:
        await run_action(ExecuteActionRequest(tool="exploding_llm"))

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["error"] == "LLM_BAD_GATEWAY"


def test_step_context_defaults_are_isolated():
    from steps.base import StepContext

    first = StepContext(pipeline_id="a", user_id="u")
    second = StepContext(pipeline_id="b", user_id="u")

    first.inputs["changed"] = True

    assert "changed" not in second.inputs
