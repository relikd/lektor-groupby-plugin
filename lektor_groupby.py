# -*- coding: utf-8 -*-
from lektor.build_programs import BuildProgram
from lektor.builder import Artifact, Builder  # typing
from lektor.constants import PRIMARY_ALT
from lektor.db import Database, Record  # typing
from lektor.pluginsystem import Plugin
from lektor.reporter import reporter
from lektor.sourceobj import SourceObject, VirtualSourceObject
from lektor.types.flow import Flow, FlowType
from lektor.utils import bool_from_string, build_url, prune_file_and_folder
# for quick config
from lektor.utils import slugify

from typing import Tuple, Dict, Set, List, NamedTuple
from typing import NewType, Optional, Iterator, Callable, Iterable

VPATH = '@groupby'  # potentially unsafe. All matching entries are pruned.


# -----------------------------------
#            Typing
# -----------------------------------
AttributeKey = NewType('AttributeKey', str)  # attribute of lektor model
GroupKey = NewType('GroupKey', str)  # key of group-by


class ResolverConf(NamedTuple):
    path: str
    attrib: AttributeKey
    group: GroupKey
    slug: str


class FieldKeyPath(NamedTuple):
    fieldKey: str
    flowIndex: Optional[int] = None
    flowKey: Optional[str] = None


class GroupByCallbackArgs(NamedTuple):
    record: Record
    key: FieldKeyPath
    field: object  # lektor model data-field value


GroupingCallback = Callable[[GroupByCallbackArgs],
                            Iterator[Tuple[GroupKey, object]]]


# -----------------------------------
#    VirtualSource & BuildProgram
# -----------------------------------


class GroupBySource(VirtualSourceObject):
    '''
    Holds information for a single group/cluster.
    This object is accessible in your template file.
    Attributes: record, attrib, group, slug, template, children

    :DEFAULTS:
    slug: "{attrib}/{group}/index.html"
    template: "groupby-attribute.html"
    '''

    def __init__(
        self,
        record: Record,
        attrib: AttributeKey,
        group: GroupKey, *,
        slug: Optional[str] = None,  # default: "{attrib}/{group}/index.html"
        template: Optional[str] = None  # default: "groupby-attrib.html"
    ) -> None:
        super().__init__(record)
        self.attrib = attrib
        self.group = group
        self.template = template or 'groupby-{}.html'.format(self.attrib)
        # custom user path
        slug = slug or '{attrib}/{group}/index.html'
        slug = slug.replace('{attrib}', self.attrib)
        slug = slug.replace('{group}', self.group)
        if slug.endswith('/index.html'):
            slug = slug[:-10]
        self.slug = slug
        # user adjustable after init
        self.children = {}  # type: Dict[Record, List[object]]
        self.dependencies = set()  # type: Set[str]

    @property
    def path(self) -> str:
        # Used in VirtualSourceInfo, used to prune VirtualObjects
        return f'{self.record.path}{VPATH}/{self.attrib}/{self.group}'

    @property
    def url_path(self) -> str:
        # Actual path to resource as seen by the browser
        return build_url([self.record.path, self.slug])

    def __getitem__(self, name: str) -> object:
        if name == '_path':
            return self.path
        elif name == '_alt':
            return PRIMARY_ALT
        return None

    def iter_source_filenames(self) -> Iterator[str]:
        ''' Enumerate all dependencies '''
        if self.dependencies:
            yield from self.dependencies
        for record in self.children:
            yield from record.iter_source_filenames()

    def __str__(self) -> str:
        txt = '<GroupBySource'
        for x in ['attrib', 'group', 'slug', 'template']:
            txt += ' {}="{}"'.format(x, getattr(self, x))
        return txt + ' children={}>'.format(len(self.children))


class GroupByBuildProgram(BuildProgram):
    ''' Generate Build-Artifacts and write files. '''

    def produce_artifacts(self) -> None:
        url = self.source.url_path
        if url.endswith('/'):
            url += 'index.html'
        self.declare_artifact(url, sources=list(
            self.source.iter_source_filenames()))
        GroupByPruner.track(url)

    def build_artifact(self, artifact: Artifact) -> None:
        self.source.pad.db.track_record_dependency(self.source)
        artifact.render_template_into(self.source.template, this=self.source)


# -----------------------------------
#              Helper
# -----------------------------------


