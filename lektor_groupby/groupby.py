from lektor.builder import PathCache
from lektor.db import Record  # isinstance
from typing import TYPE_CHECKING, Set, List
from .config import Config
from .watcher import Watcher
if TYPE_CHECKING:
    from .config import AnyConfig
    from lektor.builder import Builder
    from lektor.sourceobj import SourceObject
    from .resolver import Resolver
    from .vobj import GroupBySource


class GroupBy:
    '''
    Process all children with matching conditions under specified page.
    Creates a grouping of pages with similar (self-defined) attributes.
    The grouping is performed only once per build.
    '''

    def __init__(self, resolver: 'Resolver') -> None:
        self._watcher = []  # type: List[Watcher]
        self._results = []  # type: List[GroupBySource]
        self.resolver = resolver

    def add_watcher(self, key: str, config: 'AnyConfig') -> Watcher:
        ''' Init Config and add to watch list. '''
        w = Watcher(Config.from_any(key, config))
        self._watcher.append(w)
        return w

    def get_dependencies(self) -> Set[str]:
        deps = set()  # type: Set[str]
        for w in self._watcher:
            deps.update(w.config.dependencies)
        return deps

    def queue_all(self, builder: 'Builder') -> None:
        ''' Iterate full site-tree and queue all children. '''
        self.dependencies = self.get_dependencies()
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
                queue.extend(record.attachments)  # type: ignore[attr-defined]
            if hasattr(record, 'children'):
                queue.extend(record.children)  # type: ignore[attr-defined]
            if isinstance(record, Record):
                for w in self._watcher:
                    if w.should_process(record):
                        w.process(record)

    def make_once(self, builder: 'Builder') -> None:
        ''' Perform groupby, iter over sources with watcher callback. '''
        if self._watcher:
            self.resolver.reset()
            for w in self._watcher:
                root = builder.pad.get(w.config.root)
                for vobj in w.iter_sources(root):
                    self._results.append(vobj)
                    self.resolver.add(vobj)
            self._watcher.clear()

    def build_all(self, builder: 'Builder') -> None:
        ''' Create virtual objects and build sources. '''
        self.make_once(builder)  # in case no page used the |vgroups filter
        path_cache = PathCache(builder.env)
        for vobj in self._results:
            if vobj.slug:
                builder.build(vobj, path_cache)
        del path_cache
        self._results.clear()  # garbage collect weak refs
