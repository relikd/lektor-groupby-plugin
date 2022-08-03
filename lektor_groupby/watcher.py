from typing import TYPE_CHECKING, Dict, List, Tuple, Any, Union, NamedTuple
from typing import Optional, Callable, Iterator, Generator
from .backref import VGroups
from .model import ModelReader
from .vobj import GroupBySource
if TYPE_CHECKING:
    from lektor.db import Pad, Record
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

    def initialize(self, pad: 'Pad') -> None:
        ''' Reset internal state. You must initialize before each build! '''
        assert callable(self.callback), 'No grouping callback provided.'
        self._model_reader = ModelReader(pad.db, self.config.key, self.flatten)
        self._root_record = {}  # type: Dict[str, Record]
        self._state = {}  # type: Dict[str, Dict[str, GroupBySource]]
        for alt in pad.config.iter_alternatives():
            self._root_record[alt] = pad.get(self._root, alt=alt)
            self._state[alt] = {}

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
                group = next(_gen)
                while True:
                    if not isinstance(group, str):
                        raise TypeError(f'Unsupported groupby yield: {group}')
                    slug = self._persist(record, key, group)
                    # return slugified group key and continue iteration
                    if isinstance(_gen, Generator) and not _gen.gi_yieldfrom:
                        group = _gen.send(slug)
                    else:
                        group = next(_gen)
            except StopIteration:
                del _gen

    def _persist(self, record: 'Record', key: 'FieldKeyPath', group: str) \
            -> str:
        ''' Update internal state. Return slugified string. '''
        alt = record.alt
        slug = self.config.slugify(group)
        if slug not in self._state[alt]:
            src = GroupBySource(self._root_record[alt], slug)
            self._state[alt][slug] = src
        else:
            src = self._state[alt][slug]

        src.append_child(record, group)
        # reverse reference
        VGroups.of(record).add(key, src)
        return slug

    def iter_sources(self, root: 'Record') -> Iterator[GroupBySource]:
        ''' Prepare and yield GroupBySource elements. '''
        for vobj_list in self._state.values():
            for vobj in vobj_list.values():
                yield vobj.finalize(self.config)
        # cleanup. remove this code if you'd like to iter twice
        del self._model_reader
        del self._root_record
        del self._state

    def __repr__(self) -> str:
        return '<GroupByWatcher key="{}" enabled={} callback={}>'.format(
            self.config.key, self.config.enabled, self.callback)
