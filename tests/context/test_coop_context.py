# pyright: reportPrivateUsage=false

from collections.abc import Sequence

from hydrangea.context import Context, NativeContent
from hydrangea.context.area import AreaFlowState, AreaLifeState
from hydrangea.context.coop_context import (
    ContextIndex,
    CoopContext,
    _EffectRange,
)
from hydrangea.gateway import GatewayType
from hydrangea.message import Message, Role


class _FakeArea:
    name: str
    _life_state: AreaLifeState
    _flow_state: AreaFlowState
    _events: list[str]
    _render_content: bool
    observed_count: int

    def __init__(
        self,
        name: str,
        life_state: AreaLifeState,
        events: list[str],
        render_content: bool = False,
    ) -> None:
        self.name = name
        self._life_state = life_state
        self._flow_state = AreaFlowState.yielded
        self._events = events
        self._render_content = render_content
        self.observed_count = 0

    @property
    def life_state(self) -> AreaLifeState:
        return self._life_state

    @property
    def flow_state(self) -> AreaFlowState:
        return self._flow_state

    def observe(
        self,
        context: Sequence[NativeContent],
    ) -> None:
        _ = context
        self.observed_count += 1

    def render(self) -> list[Message]:
        if not self._render_content:
            return []

        return [
            Message(
                role=Role.user,
                content=f"rendered:{self.name}",
            )
        ]

    def promote(self) -> tuple[Message, ...]:
        self._events.append(f"promote:{self.name}")
        return (
            Message(
                role=Role.user,
                content=f"promoted:{self.name}",
            ),
        )

    def gc_prologue(self) -> None:
        self._events.append(f"gc:{self.name}")


def _context_with_messages(count: int) -> Context:
    context = Context(GatewayType.gemini)
    for index in range(count):
        context.emplace_message(
            Message(
                role=Role.user,
                content=f"message:{index}",
            )
        )

    return context


def test_context_slice_uses_python_bounds() -> None:
    context = _context_with_messages(4)

    assert len(context[1:3]) == 2
    assert len(context[:]) == 4
    assert context[2:2] == ()
    assert len(context[-2:]) == 2


def test_observe_only_updates_areas_reached_by_cursor() -> None:
    events: list[str] = []
    yielded_prefix = _FakeArea(
        "yielded-prefix",
        AreaLifeState.retain,
        events,
        render_content=True,
    )
    exclusive = _FakeArea(
        "exclusive",
        AreaLifeState.retain,
        events,
        render_content=True,
    )
    exclusive._flow_state = AreaFlowState.exclusive
    hidden_tail = _FakeArea(
        "hidden-tail",
        AreaLifeState.retain,
        events,
        render_content=True,
    )

    context = CoopContext(_context_with_messages(0))
    context.register(yielded_prefix)
    context.register(exclusive)
    context.register(hidden_tail)

    _ = context.advance()
    assert yielded_prefix.observed_count == 0
    assert exclusive.observed_count == 0
    assert hidden_tail.observed_count == 0

    _ = context.advance()
    assert yielded_prefix.observed_count == 0
    assert exclusive.observed_count == 1
    assert hidden_tail.observed_count == 0

    _ = context.advance()
    assert yielded_prefix.observed_count == 0
    assert exclusive.observed_count == 2
    assert hidden_tail.observed_count == 0


def test_collector_follows_transitive_overlap_chain() -> None:
    events: list[str] = []
    area_a = _FakeArea("a", AreaLifeState.retain, events)
    area_b = _FakeArea("b", AreaLifeState.retired, events)
    area_c = _FakeArea("c", AreaLifeState.retired, events)
    area_d = _FakeArea("d", AreaLifeState.retired, events)

    context = CoopContext(_context_with_messages(10))
    for area in (area_a, area_b, area_c, area_d):
        context.register(area)

    context._area_mapping = {
        area_a: _EffectRange(ContextIndex(0), ContextIndex(3)),
        area_b: _EffectRange(ContextIndex(2), ContextIndex(5)),
        area_c: _EffectRange(ContextIndex(4), ContextIndex(7)),
        area_d: _EffectRange(ContextIndex(6), ContextIndex(9)),
    }

    assert context._collect() is None

    area_a._life_state = AreaLifeState.retired
    plan = context._collect()

    assert plan is not None
    assert plan.earliest == ContextIndex(0)
    assert plan.areas == (area_d, area_c, area_b, area_a)


def test_gc_repairs_cursor_and_preserves_unwind_order() -> None:
    events: list[str] = []
    survivor = _FakeArea("survivor", AreaLifeState.retain, events)
    outer = _FakeArea("outer", AreaLifeState.retired, events)
    inner = _FakeArea("inner", AreaLifeState.retired, events)

    context = CoopContext(_context_with_messages(6))
    for area in (survivor, outer, inner):
        context.register(area)

    context._area_cursor_store = outer
    context._area_mapping = {
        survivor: _EffectRange(ContextIndex(0), ContextIndex(1)),
        outer: _EffectRange(ContextIndex(2), ContextIndex(5)),
        inner: _EffectRange(ContextIndex(3), ContextIndex(4)),
    }

    plan = context._collect()
    assert plan is not None
    assert plan.areas == (outer, inner)

    context._gc(plan)

    assert context._areas == [survivor]
    assert tuple(context._area_mapping) == (survivor,)
    assert context._area_cursor_store is survivor
    assert len(context.garbage) == 4
    assert len(context._context) == 4
    assert events == [
        "promote:inner",
        "promote:outer",
        "gc:inner",
        "gc:outer",
    ]


def test_cursor_repair_uses_collection_membership() -> None:
    events: list[str] = []
    selected = _FakeArea("selected", AreaLifeState.retired, events)
    disjoint = _FakeArea("disjoint", AreaLifeState.retired, events)

    context = CoopContext(_context_with_messages(6))
    context.register(selected)
    context.register(disjoint)
    context._area_cursor_store = selected
    context._area_mapping = {
        selected: _EffectRange(ContextIndex(4), ContextIndex(5)),
        disjoint: _EffectRange(ContextIndex(0), ContextIndex(1)),
    }

    plan = context._collect()
    assert plan is not None
    assert plan.areas == (selected,)

    context._gc(plan)

    assert context._area_cursor_store is disjoint
    assert context._areas == [disjoint]
    assert tuple(context._area_mapping) == (disjoint,)


def test_render_can_collect_entire_heap_without_cursor() -> None:
    events: list[str] = []
    only_area = _FakeArea("only", AreaLifeState.retired, events)

    context = CoopContext(_context_with_messages(2))
    context.register(only_area)
    context._area_mapping = {
        only_area: _EffectRange(ContextIndex(0), ContextIndex(1)),
    }

    result = context.advance()

    assert result is context._context
    assert context._areas == []
    assert context._area_mapping == {}
    assert context._area_cursor_store is None
    assert len(context.garbage) == 2
    assert len(context._context) == 1
    assert events == ["promote:only", "gc:only"]
