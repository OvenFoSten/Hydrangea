"""Public-operation sequences checked against a separate lifecycle/message ledger.

The ledger stores declaration order (not reversed stacks) and uses the graph
collector oracle. Allowed promotion tie orders are validated from events before
being accepted as one of the permitted outcomes; candidate order is not copied.
"""

from dataclasses import dataclass

from hypothesis import note, settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from hydrangea.context.area.core import InvokeTiming, LifeState
from hydrangea.context.coop_context import AreaLane, AreaLayout
from hydrangea.gateway import GatewayType

from .helpers import Harness, RecordingArea, TickStep, assert_same_objects, texts
from .oracle import expected_collection


TIMINGS = st.sampled_from([InvokeTiming.deferrable, InvokeTiming.immediate])
SPEC = st.tuples(st.integers(0, 2), TIMINGS, st.integers(0, 2))
LANE_SPEC = st.lists(SPEC, min_size=1, max_size=3)


@dataclass
class ModelArea:
    actual: RecordingArea
    timing: InvokeTiming
    emit_count: int
    promotions: tuple[str, ...]
    retired: bool = False
    collected: bool = False
    effect: tuple[int, int] | None = None
    observe: tuple[int, int] | None = None
    ticks: int = 0
    observations: int = 0
    promotes: int = 0
    gcs: int = 0
    next_timing: InvokeTiming | None = None
    observe_timing: InvokeTiming | None = None
    retire_on_tick: bool = False
    retire_on_observe: bool = False


@dataclass(eq=False)
class ModelLane:
    keys: list[int]
    actual_chain: object


