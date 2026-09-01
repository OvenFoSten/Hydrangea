from typing import NewType
from dataclasses import dataclass

from typing_extensions import assert_never

from hydrangea.context.area.core import LifeState

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

    def _gc(self,plan:_CollectionPlan)->None:        
        if plan.expected_context_size != len(self._context):
            raise RuntimeError("Unexpected context change between collector and gc.")

        # 0. Repair Cursor
        if not self._area_cursor_store:
            return
        if self._area_cursor_store.life_state == LifeState.retired:
            cursor_index = self._areas.index(self._area_cursor_store)
            area_length = len(self._areas)
            visited:int = 0
            while self._areas[cursor_index].life_state == LifeState.retired and visited<area_length:
                visited+=1
                cursor_index = (cursor_index+1)%area_length
                self._area_cursor_store = self._areas[cursor_index]

        # 1. Collect Promote
        promotes:list[Message] = list()
        for area in reversed(plan.areas):
            promotes.extend(area.promote())
        # 2. GC
        for area in reversed(plan.areas):
            area.gc_prologue()
            self._areas.remove(area)
            _ = self._area_mapping.pop(area)
        
        self.garbage.extend(self._context.detach_tail(
            plan.expected_context_size-plan.earliest))
        # 3. emplace promotes
        for promote in promotes:
            self._context.emplace_message(promote)


    def render(self)->Context:
        if not self._areas:
            return self._context
        
        if self._area_cursor_store is None:
            self._area_cursor_store = self._areas[0]
        
        # 1. Collect & GC
        plan = self._collect()
        if plan:
            self._gc(plan)

        # 3. Unfold
        area_count = len(self._areas)
        visited:int = 0
        area_cursor_index = self._areas.index(self._area_cursor_store)
        while(visited<area_count):
            visited += 1
            area_cursor = self._areas[area_cursor_index]
            # Single round till find lifestate = retain
            if(area_cursor.life_state != AreaLifeState.retain):
                area_cursor_index = (area_cursor_index+1)%area_count
                continue

            # Render Content
            content = area_cursor.render()
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




        


        




        
        
        
        