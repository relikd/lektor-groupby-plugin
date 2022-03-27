# -*- coding: utf-8 -*-
import lektor.db  # typing
from lektor.build_programs import BuildProgram
from lektor.builder import Artifact, Builder  # typing
from lektor.pluginsystem import Plugin
from lektor.reporter import reporter
from lektor.sourceobj import SourceObject, VirtualSourceObject
from lektor.types.flow import Flow, FlowType
from lektor.utils import bool_from_string, build_url, prune_file_and_folder
# for quick config
from lektor.utils import slugify

from typing import \
    NewType, NamedTuple, Tuple, Dict, Set, List, Optional, Iterator, Callable

VPATH = '@groupby'  # potentially unsafe. All matching entries are pruned.


# -----------------------------------
#            Typing
# -----------------------------------
FieldValue = NewType('FieldValue', object)  # lektor model data-field value
AttributeKey = NewType('AttributeKey', str)  # attribute of lektor model
GroupKey = NewType('GroupKey', str)  # key of group-by


class FieldKeyPath(NamedTuple):
    fieldKey: str
    flowIndex: Optional[int] = None
    flowKey: Optional[str] = None


class GroupByCallbackArgs(NamedTuple):
    record: lektor.db.Record
    key: FieldKeyPath
    field: FieldValue


class GroupByCallbackYield(NamedTuple):
    key: GroupKey
    extra: object


GroupingCallback = Callable[[GroupByCallbackArgs],
                            Iterator[GroupByCallbackYield]]


class GroupProducer(NamedTuple):
    attribute: AttributeKey
    func: GroupingCallback
    flatten: bool = True
    slug: Optional[str] = None
    template: Optional[str] = None
    dependency: Optional[str] = None


class GroupComponent(NamedTuple):
    record: lektor.db.Record
    extra: object


# -----------------------------------
#            Actual logic
# -----------------------------------


class GroupBySource(VirtualSourceObject):
    '''
    Holds information for a single group/cluster.
    This object is accessible in your template file.
    Attributes: record, attribute, group, children, template, slug

    :DEFAULTS:
    template: "groupby-attribute.html"
    slug: "{attrib}/{group}/index.html"
    '''

    def __init__(
        self,
        record: lektor.db.Record,
        attribute: AttributeKey,
        group: GroupKey,
        children: List[GroupComponent] = [],
        slug: Optional[str] = None,  # default: "{attrib}/{group}/index.html"
        template: Optional[str] = None,  # default: "groupby-attribute.html"
        dependency: Optional[str] = None
    ):
        super().__init__(record)
        self.attribute = attribute
        self.group = group
        self.children = children
        self.template = template or 'groupby-{}.html'.format(self.attribute)
        self.dependency = dependency
        # custom user path
        slug = slug or '{attrib}/{group}/index.html'
        slug = slug.replace('{attrib}', self.attribute)
        slug = slug.replace('{group}', self.group)
        if slug.endswith('/index.html'):
            slug = slug[:-10]
        self.slug = slug

    @property
    def path(self) -> str:
        # Used in VirtualSourceInfo, used to prune VirtualObjects
        return build_url([self.record.path, VPATH, self.attribute, self.group])

    @property
    def url_path(self) -> str:
        return build_url([self.record.path, self.slug])

    def iter_source_filenames(self) -> Iterator[str]:
        if self.dependency:
            yield self.dependency
        for record, _ in self.children:
            yield from record.iter_source_filenames()

    def __str__(self) -> str:
        txt = '<GroupBySource'
        for x in ['attribute', 'group', 'template', 'slug']:
            txt += ' {}="{}"'.format(x, getattr(self, x))
        return txt + ' children={}>'.format(len(self.children))


class GroupByBuildProgram(BuildProgram):
    ''' Generates Build-Artifacts and write files. '''

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


# -----------------------------------
#           Main Component
# -----------------------------------


