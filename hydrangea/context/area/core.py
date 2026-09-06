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


class InvokeTiming(Enum):
    immediate = auto()
    deferrable = auto()


class ContextAreaImplementation(Protocol):

    _life_state: LifeState
    _invoke_timing: InvokeTiming

    _observe_snapshot: Sequence[NativeContent]

    @property
    def life_state(self) -> LifeState:
        ...

    @property
    def invoke_timing(self) -> InvokeTiming:
        """
        immediate  => Expect LLM.invoke() immediately after .tick()
        deferrable => Expect at least one LLM.invoke() after .tick()
        """
        ...

    def observe(
        self,
        context: Sequence[NativeContent],
    ) -> None:
        '''
        CoopContext would use this method to update self._observe_snapshot.
        '''
        ...

    def tick(self) -> list[Message]:
        '''
        CoopContext would use this method to get a list of Message.
        .tick() means Area itself should process some details about self._life_state.
        '''
        ...

    def promote(self) -> tuple[Message, ...]:
        '''
        CoopContext would use this method when GC this area.
        .promote() means promote some message to CoopContext._context.
        Breifly, return what you wanna keep beyond GC.
        '''
        ...

    def gc_prologue(self) -> None:
        '''
        CoopContext would use this method to notify area when GC.
        It means this Area will be collected immedieatly.
        .gc_prologue is designed for important resource collection.
        '''
        ...


class Area(ABC):
    _life_state: LifeState
    _invoke_timing:InvokeTiming
    _observe_snapshot: Sequence[NativeContent]


    def __init__(self, *, invoke_timing:InvokeTiming) -> None:
        self._life_state = LifeState.retain
        self._invoke_timing = invoke_timing
        self._observe_snapshot = tuple()

    @property
    def life_state(self) -> LifeState:
        return self._life_state

    @property
    def invoke_timing(self)-> InvokeTiming:
        return self._invoke_timing

    def _retire(self) ->None:
        self._life_state = LifeState.retired

    def observe(self, context: Sequence[NativeContent]) -> None:
        self._observe_snapshot = tuple(context)

    @abstractmethod
    def tick(self) -> list[Message]:
        raise NotImplementedError

    def promote(self) -> tuple[Message, ...]:
        return ()

    def gc_prologue(self) -> None:
        pass