class GroupByPruner:
    '''
    Static collector for build-artifact urls.
    All non-tracked VPATH-urls will be pruned after build.
    '''
    _cache: Set[str] = set()
    # Note: this var is static or otherwise two instances of
    #       GroupByCreator would prune each others artifacts.

    @classmethod
    def track(cls, url: str) -> None:
        ''' Add url to build cache to prevent pruning. '''
        cls._cache.add(url.lstrip('/'))

    @classmethod
    def prune(cls, builder: Builder) -> None:
        ''' Remove previously generated, unreferenced Artifacts. '''
        dest_path = builder.destination_path
        con = builder.connect_to_database()
        try:
            with builder.new_build_state() as build_state:
                for url, file in build_state.iter_artifacts():
                    if url.lstrip('/') in cls._cache:
                        continue  # generated in this build-run
                    infos = build_state.get_artifact_dependency_infos(url, [])
                    for v_path, _ in infos:
                        if VPATH not in v_path:
                            continue  # we only care about groupby Virtuals
                        reporter.report_pruned_artifact(url)
                        prune_file_and_folder(file.filename, dest_path)
                        build_state.remove_artifact(url)
                        break  # there is only one VPATH-entry per source
        finally:
            con.close()
        cls._cache.clear()


class GroupByModelReader:
    ''' Find models and flow-models which contain attrib '''

    def __init__(self, db: Database, attrib: AttributeKey) -> None:
        self._flows = {}  # type: Dict[str, Set[str]]
        self._models = {}  # type: Dict[str, Dict[str, str]]
        # find flow blocks with attrib
        for key, flow in db.flowblocks.items():
            tmp1 = set(f.name for f in flow.fields
                       if bool_from_string(f.options.get(attrib, False)))
            if tmp1:
                self._flows[key] = tmp1
        # find models with attrib or flow-blocks containing attrib
        for key, model in db.datamodels.items():
            tmp2 = {}  # Dict[str, str]
            for field in model.fields:
                if bool_from_string(field.options.get(attrib, False)):
                    tmp2[field.name] = '*'  # include all children
                elif isinstance(field.type, FlowType) and self._flows:
                    # only processed if at least one flow has attrib
                    fbs = field.type.flow_blocks
                    # if fbs == None, all flow-blocks are allowed
                    if fbs is None or any(x in self._flows for x in fbs):
                        tmp2[field.name] = '?'  # only some flow blocks
            if tmp2:
                self._models[key] = tmp2

    def read(
        self,
        record: Record,
        flatten: bool = False
    ) -> Iterator[Tuple[FieldKeyPath, object]]:
        '''
        Enumerate all fields of a Record with attrib = True.
        Flows are either returned directly (flatten=False) or
        expanded so that each flow-block is yielded (flatten=True)
        '''
        assert isinstance(record, Record)
        for r_key, subs in self._models.get(record.datamodel.id, {}).items():
            if subs == '*':  # either normal field or flow type (all blocks)
                field = record[r_key]
                if flatten and isinstance(field, Flow):
                    for i, flow in enumerate(field.blocks):
                        flowtype = flow['_flowblock']
                        for f_key, block in flow._data.items():
                            if f_key.startswith('_'):  # e.g., _flowblock
                                continue
                            yield FieldKeyPath(r_key, i, f_key), block
                else:
                    yield FieldKeyPath(r_key), field
            else:  # always flow type (only some blocks)
                for i, flow in enumerate(record[r_key].blocks):
                    flowtype = flow['_flowblock']
                    for f_key in self._flows.get(flowtype, []):
                        yield FieldKeyPath(r_key, i, f_key), flow[f_key]


class GroupByState:
    ''' Holds and updates a groupby build state. '''

    def __init__(self) -> None:
        self.state = {}  # type: Dict[GroupKey, Dict[Record, List]]
        self._processed = set()  # type: Set[Record]

    def __contains__(self, record: Record) -> bool:
        ''' Returns True if record was already processed. '''
        return record.path in self._processed

    def items(self) -> Iterable[Tuple[GroupKey, Dict]]:
        ''' Iterable with (GroupKey, {record: extras}) tuples. '''
        return self.state.items()

    def add(self, record: Record, group: Dict[GroupKey, List]) -> None:
        ''' Append groups if not processed already. '''
        if record.path not in self._processed:
            self._processed.add(record.path)
            for group_key, extras in group.items():
                if group_key in self.state:
                    self.state[group_key][record] = extras
                else:
                    self.state[group_key] = {record: extras}


