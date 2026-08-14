from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel


class Role(Enum):
    user = "user"
    assistant = "assistant"


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class ToolCall:
    call_id: str | None
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class FunctionReply:
    call_id: str | None
    name: str
    content: BaseModel


@dataclass(frozen=True)
class FunctionReplyTurn:
    replies: tuple[FunctionReply, ...]

    def __post_init__(self) -> None:
        if not self.replies:
            raise ValueError("A function reply turn must contain at least one reply.")
