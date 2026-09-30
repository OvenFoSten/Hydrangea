import json
from collections.abc import Iterable, Mapping
from typing import TypeAlias, TypeVar, cast

from openai.types.responses import (
    EasyInputMessageParam,
    Response,
    ResponseFunctionToolCall,
    ResponseInputItemParam,
)
from openai.types.responses.response_input_item_param import FunctionCallOutput
from pydantic import BaseModel, ValidationError
from typing_extensions import assert_never

from ..message import (
    FunctionReplyTurn,
    Message,
    Role,
    ToolCall,
)


OpenAIContextContent: TypeAlias = Response | ResponseInputItemParam
SCHEMA_INPUT = TypeVar("SCHEMA_INPUT", bound=BaseModel)


def _function_tool_call_to_tool_call(
    tool_call: ResponseFunctionToolCall,
) -> ToolCall:
    try:
        parsed_arguments = cast(object, json.loads(tool_call.arguments))
    except json.JSONDecodeError as error:
        raise ValueError(
            "OpenAI returned invalid JSON tool arguments for "
            f"{tool_call.name!r}."
        ) from error

    if not isinstance(parsed_arguments, dict):
        raise ValueError(
            "OpenAI returned non-object tool arguments for "
            f"{tool_call.name!r}."
        )

    return ToolCall(
        call_id=tool_call.call_id,
        name=tool_call.name,
        arguments=dict(cast(Mapping[str, object], parsed_arguments)),
    )


def message_to_openai_param(message: Message) -> EasyInputMessageParam:
    match message.role:
        case Role.user:
            return {"role": "user", "content": message.content}
        case Role.assistant:
            return {"role": "assistant", "content": message.content}
        case _:
            assert_never(message.role)


def function_reply_turn_to_openai_params(
    turn: FunctionReplyTurn,
) -> tuple[FunctionCallOutput, ...]:
    outputs: list[FunctionCallOutput] = []
    for reply in turn.replies:
        if reply.call_id is None:
            raise ValueError(
                "OpenAI function replies require a tool call ID."
            )

        outputs.append(
            FunctionCallOutput(
                type="function_call_output",
                call_id=reply.call_id,
                output=reply.content.model_dump_json(),
            )
        )

    return tuple(outputs)


def _assistant_input_text(content: ResponseInputItemParam) -> str:
    params = cast(Mapping[str, object], content)
    if params.get("role") != "assistant":
        return ""

    raw_content = params.get("content")
    if isinstance(raw_content, str):
        return raw_content
    if not isinstance(raw_content, list):
        return ""

    texts: list[str] = []
    for part in cast(list[object], raw_content):
        if not isinstance(part, dict):
            continue
        fields = cast(Mapping[str, object], part)
        if fields.get("type") not in ("input_text", "output_text"):
            continue
        text = fields.get("text")
        if isinstance(text, str):
            texts.append(text)
    return "".join(texts)


class OpenAIContext:
    _contents: list[OpenAIContextContent]

    def __init__(
        self,
        contents: Iterable[OpenAIContextContent] | None = None,
    ) -> None:
        self._contents = []
        for content in contents if contents is not None else ():
            self.push_back(content)

    def push_back(self, content: object) -> None:
        if isinstance(content, Response):
            self._contents.append(content)
            return

        if isinstance(content, dict):
            self._contents.append(cast(ResponseInputItemParam, content))
            return

        raise TypeError(
            "OpenAIContext requires a Response or "
            "ResponseInputItemParam, got "
            f"{type(content).__name__}."
        )

    def emplace_message(self, message: Message) -> None:
        self.push_back(message_to_openai_param(message))

    def emplace_function_reply_turn(
        self,
        turn: FunctionReplyTurn,
    ) -> None:
        outputs = function_reply_turn_to_openai_params(turn)
        self._contents.extend(outputs)

    def detach_tail(
        self,
        length: int,
    ) -> tuple[OpenAIContextContent, ...]:
        context_size = len(self._contents)
        if length < 0 or length > context_size:
            raise ValueError(
                "Invalid tail length: "
                f"length={length}, "
                f"context_size={context_size}."
            )

        tail_begin = context_size - length
        detached = tuple(self._contents[tail_begin:])
        del self._contents[tail_begin:]
        return detached

    def __getitem__(
        self,
        selection: slice,
    ) -> tuple[OpenAIContextContent, ...]:
        return tuple(self._contents[selection])

    def pop_back(self) -> OpenAIContextContent:
        return self._contents.pop()

    def last_tool_calls(self) -> list[ToolCall] | None:
        if not self._contents:
            return None

        content = self._contents[-1]
        if not isinstance(content, Response):
            return None

        tool_calls: list[ToolCall] = []
        for item in content.output:
            if isinstance(item, ResponseFunctionToolCall):
                tool_calls.append(_function_tool_call_to_tool_call(item))
            elif item.type == "custom_tool_call":
                raise TypeError("OpenAI custom tool calls are not supported.")

        return tool_calls or None

    def last_schema_output(
        self,
        schema: type[SCHEMA_INPUT],
    ) -> SCHEMA_INPUT | None:
        if not self._contents:
            return None

        content = self._contents[-1]
        response_json = (
            content.output_text
            if isinstance(content, Response)
            else _assistant_input_text(content)
        )
        if not response_json:
            return None
        try:
            return schema.model_validate_json(response_json)
        except ValidationError:
            return None

    @property
    def contents(self) -> list[OpenAIContextContent]:
        return self._contents.copy()

    @property
    def input(self) -> list[ResponseInputItemParam]:
        items: list[ResponseInputItemParam] = []
        for content in self._contents:
            if isinstance(content, Response):
                # Replay every output item, including encrypted reasoning, in order.
                items.extend(
                    cast(
                        ResponseInputItemParam,
                        item.model_dump(mode="json", exclude_none=True),
                    )
                    for item in content.output
                )
            else:
                items.append(content)

        return items

    def __len__(self) -> int:
        return len(self._contents)


__all__ = [
    "OpenAIContext",
    "OpenAIContextContent",
]
