# pyright: reportPrivateUsage=false

import json
from collections.abc import Mapping
from typing import cast

import httpx
import pytest
from openai import OpenAI as OpenAIClient
from openai.types.responses import Response
from pydantic import BaseModel

from hydrangea.config import LLMConfig
from hydrangea.context import Context
from hydrangea.gateway import GatewayType
from hydrangea.instruction import SystemInstruction
from hydrangea.llm import LLM
from hydrangea.message import FunctionReply, Message, Role
from hydrangea.openai.llm import OpenAI
from hydrangea.reasoning import ReasoningEffort
from hydrangea.tool import ToolDeclaration


class _ToolArgs(BaseModel):
    query: str


class _ToolReply(BaseModel):
    result: str


def _request_payload(request: httpx.Request) -> dict[str, object]:
    parsed = cast(object, json.loads(request.content))
    assert isinstance(parsed, dict)
    return dict(cast(Mapping[str, object], parsed))


def _mock_llm(transport: httpx.MockTransport) -> LLM:
    llm = LLM(
        gateway_type=GatewayType.openai,
        config=LLMConfig(
            api_key="test-key", model_name="test-model",
            base_url="https://example.test/v1",
        ),
        instruction=SystemInstruction("Follow the instruction."),
    )
    native = llm._native
    assert isinstance(native, OpenAI)
    native._client = OpenAIClient(
        api_key="test-key", base_url="https://example.test/v1",
        http_client=httpx.Client(transport=transport),
    )
    return llm


def test_openai_llm_builds_responses_request_and_replays_restored_reasoning(
    response: Response,
) -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/responses"
        payloads.append(_request_payload(request))
        return httpx.Response(200, json=response.model_dump(mode="json"))

    llm = _mock_llm(httpx.MockTransport(handler))
    context = Context(GatewayType.openai)
    context.emplace_message(Message(role=Role.user, content="Run the tool."))
    declaration = ToolDeclaration(
        name="lookup", description="Look up a value.",
        args_schema=_ToolArgs, reply_schema=_ToolReply,
    )

    content = llm.invoke(
        context=context, effort=ReasoningEffort.high,
        tool_declarations=[declaration],
    )
    assert isinstance(content, Response)
    assert content.output == response.output
    assert len(context) == 1
    payload = payloads[0]
    assert payload["model"] == "test-model"
    assert payload["instructions"] == "Follow the instruction."
    assert payload["input"] == [{"role": "user", "content": "Run the tool."}]
    assert payload["reasoning"] == {"effort": "high", "summary": "auto"}
    assert payload["store"] is False
    assert payload["include"] == ["reasoning.encrypted_content"]
    assert "previous_response_id" not in payload
    assert "temperature" not in payload
    tools = cast(list[dict[str, object]], payload["tools"])
    assert tools == [{
        "type": "function", "name": "lookup", "description": "Look up a value.",
        "parameters": _ToolArgs.model_json_schema(), "strict": False,
    }]

    restored = Response.model_validate_json(content.model_dump_json())
    context.push_back(restored)
    context.emplace_function_replies([
        FunctionReply(call_id="call-1", name="lookup", content=_ToolReply(result="found")),
        FunctionReply(call_id="call-2", name="count", content=_ToolReply(result="two")),
    ])
    before_invoke = context[:]
    _ = llm.invoke(
        context=context, effort=ReasoningEffort.low,
        tool_declarations=[], temperature=0.25,
    )
    explicit_payload = payloads[1]
    assert explicit_payload["temperature"] == 0.25
    assert explicit_payload["reasoning"] == {"effort": "low", "summary": "auto"}
    assert "tools" not in explicit_payload
    assert context[:] == before_invoke
    assert explicit_payload["input"] == [
        {"role": "user", "content": "Run the tool."},
        *[item.model_dump(mode="json", exclude_none=True) for item in response.output],
        {"type": "function_call_output", "call_id": "call-1", "output": '{"result":"found"}'},
        {"type": "function_call_output", "call_id": "call-2", "output": '{"result":"two"}'},
    ]


@pytest.mark.parametrize("effort", list(ReasoningEffort))
def test_openai_llm_maps_all_reasoning_efforts(response: Response, effort: ReasoningEffort) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert _request_payload(request)["reasoning"] == {"effort": effort.value, "summary": "auto"}
        return httpx.Response(200, json=response.model_dump(mode="json"))

    llm = _mock_llm(httpx.MockTransport(handler))
    _ = llm.invoke(Context(GatewayType.openai), effort, [])


def test_openai_llm_rejects_empty_output(response: Response) -> None:
    response.output = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response.model_dump(mode="json"))

    llm = _mock_llm(httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="No output from OpenAI"):
        _ = llm.invoke(Context(GatewayType.openai), ReasoningEffort.low, [])


def test_openai_llm_rejects_mismatched_context() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("A mismatched context must not make an HTTP request.")

    llm = _mock_llm(httpx.MockTransport(handler))
    with pytest.raises(TypeError, match="expected OpenAIContext"):
        _ = llm.invoke(Context(GatewayType.gemini), ReasoningEffort.low, [])
