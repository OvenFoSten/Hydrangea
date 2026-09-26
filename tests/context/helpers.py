"""Small recording doubles and assertions; no runtime algorithm is mocked."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from google.genai import types
from openai.types.chat import ChatCompletionMessage

from hydrangea.context import Context, NativeContent
from hydrangea.context.area.core import Area, InvokeTiming, LifeState
from hydrangea.context.coop_context import (
    CoopContext,
    _EffectRange,
    _ObserveRange,
)
from hydrangea.gateway import GatewayType
from hydrangea.message import Message, Role


@dataclass(frozen=True)
class TickStep:
    texts: tuple[str, ...] | None = None
    timing: InvokeTiming | None = None
    retire: bool = False


@dataclass(frozen=True)
class Event:
    phase: str
    area: object


def text_of(item: NativeContent) -> str:
    if isinstance(item, types.Content):
        return "".join(part.text or "" for part in item.parts or ())
    if isinstance(item, ChatCompletionMessage):
        return item.content or ""
    value = item.get("content")
    assert isinstance(value, str), item
    return value


def texts(items: Sequence[NativeContent]) -> tuple[str, ...]:
    return tuple(text_of(item) for item in items)


def assert_same_objects(actual: Sequence[object], expected: Sequence[object]) -> None:
    assert len(actual) == len(expected)
    assert all(a is b for a, b in zip(actual, expected))


class RecordingArea(Area):
    def __init__(
        self,
        name: str,
        events: list[Event] | None = None,
        *,
        timing: InvokeTiming = InvokeTiming.deferrable,
        steps: Iterable[TickStep] = (),
        default: TickStep = TickStep(),
        promotions: tuple[str, ...] = (),
        on_observe: Callable[[RecordingArea, Sequence[NativeContent]], None] | None = None,
        fail_phase: str | None = None,
        fault: Exception | None = None,
    ) -> None:
        super().__init__(invoke_timing=timing)
        self.name = name
        self.events = events if events is not None else []
        self.steps = deque(steps)
        self.default = default
        self.promotions = promotions
        self.on_observe = on_observe
        self.fail_phase = fail_phase
        self.fault = fault if fault is not None else RuntimeError("injected callback failure")
        self.tick_count = 0
        self.observe_count = 0
        self.promote_count = 0
        self.gc_count = 0
        self.resource_open = True
        self.snapshots: list[tuple[NativeContent, ...]] = []
        self.outputs: list[tuple[str, ...] | None] = []

    def retire(self) -> None:
        self._retire()

    def set_timing(self, timing: InvokeTiming) -> None:
        self._invoke_timing = timing

    def _record(self, phase: str) -> None:
        self.events.append(Event(phase, self))
        if self.fail_phase == phase:
            raise self.fault

    def observe(self, context: Sequence[NativeContent]) -> None:
        assert self.resource_open
        assert self.life_state is LifeState.retain
        self.observe_count += 1
        self._record("observe")
        super().observe(context)
        self.snapshots.append(tuple(context))
        if self.on_observe is not None:
            self.on_observe(self, context)

    def tick(self) -> list[Message] | None:
        assert self.resource_open
        assert self.life_state is LifeState.retain
        self.tick_count += 1
        self._record("tick")
        step = self.steps.popleft() if self.steps else self.default
        if step.timing is not None:
            self.set_timing(step.timing)
        if step.retire:
            self.retire()
        self.outputs.append(step.texts)
        if step.texts is None:
            return None
        return [Message(role=Role.user, content=text) for text in step.texts]

    def promote(self) -> tuple[Message, ...]:
        assert self.resource_open, "promote after resource release"
        self.promote_count += 1
        self._record("promote")
        return tuple(Message(role=Role.user, content=text) for text in self.promotions)

    def gc_prologue(self) -> None:
        assert self.resource_open, "resource released more than once"
        self.gc_count += 1
        self._record("gc")
        self.resource_open = False


class ProtocolArea:
    """A structural implementation, intentionally not derived from Area.

    Every instance has the same hash but retains object identity equality.
    """

    def __init__(self) -> None:
        self._life_state = LifeState.retain
        self._invoke_timing = InvokeTiming.deferrable
        self._observe_snapshot: tuple[NativeContent, ...] = ()
        self.tick_count = 0
        self.gc_count = 0

    def __hash__(self) -> int:
        return 17

    @property
    def life_state(self) -> LifeState:
        return self._life_state

    @property
    def invoke_timing(self) -> InvokeTiming:
        return self._invoke_timing

    def observe(self, context: Sequence[NativeContent]) -> None:
        self._observe_snapshot = tuple(context)

    def tick(self) -> list[Message] | None:
        self.tick_count += 1
        return None

    def promote(self) -> tuple[Message, ...]:
        return ()

    def gc_prologue(self) -> None:
        self.gc_count += 1


class UnhashableArea(ProtocolArea):
    def __hash__(self) -> int:
        raise TypeError("deliberately unhashable")


class Harness:
    def __init__(self, gateway: GatewayType, prefix: tuple[str, ...] = ()) -> None:
        self.context = Context(gateway)
        for value in prefix:
            self.context.emplace_message(Message(role=Role.user, content=value))
        self.coop = CoopContext(self.context)
        self.events: list[Event] = []

    def reply(self, text: str) -> None:
        self.context.emplace_message(Message(role=Role.assistant, content=text))

    def area(self, name: str, **kwargs) -> RecordingArea:
        return RecordingArea(name, self.events, **kwargs)

    def unfold(self) -> Context:
        result = self.coop.unfold()
        assert result is self.context
        assert_runtime_invariants(self.coop)
        return result


def members(coop: CoopContext) -> tuple[object, ...]:
    return tuple(area for chain in coop._area_chains for area in chain)


def layout(coop: CoopContext) -> tuple[tuple[object, ...], ...]:
    return tuple(tuple(chain) for chain in coop._area_chains)


def phase_areas(events: Sequence[Event], phase: str) -> tuple[object, ...]:
    return tuple(event.area for event in events if event.phase == phase)


def state_snapshot(coop: CoopContext) -> tuple[object, ...]:
    """Identity-sensitive snapshot for validation failure atomicity."""
    return (
        tuple((id(chain), tuple(id(a) for a in chain)) for chain in coop._area_chains),
        id(coop._cursor_store) if coop._cursor_store is not None else None,
        tuple((id(a), r.start, r.latest) for a, r in coop._area_effect_range_mapping.items()),
        tuple((id(a), r.start, r.latest) for a, r in coop._area_observe_range_mapping.items()),
        tuple(id(item) for item in coop._context[:]),
        texts(coop._context[:]),
        tuple(id(item) for item in coop.garbage),
        texts(coop.garbage),
    )


def assert_runtime_invariants(coop: CoopContext) -> None:
    registered = members(coop)
    assert len({id(area) for area in registered}) == len(registered)
    assert all(len(chain) for chain in coop._area_chains)
    assert coop._cursor_store is None or any(
        coop._cursor_store is chain for chain in coop._area_chains
    )
    for area, effect in coop._area_effect_range_mapping.items():
        assert any(area is candidate for candidate in registered)
        assert 0 <= effect.start <= effect.latest < len(coop._context)
        assert area in coop._area_observe_range_mapping
    for area, observe in coop._area_observe_range_mapping.items():
        assert any(area is candidate for candidate in registered)
        assert 0 <= observe.start <= len(coop._context)
        # A newly created observation may point at a not-yet-appended reply.
        assert -1 <= observe.latest
        if area.life_state is LifeState.retain:
            assert observe.latest <= len(coop._context)
        # Retired effect-owning Areas can retain an old observation timestamp
        # while another independent tail is reclaimed. They are not observed.


def seed_effect(coop: CoopContext, area: RecordingArea, start: int, latest: int) -> None:
    coop._area_effect_range_mapping[area] = _EffectRange(start, latest)
    coop._area_observe_range_mapping[area] = _ObserveRange(start, len(coop._context) - 1)


def seed_observe(coop: CoopContext, area: RecordingArea, start: int, latest: int | None = None) -> None:
    coop._area_observe_range_mapping[area] = _ObserveRange(
        start, len(coop._context) - 1 if latest is None else latest
    )
