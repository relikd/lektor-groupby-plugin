from lektor.context import get_ctx
from typing import TYPE_CHECKING, Set, List, Union, Iterable, Iterator
import weakref
from .util import split_strip
if TYPE_CHECKING:
    from lektor.builder import Builder
    from lektor.db import Record
    from .groupby import GroupBy
    from .model import FieldKeyPath
    from .vobj import GroupBySource


class WeakVGroupsList(list):
    def add(self, strong: 'FieldKeyPath', weak: 'GroupBySource') -> None:
        super().append((strong, weakref.ref(weak)))
        # super().append((strong, weak))  # strong-ref


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
    def of(record: 'Record') -> WeakVGroupsList:
        '''
        Return the (weak) set of virtual objects of a page.
        Creates a new set if it does not exist yet.
        '''
        try:
            wset = record.__vgroups  # type: ignore[attr-defined]
        except AttributeError:
            wset = WeakVGroupsList()
            record.__vgroups = wset  # type: ignore[attr-defined]
        return wset  # type: ignore[no-any-return]

    @staticmethod
    def iter(
        record: 'Record',
        keys: Union[str, Iterable[str], None] = None,
        *,
        fields: Union[str, Iterable[str], None] = None,
        flows: Union[str, Iterable[str], None] = None,
        recursive: bool = False,
        order_by: Union[str, Iterable[str], None] = None,
    ) -> Iterator['GroupBySource']:
        ''' Extract all referencing groupby virtual objects from a page. '''
        # prepare filter
        if isinstance(keys, str):
            keys = [keys]
        if isinstance(fields, str):
            fields = [fields]
        if isinstance(flows, str):
            flows = [flows]
        # get GroupBy object
        ctx = get_ctx()
        if not ctx:
            raise NotImplementedError("Shouldn't happen, where is my context?")
        builder = ctx.build_state.builder
        GroupByRef.of(builder).make_once(keys)  # ensure did cluster before use
        # find groups
        proc_list = [record]
        done_list = []  # type: List[GroupBySource]
        while proc_list:
            page = proc_list.pop(0)
            if recursive and hasattr(page, 'children'):
                proc_list.extend(page.children)
            for key, vobj in VGroups.of(page):
                if fields and key.fieldKey not in fields:
                    continue
                if flows and key.flowKey not in flows:
                    continue
                if keys and vobj().config.key not in keys:
                    continue
                done_list.append(vobj())

        # manage config dependencies
        deps = set()  # type: Set[str]
        for vobj in done_list:
            deps.update(vobj.config.dependencies)
            # ctx.record_virtual_dependency(vobj) # TODO: needed? works without
        for dep in deps:
            ctx.record_dependency(dep)

        if order_by:
            if isinstance(order_by, str):
                order = split_strip(order_by, ',')  # type: Iterable[str]
            elif isinstance(order_by, (list, tuple)):
                order = order_by
            else:
                raise AttributeError('order_by must be str or list type.')
            # using get_sort_key() of GroupBySource
            yield from sorted(done_list, key=lambda x: x.get_sort_key(order))
        else:
            yield from done_list
