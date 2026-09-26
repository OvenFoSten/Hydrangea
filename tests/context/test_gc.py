"""Tail reclamation, promotion, cleanup multiplicity, and failure boundaries."""

import pytest

from hydrangea.context.area.core import InvokeTiming
from hydrangea.context.coop_context import AreaLane, AreaLayout

from .helpers import (
    Harness, TickStep, assert_same_objects, layout, phase_areas,
    seed_effect, seed_observe, state_snapshot, texts,
)


@pytest.mark.parametrize("prefix_size", [0, 1, 3])
@pytest.mark.parametrize("emission_size", [1, 3])
def test_gc_removes_exact_inclusive_tail_and_preserves_native_prefix(h: Harness, prefix_size: int, emission_size: int) -> None:
    for i in range(prefix_size):
        h.reply(f"prefix-{i}")
    prefix = h.context[:]
    values = tuple(f"emit-{i}" for i in range(emission_size))
    a = h.area("a", steps=[TickStep(values, retire=True)], promotions=("summary-1", "summary-2"))
    h.coop.append_lane(AreaLane(a))
    h.unfold()
    assert a.gc_count == 0
    h.reply("model-tail")
    old_tail = h.context[prefix_size:]
    h.unfold()
    assert_same_objects(h.context[:prefix_size], prefix)
    assert texts(h.context[prefix_size:]) == ("summary-1", "summary-2")
    assert_same_objects(h.coop.garbage, old_tail)
    assert (a.promote_count, a.gc_count) == (1, 1)
    assert a not in h.coop._area_effect_range_mapping
    assert a not in h.coop._area_observe_range_mapping
    after = state_snapshot(h.coop)
    h.unfold()
    assert state_snapshot(h.coop) == after


def test_single_message_tail_is_not_left_behind(h: Harness) -> None:
    h.reply("prefix")
    a = h.area("a", steps=[TickStep(("only",), retire=True)])
    h.coop.append_lane(AreaLane(a))
    h.unfold()
    removed = h.context[1:]
    h.unfold()
    assert texts(h.context[:]) == ("prefix",)
    assert_same_objects(h.coop.garbage, removed)


def test_garbage_accumulates_in_actual_removal_order(h: Harness) -> None:
    h.reply("prefix")
    expected = []
    for index in range(3):
        before = len(h.context)
        a = h.area(str(index), steps=[TickStep((f"data-{index}",), retire=True)], promotions=(f"summary-{index}",))
        h.coop.append_lane(AreaLane(a))
        h.unfold()
        h.reply(f"reply-{index}")
        expected.extend(h.context[before:])
        h.unfold()
        assert_same_objects(h.coop.garbage, expected)
        assert texts(h.context[:]) == ("prefix", *(f"summary-{j}" for j in range(index + 1)))


def test_gc_sweeps_adjacent_members_and_chains_without_index_drift(h: Harness) -> None:
    a, b, c, d, e, f = (h.area(name) for name in "abcdef")
    h.coop.compose(AreaLayout([AreaLane(a, b, c), AreaLane(d, e), f]))
    for area in (a, b, d, e, f):
        area.retire()
    h.unfold()
    assert layout(h.coop) == ((c,),)
    assert c.tick_count == 1 and c.resource_open
    for area in (a, b, d, e, f):
        assert area.gc_count == 1 and not area.resource_open
        assert h.coop.fetch_handle(area) is None


def test_promotions_order_by_last_touch_not_layout_and_gc_follows_own_promote(h: Harness) -> None:
    for index in range(6):
        h.reply(str(index))
    later = h.area("later", promotions=("later-1", "later-2"))
    early = h.area("early", promotions=("early",))
    untouched = h.area("untouched", promotions=("must-not-publish",))
    h.coop.compose(AreaLayout([later, untouched, early]))
    seed_effect(h.coop, early, 1, 2)
    seed_effect(h.coop, later, 3, 4)
    for area in (early, later, untouched):
        area.retire()
    h.unfold()
    assert texts(h.context[:]) == ("0", "early", "later-1", "later-2")
    assert phase_areas(h.events, "promote") == (early, later)
    for area in (early, later):
        phases = [event.phase for event in h.events if event.area is area]
        assert phases == ["promote", "gc"]
    assert untouched.promote_count == 0 and untouched.gc_count == 1


