from lektor.build_programs import BuildProgram  # subclass
from lektor.context import get_ctx
from lektor.db import _CmpHelper
from lektor.environment import Expression
from lektor.sourceobj import VirtualSourceObject  # subclass
from lektor.utils import build_url
from typing import TYPE_CHECKING, List, Any, Optional, Iterator, Iterable
from .util import report_config_error, most_used_key
if TYPE_CHECKING:
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

    def __init__(self, record: 'Record', slug: str) -> None:
        super().__init__(record)
        self.key = slug
        self._group_map = []  # type: List[str]
        self._children = []  # type: List[Record]

    def append_child(self, child: 'Record', group: str) -> None:
        if child not in self._children:
            self._children.append(child)
        # _group_map is later used to find most used group
        self._group_map.append(group)

    # -------------------------
    #   Evaluate Extra Fields
    # -------------------------

    def finalize(self, config: 'Config', group: Optional[str] = None) \
            -> 'GroupBySource':
        self.config = config
        self.group = group or most_used_key(self._group_map)
        del self._group_map
        # evaluate slug Expression
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
        # sort children
        if config.order_by:
            # using get_sort_key() of Record
            self._children.sort(key=lambda x: x.get_sort_key(config.order_by))
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

    # ---------------------
    #   Lektor properties
    # ---------------------

    @property
    def path(self) -> str:
        # Used in VirtualSourceInfo, used to prune VirtualObjects
        return f'{self.record.path}{VPATH}/{self.config.key}/{self.key}'

    @property
    def url_path(self) -> str:
        # Actual path to resource as seen by the browser
        return build_url([self.record.url_path, self.slug])  # slug can be None

    def iter_source_filenames(self) -> Iterator[str]:
        ''' Enumerate all dependencies '''
        if self.config.dependencies:
            yield from self.config.dependencies
        for record in self._children:
            yield from record.iter_source_filenames()

    # def get_checksum(self, path_cache: 'PathCache') -> Optional[str]:
    #     deps = [self.pad.env.jinja_env.get_or_select_template(
    #         self.config.template).filename]
    #     deps.extend(self.iter_source_filenames())
    #     sums = '|'.join(path_cache.get_file_info(x).filename_and_checksum
    #                     for x in deps if x) + str(len(self._children))
    #     return hashlib.sha1(sums.encode('utf-8')).hexdigest() if sums else None

    # @property
    # def pagination(self):
    #     print('pagination')
    #     return None

    # def __for_page__(self, page_num):
    #     """Get source object for a (possibly) different page number.
    #     """
    #     print('for page', page_num)
    #     return self

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
    def children(self) -> List['Record']:
        ''' Returns dict with page record key and (optional) extra value. '''
        return self._children

    @property
    def first_child(self) -> Optional['Record']:
        ''' Returns first referencing page record. '''
        if self._children:
            return iter(self._children).__next__()
        return None

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
            self.path, len(self._children))


# -----------------------------------
#           BuildProgram
# -----------------------------------

class GroupByBuildProgram(BuildProgram):
    ''' Generate Build-Artifacts and write files. '''

    def produce_artifacts(self) -> None:
        url = self.source.url_path
        if url.endswith('/'):
            url += 'index.html'
        self.declare_artifact(url, sources=list(
            self.source.iter_source_filenames()))

    def build_artifact(self, artifact: 'Artifact') -> None:
        get_ctx().record_virtual_dependency(self.source)
        artifact.render_template_into(
            self.source.config.template, this=self.source)
