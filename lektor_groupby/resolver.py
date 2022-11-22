from lektor.db import Page  # isinstance
from typing import TYPE_CHECKING, Dict, List, NamedTuple, Optional, Iterable
from .util import build_url
from .vobj import VPATH, GroupBySource
if TYPE_CHECKING:
    from lektor.environment import Environment
    from lektor.sourceobj import SourceObject
    from .config import Config


class ResolverEntry(NamedTuple):
    slug: str
    group: str
    config: 'Config'
    page: Optional[int]

    def equals(
        self, path: str, attribute: str, group: str, page: Optional[int]
    ) -> bool:
        return self.slug == group \
            and self.config.key == attribute \
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

    def reset(self) -> None:
        ''' Clear previously recorded virtual objects. '''
        self._data.clear()

    def add(self, vobj: GroupBySource) -> None:
        ''' Track new virtual object (only if slug is set). '''
        if vobj.slug:
            # page_num = 1 overwrites page_num = None -> same url_path()
            self._data[vobj.url_path] = ResolverEntry(
                vobj.key, vobj.group, vobj.config, vobj.page_num)

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
                    node, rv.slug, rv.page).finalize(rv.config, rv.group)
        return None

    def resolve_virtual_path(self, node: 'SourceObject', pieces: List[str]) \
            -> Optional[GroupBySource]:
        ''' Admin UI only: Prevent server error and null-redirect. '''
        if isinstance(node, Page) and len(pieces) >= 2:
            path = node['_path']  # type: str
            attr, grp, *optional_page = pieces
            page = None
            if optional_page:
                try:
                    page = int(optional_page[0])
                except ValueError:
                    pass
            for rv in self._data.values():
                if rv.equals(path, attr, grp, page):
                    return GroupBySource(
                        node, rv.slug, rv.page).finalize(rv.config, rv.group)
        return None
