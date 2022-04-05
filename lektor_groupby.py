# -*- coding: utf-8 -*-
from lektor.build_programs import BuildProgram
from lektor.builder import Artifact, Builder, PathCache  # typing
from lektor.context import get_ctx
from lektor.db import Database, Record  # typing
from lektor.environment import Expression
from lektor.pluginsystem import Plugin, IniFile
from lektor.reporter import reporter, style
from lektor.sourceobj import SourceObject, VirtualSourceObject
from lektor.types.flow import Flow, FlowType
from lektor.utils import bool_from_string, build_url, prune_file_and_folder
# for quick config
from lektor.utils import slugify

from typing import Tuple, Dict, Set, List, Union, Any, NamedTuple
from typing import NewType, Optional, Iterable, Callable, Iterator, Generator
from weakref import WeakSet

VPATH = '@groupby'  # potentially unsafe. All matching entries are pruned.


# -----------------------------------
#            Typing
# -----------------------------------
SelectionKey = NewType('SelectionKey', str)  # attribute of lektor model
GroupKey = NewType('GroupKey', str)  # key of group-by


class FieldKeyPath(NamedTuple):
    fieldKey: str
    flowIndex: Optional[int] = None
    flowKey: Optional[str] = None


class GroupByCallbackArgs(NamedTuple):
    record: Record
    key: FieldKeyPath
    field: object  # lektor model data-field value


GroupByCallbackYield = Union[GroupKey, Tuple[GroupKey, object]]

GroupingCallback = Callable[[GroupByCallbackArgs], Union[
    Iterator[GroupByCallbackYield],
    Generator[GroupByCallbackYield, Optional[str], None],
]]


# -----------------------------------
#               Config
# -----------------------------------


class GroupByConfig:
    '''
    Holds information for GroupByWatcher and GroupBySource.
    This object is accessible in your template file ({{this.config}}).

    Available attributes:
    key, root, slug, template, enabled, dependencies, fields, key_map
    '''

    def __init__(
        self,
        key: SelectionKey, *,
        root: Optional[str] = None,  # default: "/"
        slug: Optional[str] = None,  # default: "{attr}/{group}/index.html"
        template: Optional[str] = None,  # default: "groupby-{attr}.html"
    ) -> None:
        self.key = key
        self.root = (root or '/').rstrip('/') + '/'
        self.slug = slug or f'"{key}/" ~ this.key ~ "/"'  # this: GroupBySource
        self.template = template or f'groupby-{self.key}.html'
        # editable after init
        self.enabled = True
        self.dependencies = set()  # type: Set[str]
        self.fields = {}  # type: Dict[str, str]
        self.key_map = {}  # type: Dict[str, str]

    def slugify(self, k: str) -> str:
        ''' key_map replace and slugify. '''
        return slugify(self.key_map.get(k, k))  # type: ignore[no-any-return]

    def set_fields(self, fields: Optional[Dict[str, str]]) -> None:
        '''
        The fields dict is a mapping of attrib = Expression values.
        Each dict key will be added to the GroupBySource virtual object.
        Each dict value is passed through jinja context first.
        '''
        self.fields = fields or {}

    def set_key_map(self, key_map: Optional[Dict[str, str]]) -> None:
        ''' This mapping replaces group keys before slugify. '''
        self.key_map = key_map or {}

    def __repr__(self) -> str:
        txt = '<GroupByConfig'
        for x in ['key', 'root', 'slug', 'template', 'dependencies']:
            txt += ' {}="{}"'.format(x, getattr(self, x))
        txt += f' fields="{", ".join(self.fields)}"'
        return txt + '>'

    @staticmethod
    def from_dict(key: SelectionKey, cfg: Dict[str, str]) -> 'GroupByConfig':
        ''' Set config fields manually. Only: key, root, slug, template. '''
        return GroupByConfig(
            key=key,
            root=cfg.get('root'),
            slug=cfg.get('slug'),
            template=cfg.get('template'),
        )

    @staticmethod
    def from_ini(key: SelectionKey, ini: IniFile) -> 'GroupByConfig':
        ''' Read and parse ini file. Also adds dependency tracking. '''
        cfg = ini.section_as_dict(key)  # type: Dict[str, str]
        conf = GroupByConfig.from_dict(key, cfg)
        conf.enabled = ini.get_bool(key + '.enabled', True)
        conf.dependencies.add(ini.filename)
        conf.set_fields(ini.section_as_dict(key + '.fields'))
        conf.set_key_map(ini.section_as_dict(key + '.key_map'))
        return conf


