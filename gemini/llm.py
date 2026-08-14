from google import genai
from google.genai import types

from .config import (
    GeminiConfig,
    _llm_config_to_gemini_config,
)
from .context import GeminiContext
from ..config import LLMConfig
from ..context import ContextImplementation
from ..gateway import GatewayType
from ..prompt import Prompt
from ..reasoning import ReasoningEffort
from ..tool import ToolDeclaration


_TEMP_PROMPT: str = """
You are an agent that can think and take actions to achieve a target.
"""


def _aster_reasoning_effort_to_gemini_thinking_level(
    effort: ReasoningEffort,
) -> types.ThinkingLevel:
    candidate: object = effort

    match candidate:
        case ReasoningEffort.minimal:
            return types.ThinkingLevel.MINIMAL

        case ReasoningEffort.low:
            return types.ThinkingLevel.LOW

        case ReasoningEffort.medium:
            return types.ThinkingLevel.MEDIUM

        case ReasoningEffort.high:
            return types.ThinkingLevel.HIGH

        case _:
            raise TypeError(
                "Unsupported reasoning effort: "
                f"{candidate!r}"
            )


def _aster_tool_declaration_to_gemini_declaration(
    declaration: ToolDeclaration,
) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name=declaration.name,
        description=declaration.description,
        parameters_json_schema=(
            declaration.args_schema.model_json_schema()
        ),
        response_json_schema=(
            declaration.reply_schema.model_json_schema()
        ),
    )


class Gemini:
    _prompt: Prompt
    _config: GeminiConfig
    _client: genai.Client

    def __init__(
        self,
        config: GeminiConfig,
    ) -> None:
        self._prompt = Prompt(_TEMP_PROMPT)
        self._config = config
        self._client = genai.Client(
            api_key=self._config.api_key
        )

    @classmethod
    def from_aster_config(
        cls,
        config: LLMConfig,
    ) -> "Gemini":
        return cls(
            config=_llm_config_to_gemini_config(config),
        )

    @property
    def gateway_type(self) -> GatewayType:
        return GatewayType.gemini

    def invoke(
        self,
        target: str,
        context: ContextImplementation,
        effort: ReasoningEffort,
        tool_declarations: list[ToolDeclaration],
    ) -> types.Content:
        if not isinstance(context, GeminiContext):
            raise TypeError(
                "Context implementation does not match Gemini: "
                "expected GeminiContext, got "
                f"{type(context).__name__}."
            )

        gemini_context = context
        thinking_level = (
            _aster_reasoning_effort_to_gemini_thinking_level(
                effort
            )
        )
        prompt = self._prompt.render({
            "target": target
        })
        sdk_context: list[types.ContentUnionDict] = []
        sdk_context.extend(gemini_context.contents)
        gemini_tool_declarations = [
            _aster_tool_declaration_to_gemini_declaration(
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
                "No candidates from Google, "
                "please check the API availability."
            )

        content = candidates[0].content
        if content is None:
            raise ValueError(
                "No content from Google, "
                "please check the API availability."
            )

        return content
