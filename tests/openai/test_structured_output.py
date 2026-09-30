# pyright: reportPrivateUsage=false

import json
from collections.abc import Callable
from typing import cast

import httpx
import pytest
from openai import OpenAI as OpenAIClient
from openai.types.responses import (
    Response,
    ResponseInputItemParam,
    ResponseOutputMessage,
    ResponseOutputRefusal,
    ResponseOutputText,
)
from pydantic import BaseModel

from hydrangea.config import LLMConfig
from hydrangea.context import Context
from hydrangea.gateway import GatewayType
from hydrangea.instruction import SystemInstruction
from hydrangea.llm import LLM
from hydrangea.message import Message, Role
from hydrangea.openai.context import OpenAIContext
from hydrangea.openai.llm import OpenAI
from hydrangea.reasoning import ReasoningEffort


class _Ingredient(BaseModel):
    name: str
    amount: int


class _Recipe(BaseModel):
    name: str
    ingredients: list[_Ingredient]
    note: str | None = None


_RECIPE_JSON = '{"name":"cake","ingredients":[{"name":"flour","amount":2}],"note":null}'


def _response_text(response: Response, text: str) -> None:
    message = response.output[-1]
    assert isinstance(message, ResponseOutputMessage)
    message.content = [
        ResponseOutputText(type="output_text", text=text, annotations=[])
    ]


def _mock_llm(
    handler: Callable[[httpx.Request], httpx.Response],
) -> LLM:
    llm = LLM(
        GatewayType.openai,
        LLMConfig(
            api_key="test-key", model_name="test-model",
            base_url="https://example.test/v1",
        ),
        SystemInstruction("Return a recipe."),
    )
    native = llm._native
    assert isinstance(native, OpenAI)
    native._client = OpenAIClient(
        api_key="test-key", base_url="https://example.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return llm


def test_structured_request_supports_nested_and_nullable_fields_and_replay(
    response: Response,
) -> None:
    _response_text(response, _RECIPE_JSON)
    response.output = [response.output[0], response.output[-1]]
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        payloads.append(cast(dict[str, object], json.loads(request.content)))
        return httpx.Response(200, json=response.model_dump(mode="json"))

    llm = _mock_llm(handler)
    context = Context(GatewayType.openai)
    context.emplace_message(Message(Role.user, "Give me a recipe."))
    content = llm.invoke(context, ReasoningEffort.low, [], schema=_Recipe)
    assert isinstance(content, Response)
    context.push_back(content)
    assert context.last_schema_output(_Recipe) == _Recipe.model_validate_json(_RECIPE_JSON)

    text_config = cast(dict[str, object], payloads[0]["text"])
    text_format = cast(dict[str, object], text_config["format"])
    assert text_format["type"] == "json_schema"
    assert text_format["name"] == "_Recipe"
    assert text_format["strict"] is True
    json_schema = cast(dict[str, object], text_format["schema"])
    assert json_schema["additionalProperties"] is False
    assert set(cast(list[str], json_schema["required"])) == {"name", "ingredients", "note"}
    definitions = cast(dict[str, dict[str, object]], json_schema["$defs"])
    assert definitions["_Ingredient"]["additionalProperties"] is False
    properties = cast(dict[str, dict[str, object]], json_schema["properties"])
    assert {"type": "null"} in cast(list[dict[str, object]], properties["note"]["anyOf"])

    # The next normal request must omit the schema while retaining native reasoning.
    _ = llm.invoke(context, ReasoningEffort.low, [])
    assert "text" not in payloads[1]
    replay = cast(list[dict[str, object]], payloads[1]["input"])
    assert replay[1]["type"] == "reasoning"
    assert replay[1]["encrypted_content"] == "encrypted-reasoning"
    assert replay[-1]["content"] == response.output[-1].model_dump(mode="json", exclude_none=True)["content"]
    assert "parsed" not in cast(dict[str, object], cast(list[object], replay[-1]["content"])[0])


def test_explicit_none_schema_keeps_normal_request(response: Response) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = cast(dict[str, object], json.loads(request.content))
        assert "text" not in payload
        assert payload["store"] is False
        return httpx.Response(200, json=response.model_dump(mode="json"))

    _ = _mock_llm(handler).invoke(Context(GatewayType.openai), ReasoningEffort.low, [], schema=None)


@pytest.mark.parametrize("text", [_RECIPE_JSON, '{"name":', '{"other":"cake"}', "hello"])
def test_last_schema_output_validates_only_the_latest_response(
    response: Response, text: str,
) -> None:
    _response_text(response, text)
    restored = Response.model_validate_json(response.model_dump_json())
    native = OpenAIContext([restored])
    context = Context(GatewayType.openai, native=native)
    expected = _Recipe.model_validate_json(_RECIPE_JSON) if text == _RECIPE_JSON else None
    assert context.last_schema_output(_Recipe) == expected
    context.emplace_message(Message(Role.user, _RECIPE_JSON))
    assert context.last_schema_output(_Recipe) is None
    context.pop_back()
    assert context.last_schema_output(_Recipe) == expected
    _ = context.detach_tail(1)
    assert context.last_schema_output(_Recipe) is None


@pytest.mark.parametrize("kind", ["empty", "reasoning", "tool", "refusal"])
def test_last_schema_output_handles_turns_without_text(response: Response, kind: str) -> None:
    if kind == "empty":
        response.output = []
    elif kind == "reasoning":
        response.output = response.output[:1]
    elif kind == "tool":
        response.output = response.output[1:3]
    else:
        message = response.output[-1]
        assert isinstance(message, ResponseOutputMessage)
        message.content = [ResponseOutputRefusal(type="refusal", refusal="No.")]
        response.output = [message]
    assert OpenAIContext([response]).last_schema_output(_Recipe) is None


def test_last_schema_output_accepts_manual_assistant_messages() -> None:
    native = OpenAIContext()
    assert native.last_schema_output(_Recipe) is None
    native.emplace_message(Message(Role.assistant, _RECIPE_JSON))
    assert native.last_schema_output(_Recipe) == _Recipe.model_validate_json(_RECIPE_JSON)
    native.push_back({"type": "function_call_output", "call_id": "call-1", "output": _RECIPE_JSON})
    assert native.last_schema_output(_Recipe) is None


def test_last_schema_output_accepts_restored_multipart_assistant_message(
    response: Response,
) -> None:
    message = response.output[-1]
    assert isinstance(message, ResponseOutputMessage)
    message.content = [
        ResponseOutputText(type="output_text", text=_RECIPE_JSON[:20], annotations=[]),
        ResponseOutputText(type="output_text", text=_RECIPE_JSON[20:], annotations=[]),
    ]
    content = cast(ResponseInputItemParam, message.model_dump(mode="json", exclude_none=True))
    before = json.dumps(content, sort_keys=True)
    assert OpenAIContext([content]).last_schema_output(_Recipe) == _Recipe.model_validate_json(_RECIPE_JSON)
    assert json.dumps(content, sort_keys=True) == before