# -----------------------------------
#    VirtualSource & BuildProgram
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
        group: GroupKey,
        config: GroupByConfig,
        children: Optional[Dict[Record, List[object]]] = None,
    ) -> None:
        super().__init__(record)
        self.key = config.slugify(group)
        self.group = group
        self.config = config
        # make sure children are on the same pad
        self._children = {}  # type: Dict[Record, List[object]]
        for child, extras in (children or {}).items():
            if child.pad != record.pad:
                child = record.pad.get(child.path)
            self._children[child] = extras
        self._reverse_reference_records()
        # evaluate slug Expression
        self.slug = self._eval(config.slug, field='slug')  # type: str
        assert self.slug != Ellipsis, 'invalid config: ' + config.slug
        if self.slug and self.slug.endswith('/index.html'):
            self.slug = self.slug[:-10]
        # extra fields
        for attr, expr in config.fields.items():
            setattr(self, attr, self._eval(expr, field='fields.' + attr))

    def _eval(self, value: str, *, field: str) -> Any:
        ''' Internal only: evaluates Lektor config file field expression. '''
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

    def __getitem__(self, name: str) -> object:
        # needed for preview in admin UI
        if name == '_path':
            return self.path
        elif name == '_alt':
            return self.record.alt
        return None

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
    def children(self):
        return self._children

    @property
    def first_child(self) -> Optional[Record]:
        ''' Returns first referencing page record. '''
        if self._children:
            return iter(self._children).__next__()
        return None

    @property
    def first_extra(self) -> Optional[object]:
        ''' Returns first additional / extra info object of first page. '''
        if not self._children:
            return None
        val = iter(self._children.values()).__next__()
        return val[0] if val else None

    def __lt__(self, other: 'GroupBySource') -> bool:
        ''' The "group" attribute is used for sorting. '''
        return self.group < other.group

    def __repr__(self) -> str:
        return '<GroupBySource path="{}" children={}>'.format(
            self.path, len(self._children))

    # ---------------------
    #   Reverse Reference
    # ---------------------

    def _reverse_reference_records(self) -> None:
        ''' Attach self to page records. '''
        for child in self._children:
            if not hasattr(child, '_groupby'):
                child._groupby = WeakSet()  # type: ignore[attr-defined]
            child._groupby.add(self)  # type: ignore[attr-defined]

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
            if not hasattr(page, '_groupby'):
                continue
            for vobj in page._groupby:  # type: ignore[attr-defined]
                if not keys or vobj.config.key in keys:
                    yield vobj


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
        get_ctx().record_virtual_dependency(self.source)
        artifact.render_template_into(
            self.source.config.template, this=self.source)


# -----------------------------------
#              Helper
# -----------------------------------

