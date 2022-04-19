from lektor.db import Record  # isinstance
from lektor.utils import build_url
from typing import TYPE_CHECKING, Dict, List, Tuple, Optional, Iterable
from .vobj import VPATH, GroupBySource
if TYPE_CHECKING:
    from lektor.environment import Environment
    from lektor.sourceobj import SourceObject
    from .config import Config


class Resolver:
    '''
    Resolve virtual paths and urls ending in /.
    Init will subscribe to @urlresolver and @virtualpathresolver.
    '''

    def __init__(self, env: 'Environment') -> None:
        self._data = {}  # type: Dict[str, Tuple[str, str, Config]]
        env.urlresolver(self.resolve_server_path)
        env.virtualpathresolver(VPATH.lstrip('@'))(self.resolve_virtual_path)

    @property
    def has_any(self) -> bool:
        return bool(self._data)

    @property
    def files(self) -> Iterable[str]:
        return self._data

    def reset(self) -> None:
        ''' Clear previously recorded virtual objects. '''
        self._data.clear()

    def add(self, vobj: GroupBySource) -> None:
        ''' Track new virtual object (only if slug is set). '''
        if vobj.slug:
            self._data[vobj.url_path] = (vobj.key, vobj.group, vobj.config)

    # ------------
    #   Resolver
    # ------------

    def resolve_server_path(self, node: 'SourceObject', pieces: List[str]) \
            -> Optional[GroupBySource]:
        ''' Local server only: resolve /tag/rss/ -> /tag/rss/index.html '''
        if isinstance(node, Record):
            rv = self._data.get(build_url([node.url_path] + pieces))
            if rv:
                return GroupBySource(node, rv[0]).finalize(rv[2], rv[1])
        return None

    def resolve_virtual_path(self, node: 'SourceObject', pieces: List[str]) \
            -> Optional[GroupBySource]:
        ''' Admin UI only: Prevent server error and null-redirect. '''
        if isinstance(node, Record) and len(pieces) >= 2:
            path = node['_path']  # type: str
            attr, grp, *_ = pieces
            for slug, group, conf in self._data.values():
                if attr == conf.key and slug == grp and path == conf.root:
                    return GroupBySource(node, slug).finalize(conf, group)
        return None