def test_tied_last_touch_does_not_require_inter_area_callback_order(h: Harness) -> None:
    h.reply("prefix")
    a = h.area("a", promotions=("a1", "a2"))
    b = h.area("b", promotions=("b1", "b2"))
    h.coop.compose(AreaLayout([a, b]))
    for area in (a, b):
        seed_observe(h.coop, area, 0, 0)
        area.retire()
    h.unfold()
    assert texts(h.context[1:]) in (("a1", "a2", "b1", "b2"), ("b1", "b2", "a1", "a2"))
    for area in (a, b):
        phases = [event.phase for event in h.events if event.area is area]
        assert phases == ["promote", "gc"]


def test_stale_collect_plan_fails_before_any_mutation(h: Harness) -> None:
    area = h.area("area", steps=[TickStep(("body",), retire=True)])
    h.coop.append_lane(AreaLane(area))
    h.unfold()
    plan = h.coop._collect()
    assert plan is not None
    h.reply("changed-after-plan")
    before = state_snapshot(h.coop)
    before_events = list(h.events)
    with pytest.raises(RuntimeError, match="Unexpected context change"):
        h.coop._gc(plan)
    assert state_snapshot(h.coop) == before
    assert h.events == before_events
    assert area.promote_count == 0 and area.gc_count == 0


def test_empty_tick_list_raises_and_later_candidates_do_not_execute(h: Harness) -> None:
    before = h.area("before", steps=[TickStep(("committed-before-error",))])
    bad = h.area("bad", steps=[TickStep(())])
    after = h.area("after")
    h.coop.compose(AreaLayout([before, bad, after]))
    with pytest.raises(ValueError, match="empty content"):
        h.coop.unfold()
    assert (before.tick_count, bad.tick_count, after.tick_count) == (1, 1, 0)
    assert texts(h.context[:]) == ("committed-before-error",)
    assert bad not in h.coop._area_effect_range_mapping
    assert bad not in h.coop._area_observe_range_mapping


def test_illegal_active_timing_fails_before_executing_preselected_prefix(h: Harness) -> None:
    good, bad = h.area("good"), h.area("bad", timing=InvokeTiming.null)
    h.coop.compose(AreaLayout([good, bad]))
    with pytest.raises(RuntimeError, match="InvokeTiming"):
        h.coop.unfold()
    assert good.tick_count == bad.tick_count == 0


@pytest.mark.parametrize("phase", ["observe", "tick", "promote", "gc"])
def test_callback_exception_propagates_and_stops_later_work(h: Harness, phase: str) -> None:
    failure = LookupError(f"failure in {phase}")
    a = h.area("a", promotions=("not-appended-on-failure",), fault=failure)
    b = h.area("b")
    h.coop.compose(AreaLayout([a, b]))
    if phase == "observe":
        h.unfold()
    elif phase in ("promote", "gc"):
        h.reply("0")
        h.reply("1")
        seed_observe(h.coop, a, 0, 0)
        seed_observe(h.coop, b, 1, 1)
        a.retire()
        b.retire()
    h.events.clear()
    before = h.context[:]
    a.fail_phase = phase
    with pytest.raises(LookupError) as caught:
        h.coop.unfold()
    assert caught.value is failure
    expected_phases = ["promote", "gc"] if phase == "gc" else [phase]
    assert [event.phase for event in h.events] == expected_phases
    assert all(event.area is a for event in h.events)
    assert_same_objects(h.context[:], before)
    # No retry: failure recovery/transactional rollback is not promised.


def test_untouched_gc_exception_propagates_without_context_changes(h: Harness) -> None:
    failure = RuntimeError("untouched cleanup failure")
    dead = h.area("dead", fail_phase="gc", fault=failure)
    h.coop.compose(AreaLayout([dead]))
    h.reply("body")
    dead.retire()
    with pytest.raises(RuntimeError) as caught:
        h.coop.unfold()
    assert caught.value is failure
    assert dead.promote_count == 0 and dead.gc_count == 1
    assert texts(h.context[:]) == ("body",) and h.coop.garbage == []
