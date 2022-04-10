from lektor.builder import Builder, PathCache
from lektor.db import Record  # typing
from lektor.sourceobj import SourceObject  # typing

from typing import Set, List
from .vobj import GroupBySource  # typing
from .config import Config, AnyConfig
from .resolver import Resolver  # typing
from .watcher import Watcher


class GroupBy:
    '''
    Process all children with matching conditions under specified page.
    Creates a grouping of pages with similar (self-defined) attributes.
    The grouping is performed only once per build.
    '''

    def __init__(self) -> None:
        self._watcher = []  # type: List[Watcher]
        self._results = []  # type: List[GroupBySource]

    def add_watcher(self, key: str, config: AnyConfig) -> Watcher:
        ''' Init Config and add to watch list. '''
        w = Watcher(Config.from_any(key, config))
        self._watcher.append(w)
        return w

    def get_dependencies(self) -> Set[str]:
        deps = set()  # type: Set[str]
        for w in self._watcher:
            deps.update(w.config.dependencies)
        return deps

    def queue_all(self, builder: Builder) -> None:
        ''' Iterate full site-tree and queue all children. '''
        # remove disabled watchers
        self._watcher = [w for w in self._watcher if w.config.enabled]
        if not self._watcher:
            return
        # initialize remaining (enabled) watchers
        for w in self._watcher:
            w.initialize(builder.pad.db)
        # iterate over whole build tree
        queue = builder.pad.get_all_roots()  # type: List[SourceObject]
        while queue:
            record = queue.pop()
            self.queue_now(record)
            if hasattr(record, 'attachments'):
                queue.extend(record.attachments)  # type: ignore[attr-defined]
            if hasattr(record, 'children'):
                queue.extend(record.children)  # type: ignore[attr-defined]

    def queue_now(self, node: SourceObject) -> None:
        ''' Process record immediatelly (No-Op if already processed). '''
        if isinstance(node, Record):
            for w in self._watcher:
                if w.should_process(node):
                    w.process(node)

    def make_cluster(self, builder: Builder, resolver: Resolver) -> None:
        ''' Perform groupby, iter over sources with watcher callback. '''
        for w in self._watcher:
            root = builder.pad.get(w.config.root)
            for vobj in w.iter_sources(root):
                self._results.append(vobj)
                resolver.add(vobj)
        self._watcher.clear()

    def build_all(self, builder: Builder) -> None:
        ''' Create virtual objects and build sources. '''
        path_cache = PathCache(builder.env)
        for vobj in self._results:
            if vobj.slug:
                builder.build(vobj, path_cache)
        del path_cache
        self._results.clear()  # garbage collect weak refs
