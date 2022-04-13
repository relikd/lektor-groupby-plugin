from lektor.context import get_ctx
from typing import TYPE_CHECKING, Iterator
from weakref import WeakSet
if TYPE_CHECKING:
    from lektor.builder import Builder
    from lektor.db import Record
    from .groupby import GroupBy
    from .vobj import GroupBySource


class GroupByRef:
    @staticmethod
    def of(builder: 'Builder') -> 'GroupBy':
        ''' Get the GroupBy object of a builder. '''
        return builder.__groupby  # type:ignore[attr-defined,no-any-return]

    @staticmethod
    def set(builder: 'Builder', groupby: 'GroupBy') -> None:
        ''' Set the GroupBy object of a builder. '''
        builder.__groupby = groupby  # type: ignore[attr-defined]


class VGroups:
    @staticmethod
    def of(record: 'Record') -> WeakSet:
        '''
        Return the (weak) set of virtual objects of a page.
        Creates a new set if it does not exist yet.
        '''
        try:
            wset = record.__vgroups  # type: ignore[attr-defined]
        except AttributeError:
            wset = WeakSet()
            record.__vgroups = wset  # type: ignore[attr-defined]
        return wset  # type: ignore[no-any-return]

    @staticmethod
    def iter(record: 'Record', *keys: str, recursive: bool = False) \
            -> Iterator['GroupBySource']:
        ''' Extract all referencing groupby virtual objects from a page. '''
        ctx = get_ctx()
        if not ctx:
            raise NotImplementedError("Shouldn't happen, where is my context?")
        # get GroupBy object
        builder = ctx.build_state.builder
        groupby = GroupByRef.of(builder)
        groupby.make_once(builder)  # ensure did cluster before
        # manage config dependencies
        for dep in groupby.dependencies:
            ctx.record_dependency(dep)
        # find groups
        proc_list = [record]
        while proc_list:
            page = proc_list.pop(0)
            if recursive and hasattr(page, 'children'):
                proc_list.extend(page.children)  # type: ignore[attr-defined]
            for vobj in VGroups.of(page):
                if not keys or vobj.config.key in keys:
                    yield vobj
