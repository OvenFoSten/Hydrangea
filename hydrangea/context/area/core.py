from __future__ import annotations
from typing import Protocol
from enum import Enum, auto

from ...message import Message

class LifeState(Enum):
    retain = auto() # Do nothing
    retired = auto() # Ready for GC
    reclaimed = auto() # After GC

class FlowState(Enum):
    exclusive = auto()
    yielded = auto()

class ContextAreaImplementation(Protocol):
    
    _life_state:LifeState
    _flow_state:FlowState

    @property
    def life_state(self)->LifeState:
        ...

    @property
    def flow_state(self)->FlowState:
        ...
    
    def render(self)->list[Message]:
        '''
        .render() will return a list human-implemented message that will be appended to Context.
        Once .render() is called, CoopContext will consider this Area is causing effect.
        '''
        ...

    def promote(self)->tuple[Message,...]:
        '''
        .promote() will be executed when .life_state is "retired".
        Once .life_state is "retired", Area will be marked by Collector.
        set .life_state to "retired" doesn't mean it will be collected immedieatly.
        .promote()'s content will be added into CoopContext once the GC is done.

        =============================================================
        SWITCHING life_state & flow_state in .promote is **ILLEGAL**.
        =============================================================
        '''
        ...

    def gc_prologue(self)->None:
        '''
        .gc_prologue is a notification to Area.
        It means this Area will be collected immedieatly.
        .gc_prologue is designed for important resource collection.

        ================================================================
        SWITCHING life_state & flow_state in .gc_prologue is **USELESS**
        ================================================================
        '''
        ...