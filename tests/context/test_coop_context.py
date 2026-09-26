"""Public layout/identity contracts and focused stack primitive tests."""

from dataclasses import dataclass

import pytest

from hydrangea.context.area.core import Area, InvokeTiming
from hydrangea.context.coop_context import AreaLane, AreaLayout, _AreaChain

from .helpers import (
    Harness, ProtocolArea, RecordingArea, TickStep, UnhashableArea,
    assert_same_objects, layout, members, phase_areas, state_snapshot,
)


def test_compose_preserves_declaration_order_and_area_identity(h: Harness) -> None:
    a, b, c = (h.area(name) for name in "abc")
    lane = AreaLane(a, b)
    h.coop.compose(AreaLayout([lane, c]))
    assert layout(h.coop) == ((a, b), (c,))
    assert_same_objects(members(h.coop), (a, b, c))
    assert h.coop._area_chains[0]._areas is not lane.areas
    assert_same_objects(lane.areas, (a, b))
    lane.areas.reverse()
    lane.areas.append(h.area("declaration-only"))
    h.unfold()
    assert phase_areas(h.events, "tick") == (a, b, c)


def test_compose_empty_layout_is_noop(h: Harness) -> None:
    before = state_snapshot(h.coop)
    h.coop.compose(AreaLayout([]))
    assert state_snapshot(h.coop) == before


def test_same_fields_are_independent_keys_and_hash_survives_retirement(h: Harness) -> None:
    shared_fault = RuntimeError("unused shared fault")
    a, b = h.area("same", fault=shared_fault), h.area("same", fault=shared_fault)
    assert a.__dict__ == b.__dict__
    assert a == a and a != b
    saved_hash = hash(a)
    mapping = {a: "first", b: "second"}
    assert len(mapping) == 2 and len({a, b}) == 2
    h.coop.compose(AreaLayout([a, b]))
    h.unfold()
    a.retire()
    assert hash(a) == saved_hash and mapping[a] == "first"
    h.unfold()
    assert h.coop.fetch_handle(a) is None
    assert h.coop.fetch_handle(b) is not None
    assert (a.gc_count, b.gc_count) == (1, 0)


def test_dataclass_eq_false_inherits_identity_semantics() -> None:
    @dataclass(eq=False)
    class DataArea(Area):
        label: str

        def __post_init__(self) -> None:
            super().__init__(invoke_timing=InvokeTiming.deferrable)

        def tick(self):
            return None

    a, b = DataArea("same"), DataArea("same")
    assert a != b and len({a, b}) == 2
    assert DataArea.__eq__ is Area.__eq__
    assert DataArea.__hash__ is Area.__hash__


def test_structural_protocol_areas_with_colliding_hashes_stay_distinct(h: Harness) -> None:
    a, b = ProtocolArea(), ProtocolArea()
    assert not isinstance(a, Area)
    assert hash(a) == hash(b) and a != b
    h.coop.compose(AreaLayout([a, b]))
    h.unfold()
    assert (a.tick_count, b.tick_count) == (1, 1)
    assert len(h.coop._area_observe_range_mapping) == 2
    assert h.coop.fetch_handle(a)._chain_ref is not h.coop.fetch_handle(b)._chain_ref


@pytest.mark.parametrize("shape", ["raw", "same-lane", "cross-lane", "mixed"])
def test_compose_rejects_duplicates_across_entire_batch_atomically(h: Harness, shape: str) -> None:
    existing = h.area("existing")
    h.coop.append_lane(AreaLane(existing))
    h.unfold()
    a, b = h.area("a"), h.area("b")
    items = {
        "raw": [a, b, a],
        "same-lane": [b, AreaLane(a, a)],
        "cross-lane": [AreaLane(a), AreaLane(b, a)],
        "mixed": [AreaLane(a, b), a],
    }[shape]
    before = state_snapshot(h.coop)
    with pytest.raises(ValueError, match="duplicat|already registered"):
        h.coop.compose(AreaLayout(items))
    assert state_snapshot(h.coop) == before
    assert h.coop.fetch_handle(a) is None


@pytest.mark.parametrize("operation", ["compose", "append", "overlay"])
def test_registered_instance_is_rejected_without_partial_changes(h: Harness, operation: str) -> None:
    existing, fresh = h.area("existing"), h.area("fresh")
    h.coop.append_lane(AreaLane(existing))
    h.unfold()
    before = state_snapshot(h.coop)
    with pytest.raises(ValueError, match="already registered"):
        if operation == "compose":
            h.coop.compose(AreaLayout([fresh, AreaLane(existing)]))
        elif operation == "append":
            h.coop.append_lane(AreaLane(fresh, existing))
        else:
            h.coop.overlay(existing, h.coop.fetch_handle(existing))
    assert state_snapshot(h.coop) == before


