from __future__ import annotations
from collections.abc import Sequence
from typing import Protocol
from enum import Enum, auto
from abc import ABC, abstractmethod

from ..core import NativeContent
from ...message import Message


class LifeState(Enum):
    retain = auto()  # Do nothing
    retired = auto()  # Ready for GC


class FlowState(Enum):
    exclusive = auto()
    yielded = auto()


class ContextAreaImplementation(Protocol):

    _life_state: LifeState
    _flow_state: FlowState

    @property
    def life_state(self) -> LifeState:
        ...

    @property
    def flow_state(self) -> FlowState:
        ...

    def observe(
        self,
        context: Sequence[NativeContent],
    ) -> None:
        '''
        Observe the Context range currently owned by this Area.
        The supplied Sequence is a shallow, read-only snapshot.
        '''
        ...

    def tick(self) -> list[Message]:
        '''
        tick() returns caller-constructed messages that will be appended to Context.
        A non-empty result creates or extends this Area's EffectRange.
        '''
        ...

    def promote(self) -> tuple[Message, ...]:
        '''
        Only Areas with an EffectRange are promoted during normal collection.
        Retired Areas without an EffectRange are discarded without promotion.
        Retirement does not guarantee immediate collection.
        Promoted messages are appended to Context after the tail is detached.

        =============================================================
        SWITCHING life_state & flow_state in .promote is **ILLEGAL**.
        =============================================================
        '''
        ...

    def gc_prologue(self) -> None:
        '''
        .gc_prologue is a notification to Area.
        Also called when a retired Area without an EffectRange is discarded.
        It means this Area will be collected immedieatly.
        .gc_prologue is designed for important resource collection.

        ================================================================
        SWITCHING life_state & flow_state in .gc_prologue is **USELESS**
        ================================================================
        '''
        ...


class Area(ABC):
    _life_state: LifeState
    _flow_state: FlowState

    def __init__(self, *, flow_state: FlowState) -> None:
        self._life_state = LifeState.retain
        self._flow_state = flow_state

    @property
    def life_state(self) -> LifeState:
        return self._life_state

    @property
    def flow_state(self) -> FlowState:
        return self._flow_state

    def observe(self, context: Sequence[NativeContent]) -> None:
        pass

    @abstractmethod
    def tick(self) -> list[Message]:
        """Process one scheduled tick; returning no messages is valid."""
        raise NotImplementedError

    def promote(self) -> tuple[Message, ...]:
        return ()

    def gc_prologue(self) -> None:
        pass