class GroupByCreator:
    '''
    Process all children with matching conditions under specified page.
    Creates a grouping of pages with similar (self-defined) attributes.
    The grouping is performed only once per build (or manually invoked).
    '''

    def __init__(self):
        self._flows: Dict[AttributeKey, Dict[str, Set[str]]] = {}
        self._models: Dict[AttributeKey, Dict[str, Dict[str, str]]] = {}
        self._func: Dict[str, Set[GroupProducer]] = {}
        self._resolve_map: Dict[str, GroupBySource] = {}  # only for server
        self._watched_once: Set[GroupingCallback] = set()

    # --------------
    #   Initialize
    # --------------

    def initialize(self, db: lektor.db):
        self._flows.clear()
        self._models.clear()
        self._resolve_map.clear()
        for prod_list in self._func.values():
            for producer in prod_list:
                self._register(db, producer.attribute)

    def _register(self, db: lektor.db, attrib: AttributeKey) -> None:
        ''' Preparation: find models and flow-models which contain attrib '''
        if attrib in self._flows or attrib in self._models:
            return  # already added
        # find flow blocks with attrib
        _flows = {}  # Dict[str, Set[str]]
        for key, flow in db.flowblocks.items():
            tmp1 = set(f.name for f in flow.fields
                       if bool_from_string(f.options.get(attrib, False)))
            if tmp1:
                _flows[key] = tmp1
        # find models with attrib or flow-blocks containing attrib
        _models = {}  # Dict[str, Dict[str, str]]
        for key, model in db.datamodels.items():
            tmp2 = {}  # Dict[str, str]
            for field in model.fields:
                if bool_from_string(field.options.get(attrib, False)):
                    tmp2[field.name] = '*'  # include all children
                elif isinstance(field.type, FlowType):
                    if any(x in _flows for x in field.type.flow_blocks):
                        tmp2[field.name] = '?'  # only some flow blocks
            if tmp2:
                _models[key] = tmp2

        self._flows[attrib] = _flows
        self._models[attrib] = _models

    # ----------------
    #   Add Observer
    # ----------------

    def watch(
        self,
        root: str,
        attrib: AttributeKey, *,
        flatten: bool = True,  # if False, dont explode FlowType
        slug: Optional[str] = None,  # default: "{attrib}/{group}/index.html"
        template: Optional[str] = None,  # default: "groupby-attrib.html"
        dependency: Optional[str] = None
    ) -> Callable[[GroupingCallback], None]:
        '''
        Decorator to subscribe to attrib-elements. Converter for groupby().
        Refer to groupby() for further details.

        (record, field-key, field) -> (group-key, extra-info)

        :DEFAULTS:
        template: "groupby-attrib.html"
        slug: "{attrib}/{group}/index.html"
        '''
        root = root.rstrip('/') + '/'

        def _decorator(fn: GroupingCallback):
            if root not in self._func:
                self._func[root] = set()
            self._func[root].add(
                GroupProducer(attrib, fn, flatten, template, slug, dependency))

        return _decorator

    def watch_once(self, *args, **kwarg) -> Callable[[GroupingCallback], None]:
        ''' Same as watch() but listener is auto removed after build. '''
        def _decorator(fn: GroupingCallback):
            self._watched_once.add(fn)
            self.watch(*args, **kwarg)(fn)
        return _decorator

    def remove_watch_once(self) -> None:
        ''' Remove all watch-once listeners. '''
        for k, v in self._func.items():
            not_once = {x for x in v if x.func not in self._watched_once}
            self._func[k] = not_once
        self._watched_once.clear()

    # ----------
    #   Helper
    # ----------

    def iter_record_fields(
        self,
        source: lektor.db.Record,
        attrib: AttributeKey,
        flatten: bool = False
    ) -> Iterator[Tuple[FieldKeyPath, FieldValue]]:
        ''' Enumerate all fields of a lektor.db.Record with attrib = True '''
        assert isinstance(source, lektor.db.Record)
        _flows = self._flows.get(attrib, {})
        _models = self._models.get(attrib, {})

        for r_key, subs in _models.get(source.datamodel.id, {}).items():
            if subs == '*':  # either normal field or flow type (all blocks)
                field = source[r_key]
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
                for i, flow in enumerate(source[r_key].blocks):
                    flowtype = flow['_flowblock']
                    for f_key in _flows.get(flowtype, []):
                        yield FieldKeyPath(r_key, i, f_key), flow[f_key]

    def groupby(
        self,
        attrib: AttributeKey,
        root: lektor.db.Record,
        func: GroupingCallback,
        flatten: bool = False,
        incl_attachments: bool = True
    ) -> Dict[GroupKey, List[GroupComponent]]:
        '''
        Traverse selected root record with all children and group by func.
        Func is called with (record, FieldKeyPath, FieldValue).
        Func may yield one or more (group-key, extra-info) tuples.

        return {'group-key': [(record, extra-info), ...]}
        '''
        assert callable(func), 'no GroupingCallback provided'
        assert isinstance(root, lektor.db.Record)
        tmap = {}  # type: Dict[GroupKey, List[GroupComponent]]
        recursive_list = [root]  # type: List[lektor.db.Record]
        while recursive_list:
            record = recursive_list.pop()
            if hasattr(record, 'children'):
                # recursive_list += record.children
                recursive_list.extend(record.children)
            if incl_attachments and hasattr(record, 'attachments'):
                # recursive_list += record.attachments
                recursive_list.extend(record.attachments)
            for key, field in self.iter_record_fields(record, attrib, flatten):
                for ret in func(GroupByCallbackArgs(record, key, field)) or []:
                    assert isinstance(ret, (tuple, list)), \
                        'Must return tuple (group-key, extra-info)'
                    group_key, extras = ret
                    if group_key not in tmap:
                        tmap[group_key] = []
                    tmap[group_key].append(GroupComponent(record, extras))
        return tmap

    # -----------------
    #   Create groups
    # -----------------

    def should_process(self, node: SourceObject) -> bool:
        ''' Check if record path is being watched. '''
        return isinstance(node, lektor.db.Record) \
            and node.url_path in self._func

    def make_cluster(self, root: lektor.db.Record) -> Iterator[GroupBySource]:
        ''' Group by attrib and build Artifacts. '''
        assert isinstance(root, lektor.db.Record)
        for attr, fn, fl, temp, slug, dep in self._func.get(root.url_path, []):
            groups = self.groupby(attr, root, func=fn, flatten=fl)
            for group_key, children in groups.items():
                obj = GroupBySource(root, attr, group_key, children,
                                    template=temp, slug=slug, dependency=dep)
                self.track_dev_server_path(obj)
                yield obj

    # ------------------
    #   Path resolving
    # ------------------

    def resolve_virtual_path(
        self, node: SourceObject, pieces: List[str]
    ) -> Optional[GroupBySource]:
        ''' Given a @VPATH/attrib/groupkey path, determine url path. '''
        if len(pieces) >= 2:
            attrib: AttributeKey = pieces[0]  # type: ignore[assignment]
            group: GroupKey = pieces[1]  # type: ignore[assignment]
            for attr, _, _, _, slug, _ in self._func.get(node.url_path, []):
                if attr == attrib:
                    # TODO: do we need to provide the template too?
                    return GroupBySource(node, attr, group, slug=slug)
        return None

    def track_dev_server_path(self, sender: GroupBySource) -> None:
        ''' Dev server only: Add target path to reverse artifact url lookup '''
        self._resolve_map[sender.url_path] = sender

    def resolve_dev_server_path(
        self, node: SourceObject, pieces: List[str]
    ) -> Optional[GroupBySource]:
        ''' Dev server only: Resolve actual url to virtual obj. '''
        return self._resolve_map.get(build_url([node.url_path] + pieces))


