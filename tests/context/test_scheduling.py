"""Scheduling samples timing before tick; it is not a reactive interpreter."""

import pytest

from hydrangea.context.area.core import InvokeTiming
from hydrangea.context.coop_context import AreaLane, AreaLayout, _AreaChain

from .helpers import Harness, TickStep, layout, phase_areas


def test_empty_unfold_returns_the_original_context(h: Harness) -> None:
    h.reply("prefix")
    original = h.context[:]
    h.unfold()
    h.unfold()
    assert h.context[:] == original
    assert not h.events and h.coop._cursor_store is None


@pytest.mark.parametrize("position", [0, 1, 2])
@pytest.mark.parametrize("grouped", [False, True])
def test_immediate_stops_at_selected_area_and_retains_its_chain(h: Harness, position: int, grouped: bool) -> None:
    areas = [h.area(name) for name in "abc"]
    areas[position].set_timing(InvokeTiming.immediate)
    items = [AreaLane(*areas)] if grouped else areas
    h.coop.compose(AreaLayout(items))
    h.unfold()
    assert phase_areas(h.events, "tick") == tuple(areas[:position + 1])
    assert h.coop._cursor_store is h.coop.fetch_handle(areas[position])._chain_ref
    h.events.clear()
    h.unfold()
    expected = areas[:position + 1] if grouped else [areas[position]]
    assert phase_areas(h.events, "tick") == tuple(expected)


@pytest.mark.parametrize("grouped", [False, True])
def test_all_deferrable_keeps_start_across_multiple_rounds(h: Harness, grouped: bool) -> None:
    a, b, c = (h.area(name) for name in "abc")
    h.coop.compose(AreaLayout([AreaLane(a, b), c] if grouped else [a, b, c]))
    start = h.coop.fetch_handle(a)._chain_ref
    for _ in range(4):
        h.events.clear()
        h.unfold()
        assert phase_areas(h.events, "tick") == (a, b, c)
        assert h.coop._cursor_store is start


@pytest.mark.parametrize("initial,next_timing,first,second", [
    (InvokeTiming.deferrable, InvokeTiming.immediate, ("a", "b"), ("a",)),
    (InvokeTiming.immediate, InvokeTiming.deferrable, ("a",), ("a", "b")),
])
def test_tick_timing_change_applies_only_at_next_check(h: Harness, initial, next_timing, first, second) -> None:
    a = h.area("a", timing=initial, steps=[TickStep(timing=next_timing)])
    b = h.area("b")
    h.coop.compose(AreaLayout([a, b]))
    h.unfold()
    assert tuple(x.name for x in phase_areas(h.events, "tick")) == first
    h.events.clear()
    h.unfold()
    assert tuple(x.name for x in phase_areas(h.events, "tick")) == second


def test_observe_timing_change_precedes_current_scheduling_check(h: Harness) -> None:
    a = h.area("a", on_observe=lambda area, _: area.set_timing(InvokeTiming.immediate))
    b = h.area("b")
    h.coop.compose(AreaLayout([a, b]))
    h.unfold()
    h.events.clear()
    h.unfold()
    assert phase_areas(h.events, "observe") == (a, b)
    assert phase_areas(h.events, "tick") == (a,)


def test_wraparound_keeps_nonzero_start_after_full_pass(h: Harness) -> None:
    a = h.area("a", timing=InvokeTiming.immediate, steps=[TickStep(timing=InvokeTiming.deferrable)])
    b = h.area("b", timing=InvokeTiming.immediate, steps=[TickStep(timing=InvokeTiming.deferrable)])
    c = h.area("c")
    h.coop.compose(AreaLayout([a, b, c]))
    h.unfold()
    h.unfold()
    assert h.coop._cursor_store is h.coop.fetch_handle(b)._chain_ref
    for _ in range(3):
        h.events.clear()
        h.unfold()
        assert phase_areas(h.events, "tick") == (b, c, a)
        assert h.coop._cursor_store is h.coop.fetch_handle(b)._chain_ref


def test_append_does_not_preempt_existing_cursor(h: Harness) -> None:
    a, b = h.area("a"), h.area("b", timing=InvokeTiming.immediate)
    h.coop.compose(AreaLayout([a, b]))
    h.unfold()
    current = h.coop._cursor_store
    c = h.area("c")
    h.coop.append_lane(AreaLane(c))
    assert h.coop._cursor_store is current
    h.events.clear()
    h.unfold()
    assert phase_areas(h.events, "tick") == (b,)
    b.set_timing(InvokeTiming.deferrable)
    h.events.clear()
    h.unfold()
    assert phase_areas(h.events, "tick") == (b, c, a)


def test_overlay_is_lifo_and_reveals_original_area_after_gc(h: Harness) -> None:
    base = h.area("base", timing=InvokeTiming.immediate)
    h.coop.append_lane(AreaLane(base))
    h.unfold()
    handle = h.coop.fetch_handle(base)
    first = h.area("first", timing=InvokeTiming.immediate, steps=[TickStep(retire=True)])
    second = h.area("second", timing=InvokeTiming.immediate, steps=[TickStep(retire=True)])
    h.coop.overlay(first, handle)
    h.coop.overlay(second, handle)
    assert layout(h.coop) == ((second, first, base),)
    for expected in (second, first, base):
        h.events.clear()
        h.unfold()
        assert phase_areas(h.events, "tick") == (expected,)
    assert (second.gc_count, first.gc_count, base.gc_count) == (1, 1, 0)


def test_overlay_of_another_lane_does_not_move_cursor(h: Harness) -> None:
    a, b = h.area("a", timing=InvokeTiming.immediate), h.area("b")
    h.coop.compose(AreaLayout([a, b]))
    h.unfold()
    current = h.coop._cursor_store
    urgent = h.area("urgent", timing=InvokeTiming.immediate)
    h.coop.overlay(urgent, h.coop.fetch_handle(b))
    assert h.coop._cursor_store is current
    h.events.clear()
    h.unfold()
    assert phase_areas(h.events, "tick") == (a,)
    a.retire()
    h.events.clear()
    h.unfold()
    assert phase_areas(h.events, "tick") == (urgent,)


def test_cursor_survives_current_and_adjacent_chain_deletion(h: Harness) -> None:
    a, b, c = (h.area(name, timing=InvokeTiming.immediate) for name in "abc")
    h.coop.compose(AreaLayout([a, b, c]))
    h.unfold()
    a.retire()
    h.unfold()
    assert layout(h.coop) == ((b,), (c,))
    assert h.coop._cursor_store is h.coop.fetch_handle(b)._chain_ref
    b.retire()
    c.retire()
    h.unfold()
    assert not layout(h.coop) and h.coop._cursor_store is None
    assert (a.gc_count, b.gc_count, c.gc_count) == (1, 1, 1)
    assert c.tick_count == 0


def test_cursor_repair_skips_empty_and_retired_chains(h: Harness) -> None:
    dead, live = h.area("dead"), h.area("live")
    empty = _AreaChain(dead)
    empty.pop_top()
    dead.retire()
    dead_chain, live_chain = _AreaChain(dead), _AreaChain(live)
    h.coop._area_chains = [empty, dead_chain, live_chain]
    h.coop._cursor_store = empty
    h.coop._cursor_repair()
    assert h.coop._cursor_store is live_chain
    live.retire()
    h.coop._cursor_repair()
    assert h.coop._cursor_store is None


def test_forward_without_cursor_is_rejected(h: Harness) -> None:
    with pytest.raises(RuntimeError, match="Empty cursor"):
        h.coop._cursor_forward()
