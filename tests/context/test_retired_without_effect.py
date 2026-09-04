# pyright: reportPrivateUsage=false

from typing import final

import pytest
from typing_extensions import override

from hydrangea.context import Context
from hydrangea.context.area.core import Area, FlowState, LifeState
from hydrangea.context.coop_context import CoopContext
from hydrangea.gateway import GatewayType
from hydrangea.message import Message, Role


@final
class _RecordingArea(Area):
    _name: str
    _events: list[str]
    _emits: bool
    _retire_on_tick: bool
    ticks: int

    def __init__(
        self,
        name: str,
        events: list[str],
        *,
        flow_state: FlowState = FlowState.yielded,
        emits: bool = False,
        retire_on_tick: bool = False,
    ) -> None:
        super().__init__(flow_state=flow_state)
        self._name = name
        self._events = events
        self._emits = emits
        self._retire_on_tick = retire_on_tick
        self.ticks = 0

    @override
    def tick(self) -> list[Message]:
        self.ticks += 1
        self._events.append(f"tick:{self._name}")
        if self._retire_on_tick:
            self._life_state = LifeState.retired
        if self._emits:
            return [Message(role=Role.user, content=self._name)]
        return []

    @override
    def promote(self) -> tuple[Message, ...]:
        self._events.append(f"promote:{self._name}")
        return (
            Message(role=Role.user, content=f"promoted:{self._name}"),
        )

    @override
    def gc_prologue(self) -> None:
        self._events.append(f"gc:{self._name}")


def _new_context() -> tuple[Context, CoopContext]:
    context = Context(GatewayType.gemini)
    context.emplace_message(Message(role=Role.user, content="prefix"))
    return context, CoopContext(context)


@pytest.mark.parametrize("flow_state", [FlowState.exclusive, FlowState.yielded])
def test_empty_retirement_is_discarded_without_promotion(
    flow_state: FlowState,
) -> None:
    context, coop = _new_context()
    original = context[:]
    events: list[str] = []
    area = _RecordingArea(
        "empty", events, flow_state=flow_state, retire_on_tick=True
    )
    coop.register(area)

    assert coop.unfold() is context
    assert area.life_state is LifeState.retired
    assert coop._areas == [area]
    assert coop._area_mapping == {}

    assert coop.unfold() is context
    assert coop._areas == []
    assert coop._area_mapping == {}
    assert coop._area_cursor_store is None
    assert coop.garbage == []
    assert context[:] == original

    assert coop.unfold() is context
    assert area.ticks == 1
    assert events == ["tick:empty", "gc:empty"]


def test_already_retired_area_is_not_ticked_or_promoted() -> None:
    context, coop = _new_context()
    original = context[:]
    events: list[str] = []
    area = _RecordingArea("empty", events)
    area._life_state = LifeState.retired
    coop.register(area)

    assert coop.unfold() is context
    assert area.ticks == 0
    assert events == ["gc:empty"]
    assert coop._areas == []
    assert coop._area_cursor_store is None
    assert context[:] == original


def test_retained_area_without_effect_remains_scheduled() -> None:
    context, coop = _new_context()
    original = context[:]
    events: list[str] = []
    area = _RecordingArea("waiting", events)
    coop.register(area)

    assert coop.unfold() is context
    assert coop.unfold() is context
    assert coop._areas == [area]
    assert coop._area_mapping == {}
    assert area.life_state is LifeState.retain
    assert events == ["tick:waiting", "tick:waiting"]
    assert context[:] == original


def test_guard_notifications_follow_layout_order() -> None:
    context, coop = _new_context()
    original = context[:]
    events: list[str] = []
    first = _RecordingArea("first", events)
    waiting = _RecordingArea("waiting", events)
    last = _RecordingArea("last", events)
    first._life_state = LifeState.retired
    last._life_state = LifeState.retired
    for area in (first, waiting, last):
        coop.register(area)
    coop._area_cursor_store = last

    assert coop.unfold() is context
    assert coop._areas == [waiting]
    assert coop._area_cursor_store is waiting
    assert events == ["gc:first", "gc:last", "tick:waiting"]
    assert context[:] == original
    assert coop.garbage == []


def test_guard_cleanup_repairs_cursor_even_when_mapped_tail_is_retained() -> None:
    context, coop = _new_context()
    events: list[str] = []
    prefix = _RecordingArea("prefix", events, emits=True)
    empty = _RecordingArea(
        "empty", events, flow_state=FlowState.exclusive, retire_on_tick=True
    )
    tail = _RecordingArea("tail", events, flow_state=FlowState.exclusive, emits=True)
    for area in (prefix, empty, tail):
        coop.register(area)

    assert coop.unfold() is context
    assert coop._area_cursor_store is empty
    assert prefix in coop._area_mapping
    assert empty not in coop._area_mapping
    assert tail.ticks == 0
    previous_context = context[:]

    assert coop.unfold() is context
    assert coop._areas == [prefix, tail]
    assert coop._area_cursor_store is tail
    assert prefix.ticks == 1
    assert tail.ticks == 1
    assert context[:len(previous_context)] == previous_context
    assert coop.garbage == []
    assert events == ["tick:prefix", "tick:empty", "gc:empty", "tick:tail"]


def test_guard_cleanup_can_wrap_cursor_to_a_surviving_area() -> None:
    context, coop = _new_context()
    events: list[str] = []
    survivor = _RecordingArea("survivor", events, flow_state=FlowState.exclusive)
    empty = _RecordingArea("empty", events)
    empty._life_state = LifeState.retired
    coop.register(survivor)
    coop.register(empty)
    coop._area_cursor_store = empty

    assert coop.unfold() is context
    assert coop._areas == [survivor]
    assert coop._area_cursor_store is survivor
    assert events == ["gc:empty", "tick:survivor"]


def test_guard_cleanup_does_not_change_normal_promotion() -> None:
    context, coop = _new_context()
    original_prefix = context[:]
    events: list[str] = []
    materialized = _RecordingArea("materialized", events, emits=True, retire_on_tick=True)
    empty = _RecordingArea("empty", events, retire_on_tick=True)
    coop.register(materialized)
    coop.register(empty)

    assert coop.unfold() is context
    affected_tail = context[len(original_prefix):]
    assert len(affected_tail) == 1

    assert coop.unfold() is context
    assert coop._areas == []
    assert coop._area_mapping == {}
    assert coop._area_cursor_store is None
    assert coop.garbage == list(affected_tail)
    assert context[:len(original_prefix)] == original_prefix
    assert len(context) == len(original_prefix) + 1
    assert events == [
        "tick:materialized",
        "tick:empty",
        "gc:empty",
        "promote:materialized",
        "gc:materialized",
    ]
