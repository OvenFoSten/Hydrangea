"""Untouched and observe-only retirement are distinct lifecycle paths."""

import pytest

from hydrangea.context.area.core import InvokeTiming
from hydrangea.context.coop_context import AreaLane, AreaLayout

from .helpers import Harness, TickStep, assert_same_objects, layout, seed_effect, texts


def test_cancel_before_first_tick_releases_resources_without_promotion(h: Harness) -> None:
    h.reply("prefix")
    prefix = h.context[:]
    ask = h.area("ask", timing=InvokeTiming.immediate, steps=[TickStep(("question",))])
    waiting = h.area("waiting", promotions=("must-not-publish",))
    h.coop.compose(AreaLayout([ask, waiting]))
    h.unfold()
    h.reply("cancel")
    assert waiting.tick_count == 0
    ask.retire()
    waiting.retire()
    tail = h.context[1:]
    h.unfold()
    assert not layout(h.coop) and h.coop._cursor_store is None
    assert (ask.gc_count, waiting.gc_count) == (1, 1)
    assert (ask.promote_count, waiting.promote_count) == (1, 0)
    assert not ask.resource_open and not waiting.resource_open
    assert_same_objects(h.context[:], prefix)
    assert_same_objects(h.coop.garbage, tail)
    h.unfold()
    assert (ask.gc_count, waiting.gc_count) == (1, 1)


def test_only_untouched_candidates_do_not_edit_context_or_garbage(h: Harness) -> None:
    h.reply("prefix")
    original = h.context[:]
    a, b = h.area("a"), h.area("b")
    h.coop.append_lane(AreaLane(a, b))
    a.retire()
    b.retire()
    plan = h.coop._collect()
    assert plan is not None and plan.earliest is None
    h.unfold()
    h.unfold()
    assert (a.gc_count, b.gc_count) == (1, 1)
    assert (a.promote_count, b.promote_count) == (0, 0)
    assert (a.tick_count, b.tick_count) == (0, 0)
    assert_same_objects(h.context[:], original)
    assert h.coop.garbage == []


@pytest.mark.parametrize("prefix", [False, True])
@pytest.mark.parametrize("retirement", ["tick", "observe", "boundary"])
def test_observe_only_retirement_promotes_once_without_truncating(h: Harness, prefix: bool, retirement: str) -> None:
    if prefix:
        h.reply("prefix")
    original = h.context[:]
    area = h.area(
        "observer",
        steps=[TickStep(retire=retirement == "tick")],
        on_observe=(lambda a, _: a.retire()) if retirement == "observe" else None,
        promotions=("summary-1", "summary-2"),
    )
    h.coop.append_lane(AreaLane(area))
    h.unfold()
    assert area not in h.coop._area_effect_range_mapping
    assert area in h.coop._area_observe_range_mapping
    if retirement == "observe":
        h.unfold()
        assert area.observe_count == 1
        if not prefix:
            assert h.coop._area_observe_range_mapping[area].latest == -1
    elif retirement == "boundary":
        area.retire()
    assert area.gc_count == 0
    h.unfold()
    assert (area.promote_count, area.gc_count) == (1, 1)
    assert area.tick_count == 1 and not area.resource_open
    assert h.coop.fetch_handle(area) is None
    assert_same_objects(h.context[:len(original)], original)
    assert texts(h.context[len(original):]) == ("summary-1", "summary-2")
    assert h.coop.garbage == []
    after = h.context[:]
    h.unfold()
    h.unfold()
    assert_same_objects(h.context[:], after)
    assert (area.promote_count, area.gc_count) == (1, 1)


def test_live_untouched_and_live_observe_only_are_not_collected(h: Harness) -> None:
    blocker = h.area("blocker", timing=InvokeTiming.immediate)
    waiting = h.area("waiting")
    h.coop.compose(AreaLayout([blocker, waiting]))
    for _ in range(3):
        h.unfold()
        assert h.coop._collect() is None
    assert waiting.tick_count == 0 and blocker.tick_count == 3
    assert blocker in h.coop._area_observe_range_mapping
    assert waiting not in h.coop._area_observe_range_mapping
    assert blocker.resource_open and waiting.resource_open


def test_untouched_cleanup_still_runs_when_effect_collection_is_blocked(h: Harness) -> None:
    for i in range(5):
        h.reply(str(i))
    untouched, retired, live = (h.area(name) for name in ("untouched", "retired", "live"))
    h.coop.append_lane(AreaLane(untouched, retired, live))
    seed_effect(h.coop, retired, 1, 2)
    seed_effect(h.coop, live, 0, 4)
    untouched.retire()
    retired.retire()
    original = h.context[:]
    h.unfold()
    assert (untouched.gc_count, retired.gc_count, live.gc_count) == (1, 0, 0)
    assert retired.promote_count == 0 and retired.tick_count == 0 and retired.observe_count == 0
    assert_same_objects(h.context[:], original)
    assert h.coop.garbage == []
    live.retire()
    h.unfold()
    assert (untouched.gc_count, retired.gc_count, live.gc_count) == (1, 1, 1)
    assert_same_objects(h.coop.garbage, original)


def test_retired_null_timing_is_removed_without_scheduling_error(h: Harness) -> None:
    cancelled = h.area("cancelled", timing=InvokeTiming.null)
    cancelled.retire()
    h.coop.append_lane(AreaLane(cancelled))
    h.unfold()
    assert cancelled.tick_count == 0 and cancelled.gc_count == 1
