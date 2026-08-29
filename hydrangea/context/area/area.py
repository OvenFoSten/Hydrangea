from __future__ import annotations
from typing import Protocol
from enum import Enum, auto
from dataclasses import dataclass

from ..message import Message

class State(Enum):
    retain = auto() # Do nothing
    prompte = auto() # Area.promote()
    reclaim = auto() # GC(Area)

class ContextAreaImplementation(Protocol):
    _state:State

    @property
    def state(self)->State:
        ...
    
    # .render will return a human-implemented message list.
    def render(self)->tuple[Mark,list[Message]]:
        ...
    
@dataclass(frozen=True,slots=True,eq=False)
class Mark:
    _area:ContextAreaImplementation

    @property
    def state(self)->State:
        return self._area.state