@pytest.mark.parametrize("operation", ["compose", "append", "overlay"])
def test_unhashable_area_is_rejected_before_insertion(h: Harness, operation: str) -> None:
    existing, fresh = h.area("existing"), h.area("fresh")
    bad = UnhashableArea()
    h.coop.append_lane(AreaLane(existing))
    h.unfold()
    before = state_snapshot(h.coop)
    with pytest.raises(TypeError, match="hashable"):
        if operation == "compose":
            h.coop.compose(AreaLayout([fresh, AreaLane(bad)]))
        elif operation == "append":
            h.coop.append_lane(AreaLane(fresh, bad))
        else:
            h.coop.overlay(bad, h.coop.fetch_handle(existing))
    assert state_snapshot(h.coop) == before


def test_append_rejects_duplicate_new_instances_atomically(h: Harness) -> None:
    a = h.area("a")
    before = state_snapshot(h.coop)
    with pytest.raises(ValueError, match="duplicat"):
        h.coop.append_lane(AreaLane(a, a))
    assert state_snapshot(h.coop) == before


def test_fetch_handle_is_identity_based_and_missing_returns_none(h: Harness) -> None:
    a, b, c = (h.area(name) for name in "abc")
    h.coop.compose(AreaLayout([AreaLane(a, b), c]))
    first, again, same_lane = (h.coop.fetch_handle(x) for x in (a, a, b))
    assert first._chain_ref is again._chain_ref is same_lane._chain_ref
    assert h.coop.fetch_handle(c)._chain_ref is not first._chain_ref
    assert h.coop.fetch_handle(h.area("a")) is None


def test_foreign_handle_does_not_modify_either_context(h: Harness, gateway) -> None:
    other = Harness(gateway)
    root = other.area("root")
    other.coop.append_lane(AreaLane(root))
    before, foreign_before = state_snapshot(h.coop), state_snapshot(other.coop)
    with pytest.raises(ValueError, match="Handle"):
        h.coop.overlay(h.area("new"), other.coop.fetch_handle(root))
    assert state_snapshot(h.coop) == before
    assert state_snapshot(other.coop) == foreign_before


def test_handle_survives_partial_deletion_then_becomes_stale(h: Harness) -> None:
    a, b = h.area("a"), h.area("b")
    h.coop.append_lane(AreaLane(a, b))
    handle = h.coop.fetch_handle(a)
    a.retire()
    h.unfold()
    assert h.coop.fetch_handle(a) is None
    assert h.coop.fetch_handle(b)._chain_ref is handle._chain_ref
    urgent = h.area("urgent")
    h.coop.overlay(urgent, handle)
    assert layout(h.coop) == ((urgent, b),)
    urgent.retire()
    b.retire()
    h.unfold()
    before = state_snapshot(h.coop)
    with pytest.raises(ValueError, match="Handle"):
        h.coop.overlay(h.area("late"), handle)
    assert state_snapshot(h.coop) == before


def test_collecting_empty_runtime_allows_new_layout(h: Harness) -> None:
    old = h.area("old", steps=[TickStep(retire=True)])
    h.coop.append_lane(AreaLane(old))
    h.unfold()
    h.unfold()
    assert not members(h.coop) and h.coop._cursor_store is None
    new = h.area("new", steps=[TickStep(("new-content",))])
    h.coop.append_lane(AreaLane(new))
    h.unfold()
    assert new.tick_count == 1 and old.gc_count == 1


def test_stack_access_and_reverse_deletion_are_consistent() -> None:
    a, b, c, d = (RecordingArea(name) for name in "abcd")
    chain = _AreaChain(c, b, a)
    assert tuple(chain) == (a, b, c)
    assert chain[0] is a and chain[-1] is c and chain.top() is a
    assert a in chain and RecordingArea("a") not in chain
    chain.push(d)
    assert tuple(chain) == (d, a, b, c)
    del chain[1]
    assert tuple(chain) == (d, b, c)
    chain.pop_top()
    assert tuple(chain) == (b, c)
    del chain[1]
    chain.pop_top()
    chain.pop_top()
    assert chain.is_empty() and len(chain) == 0
    with pytest.raises(RuntimeError, match="Empty"):
        chain.top()
    with pytest.raises(IndexError):
        _ = chain[0]
