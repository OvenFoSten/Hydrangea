"""External decisions add Areas between unfolds; the runtime does not branch."""

from hydrangea.context.area.core import InvokeTiming, LifeState
from hydrangea.context.coop_context import AreaLane

from .helpers import Harness, TickStep, assert_same_objects, layout, texts


def test_information_then_conditional_overlay_then_compaction(h: Harness) -> None:
    h.reply("prefix")
    prefix = h.context[:]
    a = h.area(
        "information",
        timing=InvokeTiming.immediate,
        steps=[TickStep(("need-info",)), TickStep(), TickStep(("final-request",), retire=True)],
        promotions=("final-summary",),
    )
    h.coop.append_lane(AreaLane(a))
    handle = h.coop.fetch_handle(a)
    h.unfold()
    assert texts(h.context[:]) == ("prefix", "need-info")
    assert (h.coop._area_effect_range_mapping[a].start, h.coop._area_effect_range_mapping[a].latest) == (1, 1)
    assert h.coop._cursor_store is handle._chain_ref

    h.reply("not-ready")
    h.unfold()
    assert layout(h.coop) == ((a,),)  # External decision: no B exists yet.
    assert texts(a.snapshots[-1]) == ("need-info", "not-ready")
    assert texts(h.context[:]) == ("prefix", "need-info", "not-ready")

    h.reply("ready")
    b = h.area("work", timing=InvokeTiming.immediate, steps=[TickStep(("work",), retire=True)], promotions=("work-summary",))
    h.coop.overlay(b, handle)
    assert layout(h.coop) == ((b, a),)
    h.unfold()
    assert (a.tick_count, b.tick_count) == (2, 1)
    assert b.life_state is LifeState.retired and b.gc_count == 0
    assert texts(a.snapshots[-1]) == ("need-info", "not-ready", "ready")
    assert (h.coop._area_effect_range_mapping[b].start, h.coop._area_effect_range_mapping[b].latest) == (4, 4)
    h.reply("work-result")
    first_garbage = h.context[4:]

    h.unfold()
    assert layout(h.coop) == ((a,),)
    assert h.coop.fetch_handle(b) is None
    assert h.coop._cursor_store is handle._chain_ref
    assert (b.promote_count, b.gc_count) == (1, 1)
    assert texts(a.snapshots[-1]) == ("need-info", "not-ready", "ready", "work-summary")
    assert texts(h.context[:]) == ("prefix", "need-info", "not-ready", "ready", "work-summary", "final-request")
    assert (h.coop._area_effect_range_mapping[a].start, h.coop._area_effect_range_mapping[a].latest) == (1, 5)
    assert a.life_state is LifeState.retired and a.gc_count == 0
    assert_same_objects(h.coop.garbage, first_garbage)

    h.reply("final-model")
    second_garbage = h.context[1:]
    h.unfold()
    assert_same_objects(h.context[:1], prefix)
    assert texts(h.context[:]) == ("prefix", "final-summary")
    assert_same_objects(h.coop.garbage, (*first_garbage, *second_garbage))
    assert not h.coop._area_effect_range_mapping and not h.coop._area_observe_range_mapping
    assert not layout(h.coop) and h.coop._cursor_store is None
    assert (a.promote_count, a.gc_count, b.promote_count, b.gc_count) == (1, 1, 1, 1)
    final = h.context[:]
    h.unfold()
    assert_same_objects(h.context[:], final)


def test_layered_overlay_observe_barrier_cancellation_and_runtime_reuse(h: Harness) -> None:
    h.reply("prefix")
    prefix = h.context[:]
    base = h.area("base", timing=InvokeTiming.immediate, promotions=("base-summary",))
    h.coop.append_lane(AreaLane(base))
    h.unfold()
    assert base not in h.coop._area_effect_range_mapping
    assert h.coop._area_observe_range_mapping[base].start == 1
    h.reply("anchor")

    observer = h.area("observer", timing=InvokeTiming.immediate, steps=[TickStep(), TickStep(retire=True)], promotions=("observer-summary",))
    handle = h.coop.fetch_handle(base)
    h.coop.overlay(observer, handle)
    h.unfold()
    assert h.coop._area_observe_range_mapping[observer].start == 2
    assert texts(base.snapshots[-1]) == ("anchor",)

    cancelled = h.area("cancelled", promotions=("must-not-publish",))
    h.coop.append_lane(AreaLane(cancelled))
    cancelled.retire()
    worker = h.area("worker", timing=InvokeTiming.immediate, steps=[TickStep(("work",), retire=True)], promotions=("worker-summary",))
    h.coop.overlay(worker, handle)
    h.unfold()
    assert cancelled.tick_count == 0 and cancelled.gc_count == 1 and cancelled.promote_count == 0
    assert layout(h.coop) == ((worker, observer, base),)
    assert observer.snapshots[-1] == ()
    h.reply("work-reply")
    removed = h.context[2:]

    # Observer's start == worker's effect start: worker cannot yet be collected.
    assert h.coop._collect() is None
    h.unfold()
    assert worker.gc_count == 0 and worker.resource_open
    assert texts(observer.snapshots[-1]) == ("work", "work-reply")
    assert observer.life_state is LifeState.retired and observer.gc_count == 0

    h.unfold()
    assert layout(h.coop) == ((base,),)
    assert (worker.gc_count, observer.gc_count, base.gc_count) == (1, 1, 0)
    assert texts(h.context[:]) == ("prefix", "anchor", "worker-summary", "observer-summary")
    assert texts(base.snapshots[-1]) == ("anchor", "worker-summary", "observer-summary")
    assert_same_objects(h.coop.garbage, removed)
    assert h.coop._cursor_store is handle._chain_ref

    base.retire()
    before = h.context[:]
    h.unfold()
    assert_same_objects(h.context[:len(before)], before)
    assert texts(h.context[:]) == ("prefix", "anchor", "worker-summary", "observer-summary", "base-summary")
    assert not layout(h.coop) and base.gc_count == 1

    fresh = h.area("fresh", timing=InvokeTiming.immediate, steps=[TickStep(("fresh-work",), retire=True)], promotions=("fresh-summary",))
    h.coop.append_lane(AreaLane(fresh))
    keep = h.context[:]
    h.unfold()
    h.reply("fresh-reply")
    new_removed = h.context[len(keep):]
    h.unfold()
    assert_same_objects(h.context[:len(keep)], keep)
    assert_same_objects(h.context[:1], prefix)
    assert texts(h.context[len(keep):]) == ("fresh-summary",)
    assert_same_objects(h.coop.garbage, (*removed, *new_removed))
    assert not layout(h.coop) and h.coop._cursor_store is None
    for area in (base, observer, cancelled, worker, fresh):
        assert area.gc_count == 1 and not area.resource_open
        assert h.coop.fetch_handle(area) is None