def report_config_error(key: str, field: str, val: str, e: Exception) -> None:
    ''' Send error message to Lektor reporter. Indicate which field is bad. '''
    msg = '[ERROR] invalid config for [{}.{}] = "{}",  Error: {}'.format(
        key, field, val, repr(e))
    try:
        reporter._write_line(style(msg, fg='red'))
    except Exception:
        print(msg)


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
    ''' Find models and flow-models which contain attribute '''

    def __init__(self, db: Database, attrib: SelectionKey) -> None:
        self._flows = {}  # type: Dict[str, Set[str]]
        self._models = {}  # type: Dict[str, Dict[str, str]]
        # find flow blocks containing attribute
        for key, flow in db.flowblocks.items():
            tmp1 = set(f.name for f in flow.fields
                       if bool_from_string(f.options.get(attrib, False)))
            if tmp1:
                self._flows[key] = tmp1
        # find models and flow-blocks containing attribute
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
        self.state = {}  # type: Dict[GroupKey, Dict[Record, List[object]]]
        self._processed = set()  # type: Set[Record]

    def __contains__(self, record: Record) -> bool:
        ''' Returns True if record was already processed. '''
        return record.path in self._processed

    def items(self) -> Iterable[Tuple[GroupKey, Dict]]:
        ''' Iterable with (GroupKey, {record: [extras]}) tuples. '''
        return self.state.items()

    def add(self, record: Record, group: Dict[GroupKey, List[object]]) -> None:
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

    def __init__(self, config: GroupByConfig) -> None:
        self.config = config
        self.flatten = True
        self.callback = None  # type: GroupingCallback #type:ignore[assignment]

    def grouping(self, flatten: bool = True) \
            -> Callable[[GroupingCallback], None]:
        '''
        Decorator to subscribe to attrib-elements.
        If flatten = False, dont explode FlowType.

        (record, field-key, field) -> (group-key, extra-info)
        '''
        def _decorator(fn: GroupingCallback) -> None:
            self.flatten = flatten
            self.callback = fn
        return _decorator

    def initialize(self, db: Database) -> None:
        ''' Reset internal state. You must initialize before each build! '''
        assert callable(self.callback), 'No grouping callback provided.'
        self._root = self.config.root
        self._state = GroupByState()
        self._model_reader = GroupByModelReader(db, attrib=self.config.key)

    def should_process(self, node: Record) -> bool:
        ''' Check if record path is being watched. '''
        p = node['_path']  # type: str
        return p.startswith(self._root) or p + '/' == self._root

    def process(self, record: Record) -> None:
        '''
        Will iterate over all record fields and call the callback method.
        Each record is guaranteed to be processed only once.
        '''
        if record in self._state:
            return
        tmp = {}  # type: Dict[GroupKey, List[object]]
        for key, field in self._model_reader.read(record, self.flatten):
            _gen = self.callback(GroupByCallbackArgs(record, key, field))
            try:
                obj = next(_gen)
                while True:
                    if not isinstance(obj, (str, tuple)):
                        raise TypeError(f'Unsupported groupby yield: {obj}')
                    group = obj if isinstance(obj, str) else obj[0]
                    if group not in tmp:
                        tmp[group] = []
                    if isinstance(obj, tuple):
                        tmp[group].append(obj[1])
                    # return slugified group key and continue iteration
                    if isinstance(_gen, Generator) and not _gen.gi_yieldfrom:
                        obj = _gen.send(self.config.slugify(group))
                    else:
                        obj = next(_gen)
            except StopIteration:
                del _gen
        self._state.add(record, tmp)

    def iter_sources(self, root: Record) -> Iterator[GroupBySource]:
        ''' Prepare and yield GroupBySource elements. '''
        for group, children in self._state.items():
            yield GroupBySource(root, group, self.config, children=children)

    def __repr__(self) -> str:
        return '<GroupByWatcher key="{}" enabled={} callback={}>'.format(
            self.config.key, self.config.enabled, self.callback)


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
        self._resolver = {}  # type: Dict[str, Tuple[GroupKey, GroupByConfig]]
        self._weak_ref_keep_alive = []  # type: List[GroupBySource]

    # ----------------
    #   Add Observer
    # ----------------

    def add_watcher(
        self,
        key: SelectionKey,
        config: Union[GroupByConfig, IniFile, Dict]
    ) -> GroupByWatcher:
        ''' Init GroupByConfig and add to watch list. '''
        assert isinstance(config, (GroupByConfig, IniFile, Dict))
        if isinstance(config, GroupByConfig):
            cfg = config
        elif isinstance(config, IniFile):
            cfg = GroupByConfig.from_ini(key, config)
        elif isinstance(config, Dict):
            cfg = GroupByConfig.from_dict(key, config)

        w = GroupByWatcher(cfg)
        self._watcher.append(w)
        return w

    # -----------
    #   Builder
    # -----------

    def clear_previous_results(self) -> None:
        ''' Reset prvious results. Must be called before each build. '''
        self._watcher.clear()
        self._results.clear()
        self._resolver.clear()
        self._weak_ref_keep_alive.clear()

    def get_dependencies(self) -> Set[str]:
        deps = set()  # type: Set[str]
        for w in self._watcher:
            deps.update(w.config.dependencies)
        return deps

    def make_cluster(self, builder: Builder) -> None:
        ''' Iterate over all children and perform groupby. '''
        # remove disabled watchers
        self._watcher = [w for w in self._watcher if w.config.enabled]
        if not self._watcher:
            return
        # initialize remaining (enabled) watchers
        for w in self._watcher:
            w.initialize(builder.pad.db)
        # iterate over whole build tree
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
            root = builder.pad.get(w.config.root)
            for vobj in w.iter_sources(root):
                if vobj.slug:
                    url = vobj.url_path
                    self._results[url] = vobj
                    self._resolver[url] = (vobj.group, w.config)
                else:
                    self._weak_ref_keep_alive.append(vobj)  # for weak ref
        self._watcher.clear()

    def queue_now(self, node: SourceObject) -> None:
        ''' Process record immediatelly (No-Op if already processed). '''
        if isinstance(node, Record):
            for w in self._watcher:
                if w.should_process(node):
                    w.process(node)

    def build_all(self, builder: Builder) -> None:
        ''' Create virtual objects and build sources. '''
        path_cache = PathCache(builder.env)
        for _, vobj in sorted(self._results.items()):
            builder.build(vobj, path_cache)
        del path_cache
        self._results.clear()
        self._weak_ref_keep_alive.clear()  # garbage collect weak refs

    # -----------------
    #   Path resolver
    # -----------------

    def resolve_dev_server_path(
        self, node: SourceObject, pieces: List[str]
    ) -> Optional[GroupBySource]:
        ''' Dev server only: Resolves path/ -> path/index.html '''
        if not isinstance(node, Record):
            return None
        rv = self._resolver.get(build_url([node.url_path] + pieces))
        if not rv:
            return None
        group, conf = rv
        return GroupBySource(node, group, conf)

    def resolve_virtual_path(
        self, node: SourceObject, pieces: List[str]
    ) -> Optional[GroupBySource]:
        if isinstance(node, Record) and len(pieces) >= 2:
            path = node['_path']  # type: str
            key, grp, *_ = pieces
            for group, conf in self._resolver.values():
                if key == conf.key and path == conf.root:
                    if conf.slugify(group) == grp:
                        return GroupBySource(node, group, conf)
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
        self.env.jinja_env.filters.update(groupby=GroupBySource.of_record)

        # resolve /tag/rss/ -> /tag/rss/index.html (local server only)
        @self.env.urlresolver
        def a(node: SourceObject, parts: List[str]) -> Optional[GroupBySource]:
            return self.creator.resolve_dev_server_path(node, parts)

        # resolve virtual objects in admin UI
        @self.env.virtualpathresolver(VPATH.lstrip('@'))
        def b(node: SourceObject, parts: List[str]) -> Optional[GroupBySource]:
            return self.creator.resolve_virtual_path(node, parts)

    def _load_quick_config(self) -> None:
        ''' Load config file quick listeners. '''
        config = self.get_config()
        for key in config.sections():
            if '.' in key:  # e.g., key.fields and key.key_map
                continue

            watcher = self.creator.add_watcher(key, config)
            split = config.get(key + '.split')  # type: str

            @watcher.grouping()
            def _fn(args: GroupByCallbackArgs) -> Iterator[GroupKey]:
                val = args.field
                if isinstance(val, str):
                    val = val.split(split) if split else [val]  # make list
                if isinstance(val, list):
                    yield from val

    def on_before_build_all(self, builder: Builder, **extra: object) -> None:
        self.creator.clear_previous_results()
        self._load_quick_config()
        # let other plugins register their @groupby.watch functions
        self.emit('before-build-all', groupby=self.creator, builder=builder)
        self.config_dependencies = self.creator.get_dependencies()
        self.creator.make_cluster(builder)

    def on_before_build(self, source: SourceObject, **extra: object) -> None:
        # before-build may be called before before-build-all (issue #1017)
        # make sure it is evaluated immediatelly
        self.creator.queue_now(source)

    def on_after_build_all(self, builder: Builder, **extra: object) -> None:
        self.creator.build_all(builder)

    def on_after_prune(self, builder: Builder, **extra: object) -> None:
        # TODO: find a better way to prune unreferenced elements
        GroupByPruner.prune(builder)
