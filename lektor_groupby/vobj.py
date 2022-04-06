from lektor.build_programs import BuildProgram  # subclass
from lektor.builder import Artifact  # typing
from lektor.context import get_ctx
from lektor.db import Record  # typing
from lektor.environment import Expression
from lektor.sourceobj import VirtualSourceObject  # subclass
from lektor.utils import build_url

from typing import Dict, List, Any, Optional, Iterator
from weakref import WeakSet
from .config import Config
from .pruner import track_not_prune
from .util import report_config_error

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
        record: Record,
        group: str,
        config: Config,
        children: Optional[Dict[Record, List[Any]]] = None,
    ) -> None:
        super().__init__(record)
        self.key = config.slugify(group)
        self.group = group
        self.config = config
        # evaluate slug Expression
        if config.slug and '{key}' in config.slug:
            self.slug = config.slug.replace('{key}', self.key)
        else:
            self.slug = self._eval(config.slug, field='slug')
            assert self.slug != Ellipsis, 'invalid config: ' + config.slug
        if self.slug and self.slug.endswith('/index.html'):
            self.slug = self.slug[:-10]
        # make sure children are on the same pad
        self._children = {}  # type: Dict[Record, List[Any]]
        for child, extras in (children or {}).items():
            if child.pad != record.pad:
                child = record.pad.get(child.path)
            self._children[child] = extras
        self._reverse_reference_records()
        # extra fields
        for attr, expr in config.fields.items():
            setattr(self, attr, self._eval(expr, field='fields.' + attr))

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
    def children(self) -> Dict[Record, List[Any]]:
        ''' Returns dict with page record key and (optional) extra value. '''
        return self._children

    @property
    def first_child(self) -> Optional[Record]:
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
        return self.group < other.group

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

    # ---------------------
    #   Reverse Reference
    # ---------------------

    def _reverse_reference_records(self) -> None:
        ''' Attach self to page records. '''
        for child in self._children:
            if not hasattr(child, '_vgroups'):
                child._vgroups = WeakSet()  # type: ignore[attr-defined]
            child._vgroups.add(self)  # type: ignore[attr-defined]

    @staticmethod
    def of_record(
        record: Record,
        *keys: str,
        recursive: bool = False
    ) -> Iterator['GroupBySource']:
        ''' Extract all referencing groupby virtual objects from a page. '''
        ctx = get_ctx()
        # manage dependencies
        if ctx:
            for dep in ctx.env.plugins['groupby'].config_dependencies:
                ctx.record_dependency(dep)
        # find groups
        proc_list = [record]
        while proc_list:
            page = proc_list.pop(0)
            if recursive and hasattr(page, 'children'):
                proc_list.extend(page.children)  # type: ignore[attr-defined]
            if not hasattr(page, '_vgroups'):
                continue
            for vobj in page._vgroups:  # type: ignore[attr-defined]
                if not keys or vobj.config.key in keys:
                    yield vobj


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
        track_not_prune(url)

    def build_artifact(self, artifact: Artifact) -> None:
        get_ctx().record_virtual_dependency(self.source)
        artifact.render_template_into(
            self.source.config.template, this=self.source)