class GroupByWatcher:
    '''
    Callback is called with (Record, FieldKeyPath, field-value).
    Callback may yield one or more (group-key, extra-info) tuples.
    '''

    def __init__(
        self,
        root: str,
        attrib: AttributeKey,
        callback: GroupingCallback, *,
        slug: Optional[str] = None,  # default: "{attrib}/{group}/index.html"
        template: Optional[str] = None  # default: "groupby-attrib.html"
    ) -> None:
        self.root = root
        self.attrib = attrib
        self.callback = callback
        self.slug = slug
        self.template = template
        # user editable attributes
        self.flatten = True  # if False, dont explode FlowType
        self.dependencies = set()  # type: Set[str]

    def initialize(self, db: Database) -> None:
        ''' Reset internal state. You must initialize before each build! '''
        self._state = GroupByState()
        self._model_reader = GroupByModelReader(db, self.attrib)

    def should_process(self, node: SourceObject) -> bool:
        ''' Check if record path is being watched. '''
        if isinstance(node, Record):
            p = node['_path']  # type: str
            return p.startswith(self.root) or p + '/' == self.root
        return False

    def process(self, record: Record) -> None:
        '''
        Will iterate over all record fields and call the callback method.
        Each record is guaranteed to be processed only once.
        '''
        if record in self._state:
            return
        tmp = {}
        for key, field in self._model_reader.read(record, self.flatten):
            for ret in self.callback(GroupByCallbackArgs(record, key, field)):
                assert isinstance(ret, (tuple, list)), \
                    'Must return tuple (group-key, extra-info)'
                group_key, extra = ret
                if group_key not in tmp:
                    tmp[group_key] = [extra]
                else:
                    tmp[group_key].append(extra)
        self._state.add(record, tmp)

    def iter_sources(self, root: Record) -> Iterator[GroupBySource]:
        ''' Prepare and yield GroupBySource elements. '''
        for group_key, children in self._state.items():
            src = GroupBySource(root, self.attrib, group_key,
                                slug=self.slug, template=self.template)
            src.dependencies = self.dependencies
            src.children = children
            yield src

    def __str__(self) -> str:
        txt = '<GroupByWatcher'
        for x in [
            'root', 'attrib', 'slug', 'template', 'flatten', 'dependencies'
        ]:
            txt += ' {}="{}"'.format(x, getattr(self, x))
        return txt + '>'


# -----------------------------------
#           Main Component
# -----------------------------------


class GroupByCreator:
    '''
    Process all children with matching conditions under specified page.
    Creates a grouping of pages with similar (self-defined) attributes.
    The grouping is performed only once per build.
    '''

    def __init__(self) -> None:
        self._watcher = []  # type: List[GroupByWatcher]
        self._results = {}  # type: Dict[str, GroupBySource]
        self._resolve_map = {}  # type: Dict[str, ResolverConf]

    # ----------------
    #   Add Observer
    # ----------------

    def depends_on(self, *args: str) \
            -> Callable[[GroupByWatcher], GroupByWatcher]:
        ''' Set GroupBySource dependency, e.g., a plugin config file. '''
        def _decorator(r: GroupByWatcher) -> GroupByWatcher:
            r.dependencies.update(list(args))
            return r
        return _decorator

    def watch(
        self,
        root: str,
        attrib: AttributeKey, *,
        slug: Optional[str] = None,  # default: "{attrib}/{group}/index.html"
        template: Optional[str] = None,  # default: "groupby-attrib.html"
        flatten: bool = True,  # if False, dont explode FlowType
    ) -> Callable[[GroupingCallback], GroupByWatcher]:
        '''
        Decorator to subscribe to attrib-elements.
        (record, field-key, field) -> (group-key, extra-info)

        :DEFAULTS:
        slug: "{attrib}/{group}/index.html"
        template: "groupby-attrib.html"
        '''
        root = root.rstrip('/') + '/'

        def _decorator(fn: GroupingCallback) -> GroupByWatcher:
            w = GroupByWatcher(root, attrib, fn, slug=slug, template=template)
            w.flatten = flatten
            self._watcher.append(w)
            return w

        return _decorator

    # -----------
    #   Builder
    # -----------

    def clear_previous_results(self) -> None:
        ''' Reset prvious results. Must be called before each build. '''
        self._watcher.clear()
        self._results.clear()
        self._resolve_map.clear()

    def make_cluster(self, builder: Builder) -> None:
        ''' Perform groupby, iterate over all children. '''
        if not self._watcher:
            return
        for w in self._watcher:
            w.initialize(builder.pad.db)

        queue = builder.pad.get_all_roots()  # type: List[SourceObject]
        while queue:
            record = queue.pop()
            self.queue_now(record)
            if hasattr(record, 'attachments'):
                queue.extend(record.attachments)  # type: ignore[attr-defined]
            if hasattr(record, 'children'):
                queue.extend(record.children)  # type: ignore[attr-defined]
        # build artifacts
        for w in self._watcher:
            root = builder.pad.get(w.root)
            for vobj in w.iter_sources(root):
                self._results[vobj.url_path] = vobj
        self._watcher.clear()

    def queue_now(self, node: SourceObject) -> None:
        ''' Process record immediatelly (No-Op if already processed). '''
        for w in self._watcher:
            if w.should_process(node):  # ensures type Record
                w.process(node)  # type: ignore[arg-type]

    def build_all(self, builder: Builder) -> None:
        ''' Create virtual objects and build sources. '''
        for url, x in sorted(self._results.items()):
            builder.build(x)
            self._resolve_map[url] = ResolverConf(
                x.record['_path'], x.attrib, x.group, x.slug)
        self._results.clear()

    # -----------------
    #   Path resolver
    # -----------------

    def resolve_dev_server_path(
        self, node: SourceObject, pieces: List[str]
    ) -> Optional[GroupBySource]:
        ''' Dev server only: Resolves path/ -> path/index.html '''
        if not isinstance(node, Record):
            return None
        conf = self._resolve_map.get(build_url([node.url_path] + pieces))
        if not conf:
            return None
        return GroupBySource(node, conf.attrib, conf.group, slug=conf.slug)

    def resolve_virtual_path(
        self, node: SourceObject, pieces: List[str]
    ) -> Optional[GroupBySource]:
        if isinstance(node, Record) and len(pieces) >= 2:
            test_node = (node['_path'], pieces[0], pieces[1])
            for url, conf in self._resolve_map.items():
                if test_node == conf[:3]:
                    _, attr, group, slug = conf
                    return GroupBySource(node, attr, group, slug=slug)
        return None


