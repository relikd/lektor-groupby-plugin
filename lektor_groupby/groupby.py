from lektor.builder import PathCache
from lektor.db import Record  # isinstance
from lektor.reporter import reporter  # build
from typing import TYPE_CHECKING, List, Optional, Iterable
from .config import Config
from .watcher import Watcher
if TYPE_CHECKING:
    from lektor.builder import Builder
    from lektor.sourceobj import SourceObject
    from .config import AnyConfig
    from .resolver import Resolver
    from .vobj import GroupBySource


class GroupBy:
    '''
    Process all children with matching conditions under specified page.
    Creates a grouping of pages with similar (self-defined) attributes.
    The grouping is performed only once per build.
    '''

    def __init__(self, resolver: 'Resolver') -> None:
        self._building = False
        self._watcher = []  # type: List[Watcher]
        self._results = []  # type: List[GroupBySource]
        self._pre_build_priority = []  # type: List[str]  # config.key
        self.resolver = resolver

    @property
    def isBuilding(self) -> bool:
        return self._building

    def add_watcher(
        self, key: str, config: 'AnyConfig', *, pre_build: bool = False
    ) -> Watcher:
        ''' Init Config and add to watch list. '''
        w = Watcher(Config.from_any(key, config))
        self._watcher.append(w)
        if pre_build:
            self._pre_build_priority.append(w.config.key)
        return w

    def queue_all(self, builder: 'Builder') -> None:
        ''' Iterate full site-tree and queue all children. '''
        # remove disabled watchers
        self._watcher = [w for w in self._watcher if w.config.enabled]
        if not self._watcher:
            return
        # initialize remaining (enabled) watchers
        for w in self._watcher:
            w.initialize(builder.pad)
        # iterate over whole build tree
        queue = builder.pad.get_all_roots()  # type: List[SourceObject]
        while queue:
            record = queue.pop()
            if hasattr(record, 'attachments'):
                queue.extend(record.attachments)
            if hasattr(record, 'children'):
                queue.extend(record.children)
            if isinstance(record, Record):
                for w in self._watcher:
                    if w.should_process(record):
                        w.remember(record)
        # build sources which need building before actual lektor build
        if self._pre_build_priority:
            self.make_once(self._pre_build_priority)
            self._pre_build_priority.clear()

    def make_once(self, filter_keys: Optional[Iterable[str]] = None) -> None:
        '''
        Perform groupby, iter over sources with watcher callback.
        If `filter_keys` is set, ignore all other watchers.
        '''
        if not self._watcher:
            return
        remaining = []
        for w in self._watcher:
            # only process vobjs that are used somewhere
            if filter_keys and w.config.key not in filter_keys:
                remaining.append(w)
                continue
            self.resolver.reset(w.config.key)
            # these are used in the current context (or on `build_all`)
            for vobj in w.iter_sources():
                # add original source
                self._results.append(vobj)
                self.resolver.add(vobj)
                # and also add pagination sources
                for sub_vobj in vobj.__iter_pagination_sources__():
                    self._results.append(sub_vobj)
                    self.resolver.add(sub_vobj)
        # TODO: if this should ever run concurrently, pop() from watchers
        self._watcher = remaining

    def build_all(
        self,
        builder: 'Builder',
        specific: Optional['GroupBySource'] = None
    ) -> None:
        '''
        Build actual artifacts (if needed).
        If `specific` is set, only build the artifacts for that single vobj
        '''
        if not self._watcher and not self._results:
            return
        with reporter.build('groupby', builder):  # type:ignore
            # in case no page used the |vgroups filter
            self.make_once([specific.config.key] if specific else None)
            self._building = True
            path_cache = PathCache(builder.env)
            for vobj in self._results:
                if specific and vobj.path != specific.path:
                    continue
                if vobj.slug:
                    builder.build(vobj, path_cache)
            del path_cache
            self._building = False
            self._results.clear()  # garbage collect weak refs
