from lektor.build_programs import BuildProgram  # subclass
from lektor.context import get_ctx
from lektor.db import _CmpHelper
from lektor.environment import Expression
from lektor.sourceobj import VirtualSourceObject  # subclass
from typing import TYPE_CHECKING
from typing import List, Any, Dict, Optional, Generator, Iterator, Iterable
from .pagination import PaginationConfig
from .query import FixedRecordsQuery
from .util import most_used_key, insert_before_ext, build_url, cached_property
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
        self._expr_fields = {}  # type: Dict[str, Expression]
        self.__children = []  # type: List[str]
        self.__group_map = []  # type: List[Any]

    def append_child(self, child: 'Record', group: Any) -> None:
        if child not in self.__children:
            self.__children.append(child.path)
        # TODO: rename group to value
        # __group_map is later used to find most used group
        self.__group_map.append(group)

    def _update_attr(self, key: str, value: Any) -> None:
        ''' Set or remove Jinja evaluated Expression field. '''
        if isinstance(value, Expression):
            self._expr_fields[key] = value
            try:
                delattr(self, key)
            except AttributeError:
                pass
        else:
            if key in self._expr_fields:
                del self._expr_fields[key]
            setattr(self, key, value)

    # -------------------------
    #   Evaluate Extra Fields
    # -------------------------

    def finalize(self, config: 'Config', group: Optional[Any] = None) \
            -> 'GroupBySource':
        self.config = config
        # make a sorted children query
        self._query = FixedRecordsQuery(self.pad, self.__children, self.alt)
        self._query._order_by = config.order_by
        del self.__children
        # set group name
        self.group = group or most_used_key(self.__group_map)
        del self.__group_map
        # evaluate slug Expression
        self.slug = config.eval_slug(self.key, on=self)
        if self.slug and self.slug.endswith('/index.html'):
            self.slug = self.slug[:-10]

        if group:  # exit early if initialized through resolver
            return self
        # extra fields
        for attr in config.fields:
            self._update_attr(attr, config.eval_field(attr, on=self))
        return self

    # -----------------------
    #   Pagination handling
    # -----------------------

    @property
    def supports_pagination(self) -> bool:
        return self.config.pagination['enabled']  # type: ignore[no-any-return]

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
    def path(self) -> str:  # type: ignore[override]
        # Used in VirtualSourceInfo, used to prune VirtualObjects
        vpath = f'{self.record.path}{VPATH}/{self.config.key}/{self.key}'
        if self.page_num:
            vpath += '/' + str(self.page_num)
        return vpath

    @cached_property
    def url_path(self) -> str:  # type: ignore[override]
        ''' Actual path to resource as seen by the browser. '''
        # check if slug is absolute URL
        slug = self.slug
        if slug and slug.startswith('/'):
            parts = [self.pad.get_root(alt=self.alt).url_path]
        else:
            parts = [self.record.url_path]
        # slug can be None!!
        if not slug:
            return build_url(parts)
        # if pagination enabled, append pagination.url_suffix to path
        if self.page_num and self.page_num > 1:
            sffx = self._pagination_config.url_suffix
            if '.' in slug.rsplit('/', 1)[-1]:
                # default: ../slugpage2.html (use e.g.: url_suffix = .page.)
                parts.append(insert_before_ext(
                    slug, sffx + str(self.page_num), '.'))
            else:
                # default: ../slug/page/2/index.html
                parts += [slug, sffx, self.page_num]
        else:
            parts.append(slug)
        return build_url(parts)

    def iter_source_filenames(self) -> Generator[str, None, None]:
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
        return self.__missing__(key)

    def __getattr__(self, key: str) -> Any:
        ''' Lazy evaluate custom user field expressions. '''
        if key in self._expr_fields:
            expr = self._expr_fields[key]
            return expr.evaluate(self.pad, this=self, alt=self.alt)
        raise AttributeError

    def __lt__(self, other: 'GroupBySource') -> bool:
        # Used for |sort filter ("group" is the provided original string)
        if isinstance(self.group, (bool, int, float)) and \
                isinstance(other.group, (bool, int, float)):
            return self.group < other.group
        if self.group is None:
            return False
        if other.group is None:
            return True
        return str(self.group).lower() < str(other.group).lower()

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
