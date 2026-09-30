from collections.abc import Mapping
from typing import cast

from openai import OpenAI as OpenAIClient
from openai import omit
from openai.lib._pydantic import to_strict_json_schema
from openai.types.responses import FunctionToolParam, Response, ResponseTextConfigParam
from openai.types.shared import ReasoningEffort as OpenAIReasoningEffort
from pydantic import BaseModel
from typing_extensions import assert_never

from .config import (
    OpenAIConfig,
    llm_config_to_openai_config,
)
from .context import OpenAIContext
from ..config import LLMConfig
from ..gateway import GatewayType
from ..instruction import SystemInstruction
from ..reasoning import ReasoningEffort
from ..tool import ToolDeclaration


def _reasoning_effort_to_openai_reasoning_effort(
    effort: ReasoningEffort,
) -> OpenAIReasoningEffort:
    match effort:
        case ReasoningEffort.minimal:
            return "minimal"
        case ReasoningEffort.low:
            return "low"
        case ReasoningEffort.medium:
            return "medium"
        case ReasoningEffort.high:
            return "high"
        case _:
            assert_never(effort)


def _tool_declaration_to_openai_tool(
    declaration: ToolDeclaration,
) -> FunctionToolParam:
    parameters = dict(
        cast(
            Mapping[str, object],
            declaration.args_schema.model_json_schema(),
        )
    )
    return {
        "type": "function",
        "name": declaration.name,
        "description": declaration.description,
        "parameters": parameters,
        "strict": False,
    }


def _schema_to_openai_text_config(
    schema: type[BaseModel],
) -> ResponseTextConfigParam:
    # Use the SDK's conversion for nested objects and required nullable fields.
    json_schema = dict(
        cast(Mapping[str, object], to_strict_json_schema(schema))
    )
    return {
        "format": {
            "type": "json_schema",
            "name": schema.__name__,
            "schema": json_schema,
            "strict": True,
        }
    }


class OpenAI:
    _instruction: SystemInstruction
    _config: OpenAIConfig
    _client: OpenAIClient

    def __init__(
        self,
        config: OpenAIConfig,
        instruction: SystemInstruction,
    ) -> None:
        self._instruction = instruction
        self._config = config
        self._client = OpenAIClient(
            api_key=self._config.api_key,
            base_url=self._config.base_url,
        )

    @classmethod
    def from_llm_config(
        cls,
        config: LLMConfig,
        instruction: SystemInstruction,
    ) -> "OpenAI":
        return cls(
            config=llm_config_to_openai_config(config),
            instruction=instruction,
        )

    @property
    def gateway_type(self) -> GatewayType:
        return GatewayType.openai

    def invoke(
        self,
        context: object,
        effort: ReasoningEffort,
        tool_declarations: list[ToolDeclaration],
        schema: type[BaseModel] | None,
        temperature: float | None,
    ) -> Response:
        if not isinstance(context, OpenAIContext):
            raise TypeError(
                "Context implementation does not match OpenAI: "
                "expected OpenAIContext, got "
                f"{type(context).__name__}."
            )

        tools = [
            _tool_declaration_to_openai_tool(declaration)
            for declaration in tool_declarations
        ]
        response = self._client.responses.create(
            model=self._config.model_name,
            instructions=self._instruction,
            input=context.input,
            store=False,
            include=["reasoning.encrypted_content"],
            reasoning={
                "effort": _reasoning_effort_to_openai_reasoning_effort(effort),
                "summary": "auto",
            },
            text=(
                _schema_to_openai_text_config(schema)
                if schema is not None
                else omit
            ),
            temperature=(
                temperature
                if temperature is not None
                else omit
            ),
            tools=tools if tools else omit,
        )

        if not response.output:
            raise ValueError(
                "No output from OpenAI, "
                "please check the API availability."
            )

        return response


__all__ = ["OpenAI"]