class CoopMachine(RuleBasedStateMachine):
    gateway = GatewayType.openai

    def __init__(self) -> None:
        super().__init__()
        self.h = Harness(self.gateway)
        self.areas: dict[int, ModelArea] = {}
        self.key_by_area: dict[RecordingArea, int] = {}
        self.lanes: list[ModelLane] = []
        self.cursor: ModelLane | None = None
        self.content: list[str] = []
        self.garbage: list[str] = []
        self.garbage_native = []
        self.reply_count = 0
        self.trace: list[str] = []
        self.failed = False

    def registered(self) -> list[int]:
        return [key for lane in self.lanes for key in lane.keys]

    def live(self) -> list[int]:
        return [key for key in self.registered() if not self.areas[key].retired]

    def _new(self, spec) -> int:
        emit_count, timing, promotion_count = spec
        key = len(self.areas)
        promotions = tuple(f"promote-{key}-{i}" for i in range(promotion_count))
        area = self.h.area(f"area-{key}", timing=timing, promotions=promotions)
        self.areas[key] = ModelArea(area, timing, emit_count, promotions)
        self.key_by_area[area] = key
        return key

    @precondition(lambda self: len(self.areas) < 24)
    @rule(specs=LANE_SPEC)
    def append_lane(self, specs) -> None:
        keys = [self._new(spec) for spec in specs]
        self.h.coop.append_lane(AreaLane(*(self.areas[key].actual for key in keys)))
        chain = self.h.coop.fetch_handle(self.areas[keys[0]].actual)._chain_ref
        self.lanes.append(ModelLane(keys, chain))
        self.trace.append(f"append {keys}: {specs!r}")

    @precondition(lambda self: len(self.areas) < 24)
    @rule(groups=st.lists(LANE_SPEC, min_size=0, max_size=3))
    def compose(self, groups) -> None:
        key_groups = [[self._new(spec) for spec in specs] for specs in groups]
        items = [self.areas[keys[0]].actual if len(keys) == 1 else AreaLane(*(self.areas[k].actual for k in keys)) for keys in key_groups]
        self.h.coop.compose(AreaLayout(items))
        for keys in key_groups:
            chain = self.h.coop.fetch_handle(self.areas[keys[0]].actual)._chain_ref
            self.lanes.append(ModelLane(keys, chain))
        self.trace.append(f"compose {key_groups}: {groups!r}")

    @precondition(lambda self: bool(self.lanes) and len(self.areas) < 24)
    @rule(selector=st.integers(0, 1000), spec=SPEC)
    def overlay(self, selector: int, spec) -> None:
        lane = self.lanes[selector % len(self.lanes)]
        handle = self.h.coop.fetch_handle(self.areas[lane.keys[0]].actual)
        key = self._new(spec)
        self.h.coop.overlay(self.areas[key].actual, handle)
        lane.keys.insert(0, key)
        self.trace.append(f"overlay {key} into {lane.keys}: {spec!r}")

    @rule()
    def model_reply(self) -> None:
        value = f"reply-{self.reply_count}"
        self.reply_count += 1
        self.h.reply(value)
        self.content.append(value)
        self.trace.append(value)

    @precondition(lambda self: bool(self.live()))
    @rule(selector=st.integers(0, 1000))
    def retire_at_boundary(self, selector: int) -> None:
        choices = self.live()
        key = choices[selector % len(choices)]
        self.areas[key].retired = True
        self.areas[key].actual.retire()
        self.trace.append(f"retire {key}")

    @precondition(lambda self: bool(self.live()))
    @rule(
        selector=st.integers(0, 1000), timing=TIMINGS,
        next_timing=st.one_of(st.none(), TIMINGS),
        observe_timing=st.one_of(st.none(), TIMINGS),
        emit_count=st.integers(0, 2), retire_tick=st.booleans(), retire_observe=st.booleans(),
    )
    def configure_at_boundary(self, selector, timing, next_timing, observe_timing, emit_count, retire_tick, retire_observe) -> None:
        choices = self.live()
        key = choices[selector % len(choices)]
        model = self.areas[key]
        model.timing = timing
        model.next_timing = next_timing
        model.observe_timing = observe_timing
        model.emit_count = emit_count
        model.retire_on_tick = retire_tick
        model.retire_on_observe = retire_observe
        model.actual.set_timing(timing)
        self.trace.append(f"configure {key}: {(timing, next_timing, observe_timing, emit_count, retire_tick, retire_observe)!r}")

    @rule()
    def unfold(self) -> None:
        try:
            self._unfold_and_compare()
        except Exception:
            self.failed = True
            raise

    def _unfold_and_compare(self) -> None:
        note("\n".join(self.trace))
        old_registered = set(self.registered())
        retired = {key for key in old_registered if self.areas[key].retired}
        effects = {key: self.areas[key].effect for key in old_registered if self.areas[key].effect is not None}
        observes = {key: self.areas[key].observe for key in old_registered if self.areas[key].observe is not None}
        collected, earliest = expected_collection(old_registered, retired, effects, observes)

        # Cursor repair is specified as the first runnable lane in cyclic
        # declaration order, independent of the production reversed stack.
        if self.lanes:
            begin = self.lanes.index(self.cursor) if self.cursor is not None else 0
            cyclic = self.lanes[begin:] + self.lanes[:begin]
            self.cursor = next((lane for lane in cyclic if any(not self.areas[k].retired for k in lane.keys)), None)
        else:
            self.cursor = None

        for key in old_registered - retired:
            model = self.areas[key]
            output = tuple(f"emit-{key}-{model.ticks + 1}-{j}" for j in range(model.emit_count)) or None
            model.actual.default = TickStep(output, model.next_timing, model.retire_on_tick)
            timing, retire = model.observe_timing, model.retire_on_observe

            def on_observe(area, _snapshot, timing=timing, retire=retire):
                if timing is not None:
                    area.set_timing(timing)
                if retire:
                    area.retire()

            model.actual.on_observe = on_observe

        before_native = self.h.context[:]
        event_start = len(self.h.events)
        self.h.unfold()
        events = self.h.events[event_start:]
        trace_events = [(e.phase, self.key_by_area[e.area]) for e in events]
        note(f"expected collected={collected}, earliest={earliest}; actual events={trace_events}")
        self.trace.append(f"unfold -> {trace_events}")

        gc_order = [self.key_by_area[e.area] for e in events if e.phase == "gc"]
        promote_order = [self.key_by_area[e.area] for e in events if e.phase == "promote"]
        assert set(gc_order) == collected and len(gc_order) == len(collected)
        touched = collected & (effects.keys() | observes.keys())
        assert set(promote_order) == touched and len(promote_order) == len(touched)
        stamps = {key: effects[key][1] if key in effects else observes[key][1] for key in touched}
        assert [stamps[key] for key in promote_order] == sorted(stamps[key] for key in touched)
        for key in touched:
            phases = [phase for phase, event_key in trace_events if event_key == key]
            assert phases == ["promote", "gc"]

        keep = len(self.content) if earliest is None else earliest
        self.garbage.extend(self.content[keep:])
        self.garbage_native.extend(before_native[keep:])
        self.content = self.content[:keep]
        for key in promote_order:
            self.content.extend(self.areas[key].promotions)
            self.areas[key].promotes += 1
        for key in collected:
            self.areas[key].collected = True
            self.areas[key].gcs += 1
        for lane in self.lanes:
            lane.keys[:] = [key for key in lane.keys if key not in collected]
        self.lanes[:] = [lane for lane in self.lanes if lane.keys]
        assert_same_objects(self.h.context[:keep], before_native[:keep])
        assert_same_objects(self.h.coop.garbage, self.garbage_native)

        expected_observers = []
        for key in self.registered():
            model = self.areas[key]
            if model.retired or model.observe is None:
                continue
            expected_observers.append(key)
            start, _ = model.observe
            model.observe = (start, len(self.content) - 1)
            assert texts(model.actual.snapshots[-1]) == tuple(self.content[start:])
            model.observations += 1
            if model.observe_timing is not None:
                model.timing = model.observe_timing
            if model.retire_on_observe:
                model.retired = True
        assert [self.key_by_area[e.area] for e in events if e.phase == "observe"] == expected_observers

        expected_ticks = []
        next_cursor = self.cursor
        if self.lanes:
            assert self.cursor in self.lanes
            begin = self.lanes.index(self.cursor)
            traversal = [(lane, key) for lane in self.lanes[begin:] + self.lanes[:begin] for key in lane.keys if not self.areas[key].retired]
            for lane, key in traversal:
                expected_ticks.append(key)
                if self.areas[key].timing is InvokeTiming.immediate:
                    next_cursor = lane
                    break
        assert [self.key_by_area[e.area] for e in events if e.phase == "tick"] == expected_ticks

        for key in expected_ticks:
            model = self.areas[key]
            model.ticks += 1
            start = len(self.content)
            output = tuple(f"emit-{key}-{model.ticks}-{j}" for j in range(model.emit_count))
            if output:
                first = model.effect[0] if model.effect is not None else start
                model.effect = (first, start + len(output) - 1)
                self.content.extend(output)
            if model.observe is None:
                model.observe = (start, start)
            if model.next_timing is not None:
                model.timing = model.next_timing
            if model.retire_on_tick:
                model.retired = True
        self.cursor = next_cursor
        self._assert_consistent()

    @invariant()
    def state_matches_independent_ledger(self) -> None:
        try:
            self._assert_consistent()
        except Exception:
            self.failed = True
            raise

    def _assert_consistent(self) -> None:
        actual_layout = tuple(tuple(self.key_by_area[a] for a in chain) for chain in self.h.coop._area_chains)
        assert actual_layout == tuple(tuple(lane.keys) for lane in self.lanes)
        assert self.h.coop._cursor_store is (self.cursor.actual_chain if self.cursor is not None else None)
        assert texts(self.h.context[:]) == tuple(self.content)
        assert texts(self.h.coop.garbage) == tuple(self.garbage)
        registered = set(self.registered())
        expected_effects = {key: self.areas[key].effect for key in registered if self.areas[key].effect is not None}
        expected_observes = {key: self.areas[key].observe for key in registered if self.areas[key].observe is not None}
        assert {self.key_by_area[a]: (r.start, r.latest) for a, r in self.h.coop._area_effect_range_mapping.items()} == expected_effects
        assert {self.key_by_area[a]: (r.start, r.latest) for a, r in self.h.coop._area_observe_range_mapping.items()} == expected_observes
        for key, model in self.areas.items():
            area = model.actual
            assert (area.tick_count, area.observe_count, area.promote_count, area.gc_count) == (model.ticks, model.observations, model.promotes, model.gcs)
            assert area.resource_open == (not model.collected)
            assert (area.life_state is LifeState.retired) == model.retired
            assert area.invoke_timing is model.timing
            assert (self.h.coop.fetch_handle(area) is not None) == (key in registered)

    def teardown(self) -> None:
        if self.failed:
            # Keep the original failure: recovery after a failed unfold is not
            # a contract and teardown must not obscure its minimal example.
            return
        for key in self.registered():
            self.areas[key].retired = True
            self.areas[key].actual.retire()
        self._unfold_and_compare()
        assert not self.lanes
        assert all(model.gcs == 1 for model in self.areas.values())


class GeminiMachine(CoopMachine):
    gateway = GatewayType.gemini


class OpenAIMachine(CoopMachine):
    gateway = GatewayType.openai


TestGeminiCoop = GeminiMachine.TestCase
TestOpenAICoop = OpenAIMachine.TestCase
TestGeminiCoop.settings = settings(max_examples=100, stateful_step_count=50, deadline=None, derandomize=True, database=None)
TestOpenAICoop.settings = settings(max_examples=100, stateful_step_count=50, deadline=None, derandomize=True, database=None)
