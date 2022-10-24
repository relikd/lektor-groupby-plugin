from lektor.build_programs import BuildProgram  # subclass
from lektor.context import get_ctx
from lektor.db import _CmpHelper
from lektor.environment import Expression
from lektor.sourceobj import VirtualSourceObject  # subclass
from werkzeug.utils import cached_property

from typing import TYPE_CHECKING, List, Any, Optional, Iterator, Iterable
from .pagination import PaginationConfig
from .query import FixedRecordsQuery
from .util import (
    report_config_error, most_used_key, insert_before_ext, build_url
)
if TYPE_CHECKING:
    from lektor.pagination import Pagination
    from lektor.builder import Artifact
    from lektor.db import Record
    from .config import Config

VPATH = '@groupby'  # potentially unsafe. All matching entries are pruned.


# -----------------------------------
#           VirtualSource
# -----------------------------------

class GroupBySource(VirtualSourceObject):
    '''
    Holds information for a single group/cluster.
    This object is accessible in your template file.
    Attributes: record, key, group, slug, children, config
    '''

    def __init__(
        self,
        record: 'Record',
        slug: str,
        page_num: Optional[int] = None
    ) -> None:
        super().__init__(record)
        self.key = slug
        self.page_num = page_num
        self.__children = []  # type: List[str]
        self.__group_map = []  # type: List[str]

    def append_child(self, child: 'Record', group: str) -> None:
        if child not in self.__children:
            self.__children.append(child.path)
        # __group_map is later used to find most used group
        self.__group_map.append(group)

    # -------------------------
    #   Evaluate Extra Fields
    # -------------------------

    def finalize(self, config: 'Config', group: Optional[str] = None) \
            -> 'GroupBySource':
        self.config = config
        # make a sorted children query
        self._query = FixedRecordsQuery(self.pad, self.__children, self.alt)
        self._query._order_by = config.order_by
        # set group name
        self.group = group or most_used_key(self.__group_map)
        # cleanup temporary data
        del self.__children
        del self.__group_map
        # evaluate slug Expression
        self.slug = None  # type: Optional[str]
        if config.slug and '{key}' in config.slug:
            self.slug = config.slug.replace('{key}', self.key)
        else:
            self.slug = self._eval(config.slug, field='slug')
            assert self.slug != Ellipsis, 'invalid config: ' + config.slug
        if self.slug and self.slug.endswith('/index.html'):
            self.slug = self.slug[:-10]
        # extra fields
        for attr, expr in config.fields.items():
            setattr(self, attr, self._eval(expr, field='fields.' + attr))
        return self

    def _eval(self, value: Any, *, field: str) -> Any:
        ''' Internal only: evaluates Lektor config file field expression. '''
        if not isinstance(value, str):
            return value
        pad = self.record.pad
        alt = self.record.alt
        try:
            return Expression(pad.env, value).evaluate(pad, this=self, alt=alt)
        except Exception as e:
            report_config_error(self.config.key, field, value, e)
            return Ellipsis

    # -----------------------
    #   Pagination handling
    # -----------------------

    @cached_property
    def _pagination_config(self) -> 'PaginationConfig':
        # Generate `PaginationConfig` once we need it
        return PaginationConfig(self.record.pad.env, **self.config.pagination)

    @cached_property
    def pagination(self) -> 'Pagination':
        # Generate `Pagination` once we need it
        return self._pagination_config.get_pagination_controller(self)

    def __iter_pagination_sources__(self) -> Iterator['GroupBySource']:
        ''' If pagination enabled, yields `GroupBySourcePage` sub-pages. '''
        # Used in GroupBy.make_once() to generated paginated child sources
        if self._pagination_config.enabled and self.page_num is None:
            for page_num in range(self._pagination_config.count_pages(self)):
                yield self.__for_page__(page_num + 1)

    def __for_page__(self, page_num: Optional[int]) -> 'GroupBySource':
        ''' Get source object for a (possibly) different page number. '''
        assert page_num is not None
        return GroupBySourcePage(self, page_num)

    # ---------------------
    #   Lektor properties
    # ---------------------

    @property
    def path(self) -> str:
        # Used in VirtualSourceInfo, used to prune VirtualObjects
        vpath = f'{self.record.path}{VPATH}/{self.config.key}/{self.key}'
        if self.page_num:
            vpath += '/' + str(self.page_num)
        return vpath

    @property
    def url_path(self) -> str:
        # Actual path to resource as seen by the browser
        parts = [self.record.url_path]
        # slug can be None!!
        if not self.slug:
            return build_url(parts)
        # if pagination enabled, append pagination.url_suffix to path
        if self.page_num and self.page_num > 1:
            sffx = self._pagination_config.url_suffix
            if '.' in self.slug.split('/')[-1]:
                # default: ../slugpage2.html (use e.g.: url_suffix = .page.)
                parts.append(insert_before_ext(
                    self.slug, sffx + str(self.page_num), '.'))
            else:
                # default: ../slug/page/2/index.html
                parts += [self.slug, sffx, self.page_num]
        else:
            parts.append(self.slug)
        return build_url(parts)

    def iter_source_filenames(self) -> Iterator[str]:
        ''' Enumerate all dependencies '''
        if self.config.dependencies:
            yield from self.config.dependencies
        for record in self.children:
            yield from record.iter_source_filenames()

    # def get_checksum(self, path_cache: 'PathCache') -> Optional[str]:
    #     deps = [self.pad.env.jinja_env.get_or_select_template(
    #         self.config.template).filename]
    #     deps.extend(self.iter_source_filenames())
    #     sums = '|'.join(path_cache.get_file_info(x).filename_and_checksum
    #                     for x in deps if x) + str(self.children.count())
    #     return hashlib.sha1(sums.encode('utf-8')).hexdigest() if sums else None

    def get_sort_key(self, fields: Iterable[str]) -> List:
        def cmp_val(field: str) -> Any:
            reverse = field.startswith('-')
            if reverse or field.startswith('+'):
                field = field[1:]
            return _CmpHelper(getattr(self, field, None), reverse)

        return [cmp_val(field) for field in fields or []]

    # -----------------------
    #   Properties & Helper
    # -----------------------

    @cached_property
    def children(self) -> FixedRecordsQuery:
        ''' Return query of children of type Record. '''
        return self._query.request_page(self.page_num)

    def __getitem__(self, key: str) -> Any:
        # Used for virtual path resolver
        if key in ('_path', '_alt'):
            return getattr(self, key[1:])
        return self.__missing__(key)  # type: ignore[attr-defined]

    def __lt__(self, other: 'GroupBySource') -> bool:
        # Used for |sort filter ("group" is the provided original string)
        return self.group.lower() < other.group.lower()

    def __eq__(self, other: object) -> bool:
        # Used for |unique filter
        if self is other:
            return True
        return isinstance(other, GroupBySource) and \
            self.path == other.path and self.slug == other.slug

    def __hash__(self) -> int:
        # Used for hashing in set and dict
        return hash((self.path, self.slug))

    def __repr__(self) -> str:
        return '<GroupBySource path="{}" children={}>'.format(
            self.path,
            self.children.count() if hasattr(self, 'children') else '?')


