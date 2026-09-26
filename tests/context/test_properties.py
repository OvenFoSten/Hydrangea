"""500 generated interval layouts are compared with the overlap-graph oracle."""

from dataclasses import dataclass

from hypothesis import given, note, settings, strategies as st

from hydrangea.context.coop_context import AreaLane, AreaLayout, _INVALID_LAST_TOUCHED
from hydrangea.gateway import GatewayType

from .helpers import (
    Harness, assert_same_objects, members, seed_effect, seed_observe,
    state_snapshot, texts,
)
from .oracle import expected_collection


@dataclass(frozen=True)
class Node:
    kind: str
    start: int
    latest: int
    retired: bool
    promotions: int


@st.composite
def layouts(draw):
    size = draw(st.integers(0, 32))
    nodes = []
    for _ in range(draw(st.integers(0, 8 if size else 0))):
        start = draw(st.integers(0, size - 1))
        latest = draw(st.integers(start, size - 1))
        nodes.append(Node("effect", start, latest, draw(st.booleans()), draw(st.integers(0, 2))))
    for _ in range(draw(st.integers(0, 4))):
        start = draw(st.integers(0, size))
        latest = start if draw(st.booleans()) else size - 1
        nodes.append(Node("observe", start, latest, draw(st.booleans()), draw(st.integers(0, 2))))
    for _ in range(draw(st.integers(0, 4))):
        nodes.append(Node("untouched", 0, 0, draw(st.booleans()), draw(st.integers(0, 2))))
    order = draw(st.permutations(tuple(range(len(nodes))))) if nodes else ()
    cuts = draw(st.lists(st.booleans(), min_size=max(0, len(nodes) - 1), max_size=max(0, len(nodes) - 1)))
    return size, nodes, order, cuts


@settings(max_examples=500, deadline=None, derandomize=True, database=None)
@given(case=layouts())
def test_collector_and_gc_agree_with_independent_graph_model(case) -> None:
    size, specs, order, cuts = case
    note(f"interval case: {case!r}")
    h = Harness(GatewayType.openai)
    for index in range(size):
        h.reply(f"native-{index}")
    areas = [h.area(str(i), promotions=tuple(f"promote:{i}:{j}" for j in range(spec.promotions))) for i, spec in enumerate(specs)]
    groups = []
    group = []
    for index, key in enumerate(order):
        group.append(areas[key])
        if index == len(order) - 1 or cuts[index]:
            groups.append(AreaLane(*group))
            group = []
    h.coop.compose(AreaLayout(groups))
    effects, observes, retired = {}, {}, set()
    for key, (area, spec) in enumerate(zip(areas, specs)):
        if spec.kind == "effect":
            effects[key] = (spec.start, spec.latest)
            observes[key] = (spec.start, size - 1)
            seed_effect(h.coop, area, spec.start, spec.latest)
        elif spec.kind == "observe":
            observes[key] = (spec.start, spec.latest)
            seed_observe(h.coop, area, spec.start, spec.latest)
        if spec.retired:
            retired.add(key)
            area.retire()

    expected, earliest = expected_collection(set(range(len(areas))), retired, effects, observes)
    before = state_snapshot(h.coop)
    original = h.context[:]
    original_members = members(h.coop)
    plan = h.coop._collect()
    assert state_snapshot(h.coop) == before
    assert not h.events
    if not expected:
        assert plan is None
        return

    assert plan is not None
    assert plan.earliest == earliest
    assert plan.expected_context_size == size
    assert len(plan.candidates) == len(expected)
    assert {c.area for c in plan.candidates} == {areas[key] for key in expected}
    stamps = {}
    for key in expected:
        if key in effects:
            stamps[key] = effects[key][1]
        elif key in observes:
            stamps[key] = observes[key][1]
        else:
            stamps[key] = _INVALID_LAST_TOUCHED
    assert {c.area: c.last_touched for c in plan.candidates} == {areas[k]: value for k, value in stamps.items()}

    h.coop._cursor_repair()
    h.coop._gc(plan)
    removed_areas = {areas[key] for key in expected}
    assert_same_objects(members(h.coop), [a for a in original_members if a not in removed_areas])
    assert all(len(chain) for chain in h.coop._area_chains)
    assert h.coop._cursor_store is None or any(h.coop._cursor_store is c for c in h.coop._area_chains)
    keep = size if earliest is None else earliest
    assert_same_objects(h.context[:keep], original[:keep])
    assert_same_objects(h.coop.garbage, original[keep:])

    expected_promoted = {f"promote:{key}:{j}" for key in expected if specs[key].kind != "untouched" for j in range(specs[key].promotions)}
    actual_promoted = texts(h.context[keep:])
    assert set(actual_promoted) == expected_promoted
    assert len(actual_promoted) == len(expected_promoted)
    callback_keys = [int(event.area.name) for event in h.events if event.phase == "promote"]
    assert set(callback_keys) == {key for key in expected if specs[key].kind != "untouched"}
    assert [stamps[key] for key in callback_keys] == sorted(stamps[key] for key in callback_keys)
    expected_suffix = tuple(f"promote:{key}:{j}" for key in callback_keys for j in range(specs[key].promotions))
    assert actual_promoted == expected_suffix
    for key, area in enumerate(areas):
        assert area.gc_count == int(key in expected)
        assert area.promote_count == int(key in expected and specs[key].kind != "untouched")
        assert area.resource_open == (key not in expected)
        own_events = [event.phase for event in h.events if event.area is area]
        assert own_events == ([] if key not in expected else ["gc"] if specs[key].kind == "untouched" else ["promote", "gc"])
    assert set(h.coop._area_effect_range_mapping) == {areas[k] for k in effects.keys() - expected}
    assert set(h.coop._area_observe_range_mapping) == {areas[k] for k in observes.keys() - expected}
    for key in effects.keys() - expected:
        actual = h.coop._area_effect_range_mapping[areas[key]]
        assert (actual.start, actual.latest) == effects[key]
    for key in observes.keys() - expected:
        actual = h.coop._area_observe_range_mapping[areas[key]]
        assert (actual.start, actual.latest) == observes[key]
