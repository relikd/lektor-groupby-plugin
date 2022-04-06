from lektor.db import Database, Record  # typing
from lektor.types.flow import Flow, FlowType
from lektor.utils import bool_from_string

from typing import Set, Dict, List, Tuple, Any, Union, NamedTuple
from typing import Optional, Callable, Iterator, Generator
from .vobj import GroupBySource
from .config import Config
from .util import most_used_key


# -----------------------------------
#              Typing
# -----------------------------------

class FieldKeyPath(NamedTuple):
    fieldKey: str
    flowIndex: Optional[int] = None
    flowKey: Optional[str] = None


class GroupByCallbackArgs(NamedTuple):
    record: Record
    key: FieldKeyPath
    field: Any  # lektor model data-field value


GroupingCallback = Callable[[GroupByCallbackArgs], Union[
    Iterator[Union[str, Tuple[str, Any]]],
    Generator[Union[str, Tuple[str, Any]], Optional[str], None],
]]


# -----------------------------------
#            ModelReader
# -----------------------------------

class GroupByModelReader:
    ''' Find models and flow-models which contain attribute '''

    def __init__(self, db: Database, attrib: str) -> None:
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
    ) -> Iterator[Tuple[FieldKeyPath, Any]]:
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


# -----------------------------------
#              Watcher
# -----------------------------------

class Watcher:
    '''
    Callback is called with (Record, FieldKeyPath, field-value).
    Callback may yield one or more (group, extra-info) tuples.
    '''

    def __init__(self, config: Config) -> None:
        self.config = config
        self.flatten = True
        self.callback = None  # type: GroupingCallback #type:ignore[assignment]

    def grouping(self, flatten: bool = True) \
            -> Callable[[GroupingCallback], None]:
        '''
        Decorator to subscribe to attrib-elements.
        If flatten = False, dont explode FlowType.

        (record, field-key, field) -> (group, extra-info)
        '''
        def _decorator(fn: GroupingCallback) -> None:
            self.flatten = flatten
            self.callback = fn
        return _decorator

    def initialize(self, db: Database) -> None:
        ''' Reset internal state. You must initialize before each build! '''
        assert callable(self.callback), 'No grouping callback provided.'
        self._root = self.config.root
        self._model_reader = GroupByModelReader(db, attrib=self.config.key)
        self._state = {}  # type: Dict[str, Dict[Record, List[Any]]]
        self._group_map = {}  # type: Dict[str, List[str]]
        self._processed = set()  # type: Set[str]

    def should_process(self, node: Record) -> bool:
        ''' Check if record path is being watched. '''
        return node['_path'].startswith(self._root)

    def process(self, record: Record) -> None:
        '''
        Will iterate over all record fields and call the callback method.
        Each record is guaranteed to be processed only once.
        '''
        if record.path in self._processed:
            return
        self._processed.add(record.path)
        for key, field in self._model_reader.read(record, self.flatten):
            _gen = self.callback(GroupByCallbackArgs(record, key, field))
            try:
                obj = next(_gen)
                while True:
                    if not isinstance(obj, (str, tuple)):
                        raise TypeError(f'Unsupported groupby yield: {obj}')
                    slug = self._persist(record, obj)
                    # return slugified group key and continue iteration
                    if isinstance(_gen, Generator) and not _gen.gi_yieldfrom:
                        obj = _gen.send(slug)
                    else:
                        obj = next(_gen)
            except StopIteration:
                del _gen

    def _persist(self, record: Record, obj: Union[str, tuple]) -> str:
        group = obj if isinstance(obj, str) else obj[0]
        slug = self.config.slugify(group)
        # init group-key
        if slug not in self._state:
            self._state[slug] = {}
            self._group_map[slug] = []
        # _group_map is later used to find most used group
        self._group_map[slug].append(group)
        # init group extras
        if record not in self._state[slug]:
            self._state[slug][record] = []
        # (optional) append extra
        if isinstance(obj, tuple):
            self._state[slug][record].append(obj[1])
        return slug

    def iter_sources(self, root: Record) -> Iterator[GroupBySource]:
        ''' Prepare and yield GroupBySource elements. '''
        for key, children in self._state.items():
            group = most_used_key(self._group_map[key])
            yield GroupBySource(root, group, self.config, children=children)
        # cleanup. remove this code if you'd like to iter twice
        del self._model_reader
        del self._state
        del self._group_map
        del self._processed

    def __repr__(self) -> str:
        return '<GroupByWatcher key="{}" enabled={} callback={}>'.format(
            self.config.key, self.config.enabled, self.callback)
