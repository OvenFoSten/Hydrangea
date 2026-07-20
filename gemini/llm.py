from collections.abc import Sequence
from enum import Enum

from google import genai
from google.genai import types


from .config import GeminiConfig
from .context import GeminiContext
from ..tool import AsterTool
from ..prompt import AsterPrompt
from .response import GeminiResponse


_TEMP_PROMPT:str = """
You are an agent that can think and take actions to achieve a target.
"""

class ReasoningEffort(Enum):
    minimal = types.ThinkingLevel.MINIMAL
    low = types.ThinkingLevel.LOW
    medium = types.ThinkingLevel.MEDIUM
    high = types.ThinkingLevel.HIGH

def _gemini_aster_tool_to_declaration(tool:AsterTool)->types.FunctionDeclaration:
    return types.FunctionDeclaration(
            name=tool.name,
            description=tool.description,
            parameters_json_schema=(
                tool.args_schema.model_json_schema()
            ),
            response_json_schema=(
                tool.return_schema.model_json_schema()
            ),
        )

class Gemini:
    _prompt:AsterPrompt
    _config:GeminiConfig
    _client:genai.Client
    _tool_declarations: list[types.FunctionDeclaration]
    
    def __init__(
        self,
        config: GeminiConfig,
        tools: list[AsterTool] | None = None,
    ) -> None:
        self._prompt = AsterPrompt(_TEMP_PROMPT)
        self._config = config
        self._client = genai.Client(
            api_key=self._config.api_key
        )

        self._tool_declarations = [
            _gemini_aster_tool_to_declaration(tool)
            for tool in tools or []
        ]
        
    def invoke(
        self,
        target: str,
        context: GeminiContext,
        effort: ReasoningEffort,
    ) -> GeminiResponse:
        prompt = self._prompt.render({
            "target":target
        })
        sdk_context: list[types.ContentUnionDict] = []
        sdk_context.extend(context.contents)

        response = self._client.models.generate_content(
            model=self._config.model_name,
            contents=sdk_context,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                thinking_level=effort.value,
                include_thoughts=True,
                ),
                system_instruction=prompt,

                tools=(
                [
                    types.Tool(function_declarations=(
                            self._tool_declarations
                        )
                    )
                ]
                if self._tool_declarations
                else None
                ),

                temperature=0.7
            ),
        )
        
        if not response.candidates:
            raise ValueError("No candidates from Google, please check the API availability.")
        
        if not response.candidates[0].content:
            raise ValueError("No content from Google, please check the API availability.")
        
                
        return GeminiResponse(response.candidates[0].content)
