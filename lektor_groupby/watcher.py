from lektor.db import Database, Record  # typing
from lektor.types.flow import Flow, FlowType
from lektor.utils import bool_from_string

from typing import Set, Dict, List, Tuple, Any, Union, NamedTuple
from typing import Optional, Callable, Iterable, Iterator, Generator
from .vobj import GroupBySource
from .config import Config


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
#               State
# -----------------------------------

class GroupByState:
    ''' Store and update a groupby build state. {group: {record: [extras]}} '''

    def __init__(self) -> None:
        self.state = {}  # type: Dict[str, Dict[Record, List[Any]]]
        self._processed = set()  # type: Set[Record]

    def __contains__(self, record: Record) -> bool:
        ''' Returns True if record was already processed. '''
        return record.path in self._processed

    def items(self) -> Iterable[Tuple[str, Dict[Record, List[Any]]]]:
        ''' Iterable with (group, {record: [extras]}) tuples. '''
        return self.state.items()

    def add(self, record: Record, sub_groups: Dict[str, List[Any]]) -> None:
        ''' Append groups if not processed already. {group: [extras]} '''
        if record.path not in self._processed:
            self._processed.add(record.path)
            for group, extras in sub_groups.items():
                if group in self.state:
                    self.state[group][record] = extras
                else:
                    self.state[group] = {record: extras}


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
        tmp = {}  # type: Dict[str, List[Any]] # {group: [extras]}
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