# -----------------------------------
#           Plugin Entry
# -----------------------------------


class GroupByPlugin(Plugin):
    name = 'GroupBy Plugin'
    description = 'Cluster arbitrary records with field attribute keyword.'

    def on_setup_env(self, **extra):
        self.creator = GroupByCreator()
        self.env.add_build_program(GroupBySource, GroupByBuildProgram)
        # let other plugins register their @groupby.watch functions
        self.emit('init', groupby=self.creator, **extra)

        # resolve /tag/rss/ -> /tag/rss/index.html (local server only)
        @self.env.urlresolver
        def groupby_path_resolver(node, pieces):
            if self.creator.should_process(node):
                return self.creator.resolve_dev_server_path(node, pieces)

        # use VPATH in templates: {{ '/@groupby/attrib/group' | url }}
        @self.env.virtualpathresolver(VPATH.lstrip('@'))
        def groupby_virtualpath_resolver(node, pieces):
            if self.creator.should_process(node):
                return self.creator.resolve_virtual_path(node, pieces)

        # injection to generate GroupBy nodes when processing artifacts
        # @self.env.generator
        # def groupby_generator(node):
        #     if self.creator.should_process(node):
        #         yield from self.creator.make_cluster(node)

    def _quick_config(self):
        config = self.get_config()
        for attrib in config.sections():
            sect = config.section_as_dict(attrib)
            root = sect.get('root', '/')
            slug = sect.get('slug')
            temp = sect.get('template')
            split = sect.get('split')

            @self.creator.watch_once(root, attrib, template=temp, slug=slug,
                                     dependency=self.config_filename)
            def _fn(args):
                val = args.field
                if isinstance(val, str):
                    val = val.split(split) if split else [val]  # make list
                if isinstance(val, list):
                    for tag in val:
                        yield slugify(tag), tag

    def on_before_build_all(self, builder, **extra):
        # let other plugins register their @groupby.watch_once functions
        self.emit('init-once', groupby=self.creator, builder=builder, **extra)
        # load config file quick listeners (before initialize!)
        self._quick_config()
        # parse all models to detect attribs of listeners
        self.creator.initialize(builder.pad.db)

    def on_before_build(self, builder, build_state, source, prog, **extra):
        # Injection to create GroupBy nodes before parent node is built.
        # Use this callback (not @generator) to modify parent beforehand.
        # Relevant for the root page which is otherwise build before GroupBy.
        if self.creator.should_process(source):
            for vobj in self.creator.make_cluster(source):
                builder.build(vobj)

    def on_after_build_all(self, builder, **extra):
        # remove all quick listeners (will be added again in the next build)
        self.creator.remove_watch_once()

    def on_after_prune(self, builder, **extra):
        # TODO: find better way to prune unreferenced elements
        GroupByPruner.prune(builder)
