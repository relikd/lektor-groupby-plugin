from lektor.db import Record
from lektor.environment import Environment
from lektor.sourceobj import SourceObject
from lektor.utils import build_url

from typing import Dict, List, Tuple, Optional
from .config import Config  # typing
from .vobj import GroupBySource, VPATH


class Resolver:
    '''
    Resolve virtual paths and urls ending in /.
    Init will subscribe to @urlresolver and @virtualpathresolver.
    '''

    def __init__(self, env: Environment) -> None:
        self._data = {}  # type: Dict[str, Tuple[str, Config]]

        # Local server only: resolve /tag/rss/ -> /tag/rss/index.html
        @env.urlresolver
        def dev_server_path(node: SourceObject, pieces: List[str]) \
                -> Optional[GroupBySource]:
            if isinstance(node, Record):
                rv = self._data.get(build_url([node.url_path] + pieces))
                if rv:
                    return GroupBySource(node, group=rv[0], config=rv[1])
            return None

        # Admin UI only: Prevent server error and null-redirect.
        @env.virtualpathresolver(VPATH.lstrip('@'))
        def virtual_path(node: SourceObject, pieces: List[str]) \
                -> Optional[GroupBySource]:
            if isinstance(node, Record) and len(pieces) >= 2:
                path = node['_path']  # type: str
                key, grp, *_ = pieces
                for group, conf in self._data.values():
                    if key == conf.key and path == conf.root:
                        if conf.slugify(group) == grp:
                            return GroupBySource(node, group, conf)
            return None

    def reset(self) -> None:
        ''' Clear previously recorded virtual objects. '''
        self._data.clear()

    def add(self, vobj: GroupBySource) -> None:
        ''' Track new virtual object (only if slug is set). '''
        if vobj.slug:
            self._data[vobj.url_path] = (vobj.group, vobj.config)
