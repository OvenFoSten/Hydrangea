from typing import NewType
from dataclasses import dataclass

from typing_extensions import assert_never

from .area import ContextAreaImplementation,AreaLifeState,AreaFlowState
from .core import Context, NativeContent
from ..message import Message

ContextIndex = NewType("ContextIndex",int)

@dataclass(slots=True)
class _EffectRange:
    earliest: ContextIndex
    latest: ContextIndex

@dataclass(frozen=True,slots=True)
class _CollectionPlan:
    earliest: ContextIndex
    expected_context_size: int
    areas: tuple[ContextAreaImplementation,...]

class CoopContext:
    _context:Context
    garbage:list[NativeContent]

    _areas:list[ContextAreaImplementation]
    _area_mapping:dict[ContextAreaImplementation,_EffectRange]
    _area_cursor_store:ContextAreaImplementation|None

    def __init__(self,context:Context):
        self._context = context
        self.garbage = list()

        self._areas = list()
        self._area_mapping = dict()

        self._area_cursor_store = None

    def register(self,area:ContextAreaImplementation)->None:
        self._areas.append(area)

    def _collect(self)->_CollectionPlan|None:
        if not self._area_mapping:
            return None

        context_size = len(self._context)
        ordered_areas = sorted(
            self._area_mapping,
            key=lambda area: self._area_mapping[area].latest,
            reverse=True,
        )

        for area in ordered_areas:
            effect_range = self._area_mapping[area]
            if (
                effect_range.earliest < 0
                or effect_range.latest < effect_range.earliest
                or effect_range.latest >= context_size
            ):
                raise RuntimeError(
                    "EffectRange is outside Context: "
                    f"[{effect_range.earliest}, {effect_range.latest}], "
                    f"context_size={context_size}."
                )

        tail_area = ordered_areas[0]
        tail_effect_range = self._area_mapping[tail_area]
        component_earliest = tail_effect_range.earliest
        component: list[ContextAreaImplementation] = []

        for area in ordered_areas:
            effect_range = self._area_mapping[area]
            if effect_range.latest < component_earliest:
                break

            match area.life_state:
                case AreaLifeState.retain:
                    return None

                case AreaLifeState.retired:
                    component.append(area)

                case _:
                    assert_never(area.life_state)

            if effect_range.earliest < component_earliest:
                component_earliest = effect_range.earliest

        return _CollectionPlan(
            earliest=component_earliest,
            expected_context_size=context_size,
            areas=tuple(component),
        )

    def _cursor_after_collection(
        self,
        areas_to_collect:set[ContextAreaImplementation],
    )->ContextAreaImplementation|None:
        current_area = self._area_cursor_store
        if current_area is None:
            return None

        if current_area not in self._areas:
            raise RuntimeError(
                "Current Area is missing from CoopContext."
            )

        if current_area not in areas_to_collect:
            return current_area

        current_index = self._areas.index(current_area)
        area_count = len(self._areas)
        for offset in range(1,area_count+1):
            candidate = self._areas[
                (current_index+offset)%area_count
            ]
            if candidate not in areas_to_collect:
                return candidate

        return None

    def _gc(self,plan:_CollectionPlan)->None:
        if plan.expected_context_size != len(self._context):
            raise RuntimeError("Unexpected context change between collector and gc.")

        areas_to_collect = set(plan.areas)
        for area in plan.areas:
            if area not in self._areas:
                raise RuntimeError(
                    "Collected Area is missing from CoopContext."
                )
            if area not in self._area_mapping:
                raise RuntimeError(
                    "Collected Area is missing from the working set."
                )

        next_cursor = self._cursor_after_collection(
            areas_to_collect
        )

        # 1. Collect Promote
        promotes:list[Message] = list()
        for area in reversed(plan.areas):
            promotes.extend(area.promote())
        # 2. GC
        for area in reversed(plan.areas):
            area.gc_prologue()

        tail_length = (
            plan.expected_context_size
            - int(plan.earliest)
        )
        detached = self._context.detach_tail(
            length=tail_length
        )
        self.garbage.extend(detached)

        for area in plan.areas:
            _ = self._area_mapping.pop(area)

        self._areas[:] = [
            area
            for area in self._areas
            if area not in areas_to_collect
        ]
        self._area_cursor_store = next_cursor

        # 3. emplace promotes
        for promote in promotes:
            self._context.emplace_message(promote)


    def advance(self)->Context:
        if not self._areas:
            return self._context

        # 1. Collect & GC
        plan = self._collect()
        if plan is not None:
            self._gc(plan)

        if not self._areas:
            self._area_cursor_store = None
            return self._context

        if self._area_cursor_store is None:
            self._area_cursor_store = self._areas[0]

        # 3. Unfold
        area_count = len(self._areas)
        visited:int = 0
        area_cursor_index = self._areas.index(self._area_cursor_store)
        while(visited<area_count):
            visited += 1
            area_cursor = self._areas[area_cursor_index]
            # Single round till find lifestate = retain
            area_life_state:AreaLifeState = area_cursor.life_state
            if(area_life_state != AreaLifeState.retain):
                area_cursor_index = (area_cursor_index+1)%area_count
                continue

            effect_range = self._area_mapping.get(area_cursor)
            if effect_range is not None:
                context_slice = self._context[
                    int(effect_range.earliest):
                    int(effect_range.latest) + 1
                ]
                area_cursor.observe(context_slice)

                area_life_state = area_cursor.life_state
                if area_life_state is AreaLifeState.retired:
                    area_cursor_index = (
                        area_cursor_index + 1
                    ) % area_count
                    continue

            # Render Content
            content = area_cursor.advance()
            if content:
                # Calc Effect Range
                effect_start = ContextIndex(len(self._context))
                effect_end = ContextIndex(effect_start+len(content)-1)
                # Emplace Context
                for msg in content:
                    self._context.emplace_message(msg)
                # Remember Effect Range
                if self._area_mapping.get(area_cursor) is None:
                    self._area_mapping[area_cursor]=_EffectRange(earliest=effect_start,latest=effect_end)
                else:
                    self._area_mapping[area_cursor].latest = effect_end
            # Move Cursor Index
            match area_cursor.flow_state:
                case AreaFlowState.exclusive:
                    self._area_cursor_store = area_cursor
                    return self._context
                case AreaFlowState.yielded:
                    area_cursor_index = (area_cursor_index + 1)%area_count
                case _:
                    assert_never(area_cursor.flow_state)

        # 4. Store Cursor
        self._area_cursor_store = self._areas[area_cursor_index]
        # 5. Return Context
        return self._context
