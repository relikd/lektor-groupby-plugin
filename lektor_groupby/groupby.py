from lektor.builder import Builder, PathCache
from lektor.db import Record
from lektor.sourceobj import SourceObject
from lektor.utils import build_url

from typing import Set, Dict, List, Optional, Tuple
from .vobj import GroupBySource, GroupKey
from .config import Config, ConfigKey, AnyConfig
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
        self._resolver = {}  # type: Dict[str, Tuple[GroupKey, Config]]

    # ----------------
    #   Add observer
    # ----------------

    def add_watcher(self, key: ConfigKey, config: AnyConfig) -> Watcher:
        ''' Init Config and add to watch list. '''
        w = Watcher(Config.from_any(key, config))
        self._watcher.append(w)
        return w

    # -----------
    #   Builder
    # -----------

    def clear_previous_results(self) -> None:
        ''' Reset prvious results. Must be called before each build. '''
        self._watcher.clear()
        self._results.clear()
        self._resolver.clear()

    def get_dependencies(self) -> Set[str]:
        deps = set()  # type: Set[str]
        for w in self._watcher:
            deps.update(w.config.dependencies)
        return deps

    def make_cluster(self, builder: Builder) -> None:
        ''' Iterate over all children and perform groupby. '''
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
        # build artifacts
        for w in self._watcher:
            root = builder.pad.get(w.config.root)
            for vobj in w.iter_sources(root):
                self._results.append(vobj)
                if vobj.slug:
                    self._resolver[vobj.url_path] = (vobj.group, w.config)
        self._watcher.clear()

    def queue_now(self, node: SourceObject) -> None:
        ''' Process record immediatelly (No-Op if already processed). '''
        if isinstance(node, Record):
            for w in self._watcher:
                if w.should_process(node):
                    w.process(node)

    def build_all(self, builder: Builder) -> None:
        ''' Create virtual objects and build sources. '''
        path_cache = PathCache(builder.env)
        for vobj in self._results:
            if vobj.slug:
                builder.build(vobj, path_cache)
        del path_cache
        self._results.clear()  # garbage collect weak refs

    # -----------------
    #   Path resolver
    # -----------------

    def resolve_dev_server_path(self, node: SourceObject, pieces: List[str]) \
            -> Optional[GroupBySource]:
        ''' Dev server only: Resolves path/ -> path/index.html '''
        if isinstance(node, Record):
            rv = self._resolver.get(build_url([node.url_path] + pieces))
            if rv:
                return GroupBySource(node, group=rv[0], config=rv[1])
        return None

    def resolve_virtual_path(self, node: SourceObject, pieces: List[str]) \
            -> Optional[GroupBySource]:
        ''' Admin UI only: Prevent server error and null-redirect. '''
        if isinstance(node, Record) and len(pieces) >= 2:
            path = node['_path']  # type: str
            key, grp, *_ = pieces
            for group, conf in self._resolver.values():
                if key == conf.key and path == conf.root:
                    if conf.slugify(group) == grp:
                        return GroupBySource(node, group, conf)
        return None
