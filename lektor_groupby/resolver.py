from lektor.db import Page  # isinstance
from typing import (
    TYPE_CHECKING, NamedTuple, Dict, List, Any, Optional, Iterable
)
from .util import build_url
from .vobj import VPATH, GroupBySource
if TYPE_CHECKING:
    from lektor.environment import Environment
    from lektor.sourceobj import SourceObject
    from .config import Config


class ResolverEntry(NamedTuple):
    key: str
    key_obj: Any
    config: 'Config'
    page: Optional[int]

    def equals(
        self, path: str, conf_key: str, vobj_key: str, page: Optional[int]
    ) -> bool:
        return self.key == vobj_key \
            and self.config.key == conf_key \
            and self.config.root == path \
            and self.page == page


class Resolver:
    '''
    Resolve virtual paths and urls ending in /.
    Init will subscribe to @urlresolver and @virtualpathresolver.
    '''

    def __init__(self, env: 'Environment') -> None:
        self._data = {}  # type: Dict[str, ResolverEntry]
        env.urlresolver(self.resolve_server_path)
        env.virtualpathresolver(VPATH.lstrip('@'))(self.resolve_virtual_path)

    @property
    def has_any(self) -> bool:
        return bool(self._data)

    @property
    def files(self) -> Iterable[str]:
        return self._data

    def reset(self, optional_key: Optional[str] = None) -> None:
        ''' Clear previously recorded virtual objects. '''
        if optional_key:
            self._data = {k: v for k, v in self._data.items()
                          if v.config.key != optional_key}
        else:
            self._data.clear()

    def add(self, vobj: GroupBySource) -> None:
        ''' Track new virtual object (only if slug is set). '''
        if vobj.slug:
            # `page_num = 1` overwrites `page_num = None` -> same url_path()
            self._data[vobj.url_path] = ResolverEntry(
                vobj.key, vobj.key_obj, vobj.config, vobj.page_num)

    # ------------
    #   Resolver
    # ------------

    def resolve_server_path(self, node: 'SourceObject', pieces: List[str]) \
            -> Optional[GroupBySource]:
        ''' Local server only: resolve /tag/rss/ -> /tag/rss/index.html '''
        if isinstance(node, Page):
            rv = self._data.get(build_url([node.url_path] + pieces))
            if rv:
                return GroupBySource(
                    node, rv.key, rv.page).finalize(rv.config, rv.key_obj)
        return None

    def resolve_virtual_path(self, node: 'SourceObject', pieces: List[str]) \
            -> Optional[GroupBySource]:
        ''' Admin UI only: Prevent server error and null-redirect. '''
        # format: /path/to/page@groupby/{config-key}/{vobj-key}/{page-num}
        if isinstance(node, Page) and len(pieces) >= 2:
            path = node['_path']  # type: str
            conf_key, vobj_key, *optional_page = pieces
            page = None
            if optional_page:
                try:
                    page = int(optional_page[0])
                except ValueError:
                    pass
            for rv in self._data.values():
                if rv.equals(path, conf_key, vobj_key, page):
                    return GroupBySource(
                        node, rv.key, rv.page).finalize(rv.config, rv.key_obj)
        return None
