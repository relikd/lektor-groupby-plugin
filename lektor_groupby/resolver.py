from lektor.db import Page  # isinstance
from typing import TYPE_CHECKING, NamedTuple, Dict, List, Set, Any, Optional
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
        self._data = {}  # type: Dict[str, Dict[str, ResolverEntry]]
        env.urlresolver(self.resolve_server_path)
        env.virtualpathresolver(VPATH.lstrip('@'))(self.resolve_virtual_path)

    @property
    def has_any(self) -> bool:
        return any(bool(x) for x in self._data.values())

    @property
    def files(self) -> Set[str]:
        return set(y for x in self._data.values() for y in x.keys())

    def reset(self, key: Optional[str] = None) -> None:
        ''' Clear previously recorded virtual objects. '''
        if key:
            if key in self._data:  # only delete if exists
                del self._data[key]
        else:
            self._data.clear()

    def add(self, vobj: GroupBySource) -> None:
        ''' Track new virtual object (only if slug is set). '''
        if vobj.slug:
            # `page_num = 1` overwrites `page_num = None` -> same url_path()
            if vobj.config.key not in self._data:
                self._data[vobj.config.key] = {}
            self._data[vobj.config.key][vobj.url_path] = ResolverEntry(
                vobj.key, vobj.key_obj, vobj.config, vobj.page_num)

    # ------------
    #   Resolver
    # ------------

    def resolve_server_path(self, node: 'SourceObject', pieces: List[str]) \
            -> Optional[GroupBySource]:
        ''' Local server only: resolve /tag/rss/ -> /tag/rss/index.html '''
        if isinstance(node, Page):
            url = build_url([node.url_path] + pieces)
            for subset in self._data.values():
                rv = subset.get(url)
                if rv:
                    return GroupBySource(
                        node, rv.key, rv.config, rv.page).finalize(rv.key_obj)
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
            for rv in self._data.get(conf_key, {}).values():
                if rv.equals(path, conf_key, vobj_key, page):
                    return GroupBySource(
                        node, rv.key, rv.config, rv.page).finalize(rv.key_obj)
        return None