# -----------------------------------
#           BuildProgram
# -----------------------------------

class GroupByBuildProgram(BuildProgram):
    ''' Generate Build-Artifacts and write files. '''

    def produce_artifacts(self) -> None:
        pagination_enabled = self.source._pagination_config.enabled
        if pagination_enabled and self.source.page_num is None:
            return  # only __iter_pagination_sources__()
        url = self.source.url_path
        if url.endswith('/'):
            url += 'index.html'
        self.declare_artifact(url, sources=list(
            self.source.iter_source_filenames()))

    def build_artifact(self, artifact: 'Artifact') -> None:
        get_ctx().record_virtual_dependency(self.source)
        artifact.render_template_into(
            self.source.config.template, this=self.source)


class GroupBySourcePage(GroupBySource):
    ''' Pagination wrapper. Redirects get attr/item to non-paginated node. '''

    def __init__(self, parent: 'GroupBySource', page_num: int) -> None:
        self.__parent = parent
        self.page_num = page_num

    def __for_page__(self, page_num: Optional[int]) -> 'GroupBySource':
        ''' Get source object for a (possibly) different page number. '''
        if page_num is None:
            return self.__parent
        if page_num == self.page_num:
            return self
        return GroupBySourcePage(self.__parent, page_num)

    def __getitem__(self, key: str) -> Any:
        return self.__parent.__getitem__(key)

    def __getattr__(self, key: str) -> Any:
        return getattr(self.__parent, key)

    def __repr__(self) -> str:
        return '<GroupBySourcePage path="{}" page={}>'.format(
            self.__parent.path, self.page_num)
