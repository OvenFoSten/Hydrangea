"""Observation and effect regions, including empty/prospective boundaries."""

from hydrangea.context.area.core import InvokeTiming
from hydrangea.context.coop_context import AreaLane, AreaLayout

from .helpers import Harness, TickStep, assert_same_objects, phase_areas, texts


def test_none_then_emit_then_none_keeps_observation_head_and_effect_bounds(h: Harness) -> None:
    h.reply("prefix")
    a = h.area("a", steps=[TickStep(), TickStep(("a1", "a2")), TickStep()])
    h.coop.append_lane(AreaLane(a))
    h.unfold()
    ob = h.coop._area_observe_range_mapping[a]
    assert (ob.start, ob.latest) == (1, 1)
    assert a not in h.coop._area_effect_range_mapping
    assert a.observe_count == 0
    h.reply("reply-1")
    h.unfold()
    effect = h.coop._area_effect_range_mapping[a]
    assert (effect.start, effect.latest) == (2, 3)
    assert (ob.start, ob.latest) == (1, 1)
    assert texts(a.snapshots[-1]) == ("reply-1",)
    h.reply("reply-2")
    h.unfold()
    assert (effect.start, effect.latest) == (2, 3)
    assert (ob.start, ob.latest) == (1, 4)
    assert texts(a.snapshots[-1]) == ("reply-1", "a1", "a2", "reply-2")


def test_repeated_none_on_empty_context_has_valid_empty_observations(h: Harness) -> None:
    a = h.area("waiting")
    h.coop.append_lane(AreaLane(a))
    h.unfold()
    assert h.coop._area_observe_range_mapping[a].start == 0
    for _ in range(3):
        h.unfold()
        ob = h.coop._area_observe_range_mapping[a]
        assert (ob.start, ob.latest) == (0, -1)
        assert a.snapshots[-1] == ()
        assert a not in h.coop._area_effect_range_mapping
    assert a.tick_count == 4 and a.observe_count == 3


def test_multi_message_effect_and_interleaved_output_use_inclusive_indices(h: Harness) -> None:
    a = h.area("a", steps=[TickStep(("a0",)), TickStep(("a1", "a2"))])
    b = h.area("b", steps=[TickStep(("b0",)), TickStep()])
    h.coop.compose(AreaLayout([a, b]))
    h.unfold()
    assert (h.coop._area_effect_range_mapping[a].start, h.coop._area_effect_range_mapping[a].latest) == (0, 0)
    assert (h.coop._area_effect_range_mapping[b].start, h.coop._area_effect_range_mapping[b].latest) == (1, 1)
    h.reply("model")
    before_tick = h.context[:]
    h.unfold()
    assert (h.coop._area_effect_range_mapping[a].start, h.coop._area_effect_range_mapping[a].latest) == (0, 4)
    assert (h.coop._area_effect_range_mapping[b].start, h.coop._area_effect_range_mapping[b].latest) == (1, 1)
    assert_same_objects(a.snapshots[-1], before_tick)
    assert_same_objects(b.snapshots[-1], before_tick[1:])
    assert texts(h.context[:]) == ("a0", "b0", "model", "a1", "a2")


def test_all_existing_live_ranges_observe_even_when_tick_is_hidden(h: Harness) -> None:
    a = h.area("a", steps=[TickStep(("a",))])
    b = h.area("b", steps=[TickStep(("b",))])
    h.coop.compose(AreaLayout([a, b]))
    h.unfold()
    h.reply("model")
    urgent = h.area("urgent", timing=InvokeTiming.immediate)
    h.coop.overlay(urgent, h.coop.fetch_handle(a))
    before_tick = h.context[:]
    h.events.clear()
    h.unfold()
    assert phase_areas(h.events, "observe") == (a, b)
    assert phase_areas(h.events, "tick") == (urgent,)
    assert_same_objects(a.snapshots[-1], before_tick)
    assert_same_objects(b.snapshots[-1], before_tick[1:])
    assert urgent.observe_count == 0


def test_observe_can_retire_self_before_candidate_selection(h: Harness) -> None:
    a = h.area("a", on_observe=lambda area, _: area.retire())
    h.coop.append_lane(AreaLane(a))
    h.unfold()
    h.unfold()
    assert a.tick_count == 1 and a.observe_count == 1
    assert a.gc_count == 0  # This call's collection preceded observe().
    h.unfold()
    assert (a.promote_count, a.gc_count) == (1, 1)
    assert h.coop.fetch_handle(a) is None


def test_gc_updates_observation_to_shortened_context_before_next_tick(h: Harness) -> None:
    observer = h.area("observer")
    h.coop.append_lane(AreaLane(observer))
    h.unfold()
    h.reply("head")
    tail = h.area("tail", steps=[TickStep(("tail",)), TickStep(retire=True)], promotions=("summary",))
    h.coop.append_lane(AreaLane(tail))
    h.unfold()
    h.reply("tail-reply")
    h.unfold()
    assert texts(observer.snapshots[-1]) == ("head", "tail", "tail-reply")
    assert h.coop._area_observe_range_mapping[observer].latest == 2
    old_tail = h.context[1:]
    h.unfold()
    assert texts(observer.snapshots[-1]) == ("head", "summary")
    assert (h.coop._area_observe_range_mapping[observer].start, h.coop._area_observe_range_mapping[observer].latest) == (0, 1)
    assert_same_objects(h.coop.garbage, old_tail)


def test_observe_only_covers_later_area_output_and_model_reply(h: Harness) -> None:
    observer = h.area("observer")
    writer = h.area("writer", steps=[TickStep(("later-area",))])
    h.coop.compose(AreaLayout([observer, writer]))
    h.unfold()
    h.reply("model-reply")
    h.unfold()
    assert texts(observer.snapshots[-1]) == ("later-area", "model-reply")


def test_multiple_emit_messages_create_exact_first_range(h: Harness) -> None:
    h.reply("prefix")
    a = h.area("a", steps=[TickStep(("one", "two", "three"))])
    h.coop.append_lane(AreaLane(a))
    h.unfold()
    effect = h.coop._area_effect_range_mapping[a]
    assert (effect.start, effect.latest) == (1, 3)
    h.unfold()
    assert texts(a.snapshots[-1]) == ("one", "two", "three")
