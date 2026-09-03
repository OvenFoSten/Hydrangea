from collections.abc import Mapping
from typing import cast

from openai import OpenAI as OpenAIClient
from openai import omit
from openai.types.chat import (
    ChatCompletionDeveloperMessageParam,
    ChatCompletionFunctionToolParam,
    ChatCompletionMessage,
    ChatCompletionReasoningEffort,
)
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
) -> ChatCompletionReasoningEffort:
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
) -> ChatCompletionFunctionToolParam:
    parameters = dict(
        cast(
            Mapping[str, object],
            declaration.args_schema.model_json_schema(),
        )
    )
    return {
        "type": "function",
        "function": {
            "name": declaration.name,
            "description": declaration.description,
            "parameters": parameters,
        },
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
        temperature: float | None,
    ) -> ChatCompletionMessage:
        if not isinstance(context, OpenAIContext):
            raise TypeError(
                "Context implementation does not match OpenAI: "
                "expected OpenAIContext, got "
                f"{type(context).__name__}."
            )

        messages = context.messages
        instruction = ChatCompletionDeveloperMessageParam(
            role="developer",
            content=self._instruction,
        )
        messages.insert(0, instruction)

        tools = [
            _tool_declaration_to_openai_tool(declaration)
            for declaration in tool_declarations
        ]
        response = self._client.chat.completions.create(
            model=self._config.model_name,
            messages=messages,
            reasoning_effort=(
                _reasoning_effort_to_openai_reasoning_effort(
                    effort
                )
            ),
            temperature=(
                temperature
                if temperature is not None
                else omit
            ),
            tools=tools if tools else omit,
        )

        if not response.choices:
            raise ValueError(
                "No choices from OpenAI, "
                "please check the API availability."
            )

        return response.choices[0].message


__all__ = ["OpenAI"]
