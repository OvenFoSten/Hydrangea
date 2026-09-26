"""White-box geometry tests use only valid closed intervals and actual Context."""

import pytest

from hydrangea.context.coop_context import AreaLane, AreaLayout, _INVALID_LAST_TOUCHED

from .helpers import Harness, seed_effect, seed_observe, state_snapshot


@pytest.mark.parametrize("ranges,expected,earliest", [
    ([], set(), None),
    ([(2, 2, True)], {0}, 2),
    ([(2, 2, False)], set(), None),
    ([(0, 1, True), (3, 4, True)], {0, 1}, 0),
    ([(0, 1, False), (2, 3, True)], {1}, 2),
    ([(0, 2, False), (2, 4, True)], set(), None),
    ([(0, 8, False), (2, 5, True)], set(), None),
    ([(0, 8, True), (2, 5, True)], {0, 1}, 0),
    ([(0, 3, False), (2, 5, True), (4, 7, True), (6, 9, True)], set(), None),
    ([(0, 3, True), (2, 5, True), (4, 7, True), (6, 9, True)], {0, 1, 2, 3}, 0),
    ([(0, 3, False), (2, 5, True), (7, 8, True)], {2}, 7),
    ([(0, 1, True), (5, 6, False), (8, 9, True)], {2}, 8),
    ([(0, 1, True), (8, 9, False)], set(), None),
], ids=["none", "point", "live-point", "disjoint-retired", "adjacent", "touching", "nested-live", "nested-retired", "transitive-live", "transitive-retired", "independent-tail", "stop-at-middle", "live-tail"])
def test_collect_selects_only_longest_legal_tail(h: Harness, ranges, expected, earliest) -> None:
    for index in range(12):
        h.reply(str(index))
    areas = [h.area(str(index)) for index in range(len(ranges))]
    h.coop.compose(AreaLayout(areas))
    for area, (start, end, retired) in zip(areas, ranges):
        seed_effect(h.coop, area, start, end)
        if retired:
            area.retire()
    before = state_snapshot(h.coop)
    plan = h.coop._collect()
    assert state_snapshot(h.coop) == before
    assert not h.events
    if not expected:
        assert plan is None
    else:
        assert plan is not None
        assert {candidate.area for candidate in plan.candidates} == {areas[i] for i in expected}
        assert len(plan.candidates) == len(expected)
        assert plan.earliest == earliest
        assert plan.expected_context_size == len(h.context)
        assert all(c.last_touched == h.coop._area_effect_range_mapping[c.area].latest for c in plan.candidates)
        assert h.coop._collect() == plan


@pytest.mark.parametrize("barrier,collectable", [(2, True), (3, False), (4, False), (6, False)])
def test_observe_barrier_preserves_head_including_equal_boundary(h: Harness, barrier: int, collectable: bool) -> None:
    for index in range(6):
        h.reply(str(index))
    observer, tail = h.area("observer"), h.area("tail")
    h.coop.compose(AreaLayout([observer, tail]))
    seed_observe(h.coop, observer, barrier)
    seed_effect(h.coop, tail, 3, 5)
    tail.retire()
    plan = h.coop._collect()
    if collectable:
        assert plan is not None and plan.earliest == 3
        assert [candidate.area for candidate in plan.candidates] == [tail]
    else:
        assert plan is None


def test_maximum_active_observe_head_is_the_barrier(h: Harness) -> None:
    for index in range(6):
        h.reply(str(index))
    left, right, tail = (h.area(name) for name in ("left", "right", "tail"))
    h.coop.compose(AreaLayout([left, right, tail]))
    seed_observe(h.coop, left, 1)
    seed_observe(h.coop, right, 4)
    seed_effect(h.coop, tail, 3, 5)
    tail.retire()
    assert h.coop._collect() is None
    right.retire()
    plan = h.coop._collect()
    assert plan is not None and plan.earliest == 3
    assert {c.area for c in plan.candidates} == {right, tail}


def test_overlap_can_pull_component_left_across_barrier(h: Harness) -> None:
    for index in range(15):
        h.reply(str(index))
    observer, wide, tail = (h.area(name) for name in ("observer", "wide", "tail"))
    h.coop.compose(AreaLayout([observer, wide, tail]))
    seed_observe(h.coop, observer, 8)
    seed_effect(h.coop, wide, 5, 11)
    seed_effect(h.coop, tail, 10, 12)
    wide.retire()
    tail.retire()
    assert h.coop._collect() is None


def test_barrier_does_not_discard_already_independent_right_tail(h: Harness) -> None:
    for index in range(15):
        h.reply(str(index))
    observer, left, right = (h.area(name) for name in ("observer", "left", "right"))
    h.coop.compose(AreaLayout([observer, left, right]))
    seed_observe(h.coop, observer, 8)
    seed_effect(h.coop, left, 5, 9)
    seed_effect(h.coop, right, 11, 13)
    left.retire()
    right.retire()
    plan = h.coop._collect()
    assert plan is not None and plan.earliest == 11
    assert [candidate.area for candidate in plan.candidates] == [right]


def test_no_effect_candidates_are_collected_even_if_live_effect_blocks_tail(h: Harness) -> None:
    h.reply("live")
    untouched, observer, live = (h.area(name) for name in ("untouched", "observer", "live"))
    h.coop.compose(AreaLayout([AreaLane(untouched, observer), live]))
    seed_observe(h.coop, observer, 0)
    seed_effect(h.coop, live, 0, 0)
    untouched.retire()
    observer.retire()
    plan = h.coop._collect()
    assert plan is not None and plan.earliest is None
    touched = {c.area: c.last_touched for c in plan.candidates}
    assert touched == {untouched: _INVALID_LAST_TOUCHED, observer: 0}


def test_empty_context_observe_timestamp_is_not_untouched_sentinel(h: Harness) -> None:
    untouched, observer = h.area("untouched"), h.area("observer")
    h.coop.compose(AreaLayout([untouched, observer]))
    seed_observe(h.coop, observer, 0, -1)
    untouched.retire()
    observer.retire()
    plan = h.coop._collect()
    assert plan is not None and plan.earliest is None
    stamps = {c.area: c.last_touched for c in plan.candidates}
    assert stamps[untouched] == _INVALID_LAST_TOUCHED
    assert stamps[observer] == -1 != _INVALID_LAST_TOUCHED
