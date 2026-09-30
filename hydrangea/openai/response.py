from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
)


class OpenAIResponse:
    content: Response
    thoughts: list[str] | None
    tool_calls: list[ResponseFunctionToolCall] | None
    output: str

    def __init__(self, content: Response) -> None:
        self.content = content
        self.thoughts = None
        self.tool_calls = None
        self.output = ""
        if not content.output:
            raise ValueError(
                "No output from OpenAI, please check the API availability."
            )

        thoughts: list[str] = []
        tool_calls: list[ResponseFunctionToolCall] = []
        for item in content.output:
            if isinstance(item, ResponseReasoningItem):
                thoughts.extend(summary.text for summary in item.summary)
            elif isinstance(item, ResponseFunctionToolCall):
                tool_calls.append(item)
            elif isinstance(item, ResponseOutputMessage):
                for part in item.content:
                    if isinstance(part, ResponseOutputText):
                        self.output += part.text

        if thoughts:
            self.thoughts = thoughts
        if tool_calls:
            self.tool_calls = tool_calls


__all__ = ["OpenAIResponse"]
