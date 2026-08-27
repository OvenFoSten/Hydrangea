from google import genai
from google.genai import types
from typing_extensions import assert_never

from .config import (
    GeminiConfig,
    llm_config_to_gemini_config,
)
from .context import GeminiContext
from ..config import LLMConfig
from ..context import ContextImplementation
from ..gateway import GatewayType
from ..prompt import SystemInstruction
from ..reasoning import ReasoningEffort
from ..tool import ToolDeclaration


def _reasoning_effort_to_gemini_thinking_level(
    effort: ReasoningEffort,
) -> types.ThinkingLevel:

    match effort:
        case ReasoningEffort.minimal:
            return types.ThinkingLevel.MINIMAL

        case ReasoningEffort.low:
            return types.ThinkingLevel.LOW

        case ReasoningEffort.medium:
            return types.ThinkingLevel.MEDIUM

        case ReasoningEffort.high:
            return types.ThinkingLevel.HIGH

        case _:
            assert_never(effort)
            


def _tool_declaration_to_gemini_declaration(
    declaration: ToolDeclaration,
) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        description=declaration.description,
        name=declaration.name,
        parameters_json_schema=(
            declaration.args_schema.model_json_schema()
        ),
        response_json_schema=(
            declaration.reply_schema.model_json_schema()
        ),
    )


class Gemini:
    _instruction: SystemInstruction
    _config: GeminiConfig
    _client: genai.Client

    def __init__(
        self,
        config: GeminiConfig,
        instruction:SystemInstruction
    ) -> None:
        self._instruction = instruction
        self._config = config
        self._client = genai.Client(
            api_key=self._config.api_key
        )

    @classmethod
    def from_llm_config(
        cls,
        config: LLMConfig,
        instruction:SystemInstruction
    ) -> "Gemini":
        return cls(
            config=llm_config_to_gemini_config(config),
            instruction = instruction
        )

    @property
    def gateway_type(self) -> GatewayType:
        return GatewayType.gemini

    def invoke(
        self,
        context: ContextImplementation,
        effort: ReasoningEffort,
        tool_declarations: list[ToolDeclaration],
    ) -> types.Content:
        if not isinstance(context, GeminiContext):
            raise TypeError(
                "Context implementation does not match Gemini: "+
                "expected GeminiContext, got "+
                f"{type(context).__name__}."
            )

        gemini_context = context
        thinking_level = (
            _reasoning_effort_to_gemini_thinking_level(
                effort
            )
        )
        prompt = self._instruction
        sdk_context: list[types.ContentUnionDict] = []
        sdk_context.extend(gemini_context.contents)
        gemini_tool_declarations = [
            _tool_declaration_to_gemini_declaration(
                declaration
            )
            for declaration in tool_declarations
        ]

        response = self._client.models.generate_content(
            model=self._config.model_name,
            contents=sdk_context,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level=thinking_level,
                    include_thoughts=True,
                ),
                system_instruction=prompt,
                tools=(
                    [
                        types.Tool(
                            function_declarations=(
                                gemini_tool_declarations
                            )
                        )
                    ]
                    if gemini_tool_declarations
                    else None
                ),
                temperature=0.7,
            ),
        )

        candidates = response.candidates
        if not candidates:
            raise ValueError(
                "No candidates from Google, "+
                "please check the API availability."
            )

        content = candidates[0].content
        if content is None:
            raise ValueError(
                "No content from Google, "+
                "please check the API availability."
            )

        return content
