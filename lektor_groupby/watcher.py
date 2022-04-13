from typing import TYPE_CHECKING, Dict, List, Tuple, Any, Union, NamedTuple
from typing import Optional, Callable, Iterator, Generator
from .model import ModelReader
from .util import most_used_key
from .vobj import GroupBySource
if TYPE_CHECKING:
    from lektor.db import Database, Record
    from .config import Config
    from .model import FieldKeyPath


class GroupByCallbackArgs(NamedTuple):
    record: 'Record'
    key: 'FieldKeyPath'
    field: Any  # lektor model data-field value


GroupingCallback = Callable[[GroupByCallbackArgs], Union[
    Iterator[Union[str, Tuple[str, Any]]],
    Generator[Union[str, Tuple[str, Any]], Optional[str], None],
]]


class Watcher:
    '''
    Callback is called with (Record, FieldKeyPath, field-value).
    Callback may yield one or more (group, extra-info) tuples.
    '''

    def __init__(self, config: 'Config') -> None:
        self.config = config
        self._root = self.config.root

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

    def initialize(self, db: 'Database') -> None:
        ''' Reset internal state. You must initialize before each build! '''
        assert callable(self.callback), 'No grouping callback provided.'
        self._model_reader = ModelReader(db, self.config.key, self.flatten)
        self._state = {}  # type: Dict[str, Dict[Record, List[Any]]]
        self._group_map = {}  # type: Dict[str, List[str]]

    def should_process(self, node: 'Record') -> bool:
        ''' Check if record path is being watched. '''
        return node['_path'].startswith(self._root)

    def process(self, record: 'Record') -> None:
        '''
        Will iterate over all record fields and call the callback method.
        Each record is guaranteed to be processed only once.
        '''
        for key, field in self._model_reader.read(record):
            _gen = self.callback(GroupByCallbackArgs(record, key, field))
            try:
                obj = next(_gen)
                while True:
                    if not isinstance(obj, (str, tuple)):
                        raise TypeError(f'Unsupported groupby yield: {obj}')
                    slug = self._persist(record, key, obj)
                    # return slugified group key and continue iteration
                    if isinstance(_gen, Generator) and not _gen.gi_yieldfrom:
                        obj = _gen.send(slug)
                    else:
                        obj = next(_gen)
            except StopIteration:
                del _gen

    def _persist(
        self,
        record: 'Record',
        key: 'FieldKeyPath',
        obj: Union[str, tuple]
    ) -> str:
        ''' Update internal state. Return slugified string. '''
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
        # append extras (or default value)
        if isinstance(obj, tuple):
            self._state[slug][record].append(obj[1])
        else:
            self._state[slug][record].append(key.fieldKey)
        return slug

    def iter_sources(self, root: 'Record') -> Iterator[GroupBySource]:
        ''' Prepare and yield GroupBySource elements. '''
        for key, children in self._state.items():
            group = most_used_key(self._group_map[key])
            yield GroupBySource(root, group, self.config, children=children)
        # cleanup. remove this code if you'd like to iter twice
        del self._model_reader
        del self._state
        del self._group_map

    def __repr__(self) -> str:
        return '<GroupByWatcher key="{}" enabled={} callback={}>'.format(
            self.config.key, self.config.enabled, self.callback)
