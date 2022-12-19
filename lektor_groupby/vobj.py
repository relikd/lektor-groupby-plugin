from lektor.build_programs import BuildProgram  # subclass
from lektor.context import get_ctx
from lektor.db import _CmpHelper
from lektor.environment import Expression
from lektor.sourceobj import VirtualSourceObject  # subclass
from typing import (
    TYPE_CHECKING, List, Any, Dict, Optional, Generator, Iterator, Iterable
)
from .pagination import PaginationConfig
from .pruner import VirtualPruner
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
    Attributes: record, key, key_obj, slug, children, config
    '''

    def __init__(
        self,
        record: 'Record',
        key: str,
        config: 'Config',
        page_num: Optional[int] = None
    ) -> None:
        super().__init__(record)
        self.__children = []  # type: List[str]
        self.__key_obj_map = []  # type: List[Any]
        self._expr_fields = {}  # type: Dict[str, Expression]
        self.key = key
        self.config = config
        self.page_num = page_num

    def append_child(self, child: 'Record', key_obj: Any) -> None:
        if child not in self.__children:
            self.__children.append(child.path)
        # __key_obj_map is later used to find most used key_obj
        self.__key_obj_map.append(key_obj)

    def _update_attr(self, key: str, value: Any) -> None:
        ''' Set or remove Jinja evaluated Expression field. '''
        # TODO: instead we could evaluate the fields only once.
        #       But then we need to record_dependency() every successive access
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

    def finalize(self, key_obj: Optional[Any] = None) \
            -> 'GroupBySource':
        # make a sorted children query
        self._query = FixedRecordsQuery(self.pad, self.__children, self.alt)
        self._query._order_by = self.config.order_by
        del self.__children
        # set indexed original value (can be: str, int, float, bool, obj)
        self.key_obj = key_obj or most_used_key(self.__key_obj_map)
        del self.__key_obj_map

        if key_obj:  # exit early if initialized through resolver
            return self
        # extra fields
        for attr in self.config.fields:
            self._update_attr(attr, self.config.eval_field(attr, on=self))
        return self

    @cached_property
    def slug(self) -> Optional[str]:
        # evaluate slug Expression once we need it
        slug = self.config.eval_slug(self.key, on=self)
        if slug and slug.endswith('/index.html'):
            slug = slug[:-10]
        return slug

    # -----------------------
    #   Pagination handling
    # -----------------------

    @property
    def supports_pagination(self) -> bool:
        return self.config.pagination['enabled']  # type: ignore[no-any-return]

    @cached_property
    def _pagination_config(self) -> 'PaginationConfig':
        # Generate `PaginationConfig` once we need it
        return PaginationConfig(self.record.pad.env, self.config.pagination,
                                self._query.total)

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

    @property
    def children(self) -> FixedRecordsQuery:
        ''' Return query of children of type Record. '''
        return self._query

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
        # Used for |sort filter (`key_obj` is the indexed original value)
        if isinstance(self.key_obj, (bool, int, float)) and \
                isinstance(other.key_obj, (bool, int, float)):
            return self.key_obj < other.key_obj
        if self.key_obj is None:
            return False  # this will sort None at the end
        if other.key_obj is None:
            return True
        return str(self.key_obj).lower() < str(other.key_obj).lower()

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
        get_ctx().record_virtual_dependency(VirtualPruner())
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
