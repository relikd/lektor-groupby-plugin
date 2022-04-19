from lektor.build_programs import BuildProgram  # subclass
from lektor.context import get_ctx
from lektor.environment import Expression
from lektor.sourceobj import VirtualSourceObject  # subclass
from lektor.utils import build_url
from typing import TYPE_CHECKING, Dict, List, Any, Optional, Iterator
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
        self._children = {}  # type: Dict[Record, List[Any]]

    def append_child(self, child: 'Record', extra: Any, group: str) -> None:
        if child not in self._children:
            self._children[child] = [extra]
        else:
            self._children[child].append(extra)
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
        return build_url([self.record.path, self.slug])  # slug can be None!

    def iter_source_filenames(self) -> Iterator[str]:
        ''' Enumerate all dependencies '''
        if self.config.dependencies:
            yield from self.config.dependencies
        for record in self._children:
            yield from record.iter_source_filenames()

    # -----------------------
    #   Properties & Helper
    # -----------------------

    @property
    def children(self) -> Dict['Record', List[Any]]:
        ''' Returns dict with page record key and (optional) extra value. '''
        return self._children

    @property
    def first_child(self) -> Optional['Record']:
        ''' Returns first referencing page record. '''
        if self._children:
            return iter(self._children).__next__()
        return None

    @property
    def first_extra(self) -> Optional[Any]:
        ''' Returns first additional / extra info object of first page. '''
        if not self._children:
            return None
        val = iter(self._children.values()).__next__()
        return val[0] if val else None

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
