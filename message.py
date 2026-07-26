from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel


class AsterRole(Enum):
    user = "user"
    assistant = "assistant"


@dataclass(frozen=True)
class AsterMessage:
    role: AsterRole
    content: str


@dataclass(frozen=True)
class AsterToolCall:
    call_id: str | None
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class AsterFunctionReply:
    call_id: str | None
    name: str
    content: BaseModel


@dataclass(frozen=True)
class AsterFunctionReplyTurn:
    replies: tuple[AsterFunctionReply, ...]

    def __post_init__(self) -> None:
        if not self.replies:
            raise ValueError("A function reply turn must contain at least one reply.")