# -----------------------------------
#           Plugin Entry
# -----------------------------------


class GroupByPlugin(Plugin):
    name = 'GroupBy Plugin'
    description = 'Cluster arbitrary records with field attribute keyword.'

    def on_setup_env(self, **extra: object) -> None:
        self.creator = GroupByCreator()
        self.env.add_build_program(GroupBySource, GroupByBuildProgram)

        # resolve /tag/rss/ -> /tag/rss/index.html (local server only)
        @self.env.urlresolver
        def a(node: SourceObject, parts: List[str]) -> Optional[GroupBySource]:
            return self.creator.resolve_dev_server_path(node, parts)

        @self.env.virtualpathresolver(VPATH.lstrip('@'))
        def b(node: SourceObject, parts: List[str]) -> Optional[GroupBySource]:
            return self.creator.resolve_virtual_path(node, parts)

    def _load_quick_config(self) -> None:
        ''' Load config file quick listeners. '''
        config = self.get_config()
        for attrib in config.sections():
            sect = config.section_as_dict(attrib)
            root = sect.get('root', '/')
            slug = sect.get('slug')
            temp = sect.get('template')
            split = sect.get('split')

            @self.creator.depends_on(self.config_filename)
            @self.creator.watch(root, attrib, slug=slug, template=temp)
            def _fn(args: GroupByCallbackArgs) \
                    -> Iterator[Tuple[GroupKey, object]]:
                val = args.field
                if isinstance(val, str):
                    val = val.split(split) if split else [val]  # make list
                if isinstance(val, list):
                    for tag in val:
                        yield slugify(tag), tag

    def on_before_build_all(self, builder: Builder, **extra: object) -> None:
        self.creator.clear_previous_results()
        # let other plugins register their @groupby.watch functions
        self.emit('before-build-all', groupby=self.creator, builder=builder)
        self.creator.make_cluster(builder)

    def on_before_build(self, source: SourceObject, **extra: object) -> None:
        # before-build may be called before before-build-all (issue #1017)
        # make sure it is evaluated immediatelly
        self.creator.queue_now(source)

    def on_after_build_all(self, builder: Builder, **extra: object) -> None:
        self.emit('after-build-all', groupby=self.creator, builder=builder)
        self._load_quick_config()
        self.creator.make_cluster(builder)
        self.creator.build_all(builder)

    def on_after_prune(self, builder: Builder, **extra: object) -> None:
        # TODO: find a better way to prune unreferenced elements
        GroupByPruner.prune(builder)
