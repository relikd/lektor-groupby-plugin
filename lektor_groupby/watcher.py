from typing import (
    TYPE_CHECKING, Dict, List, Any, Union, NamedTuple,
    Optional, Callable, Iterator, Generator
)
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
    Iterator[Any],
    Generator[Any, Optional[GroupBySource], None],
]]


class Watcher:
    '''
    Callback is called with (Record, FieldKeyPath, field-value).
    Callback may yield 0-n objects.
    '''

    def __init__(self, config: 'Config') -> None:
        self.config = config
        self._root = self.config.root

    def grouping(self, flatten: bool = True) \
            -> Callable[[GroupingCallback], None]:
        '''
        Decorator to subscribe to attrib-elements.
        If flatten = False, dont explode FlowType.

        (record, field-key, field) -> value
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
        self._state = {}  # type: Dict[str, Dict[Optional[str], GroupBySource]]
        self._rmmbr = []  # type: List[Record]
        for alt in pad.config.iter_alternatives():
            self._root_record[alt] = pad.get(self._root, alt=alt)
            self._state[alt] = {}

    def should_process(self, node: 'Record') -> bool:
        ''' Check if record path is being watched. '''
        return str(node['_path']).startswith(self._root)

    def process(self, record: 'Record') -> None:
        '''
        Will iterate over all record fields and call the callback method.
        Each record is guaranteed to be processed only once.
        '''
        for key, field in self._model_reader.read(record):
            args = GroupByCallbackArgs(record, key, field)
            _gen = self.callback(args)
            try:
                key_obj = next(_gen)
                while True:
                    if self.config.key_obj_fn:
                        vobj = self._persist_multiple(args, key_obj)
                    else:
                        vobj = self._persist(args, key_obj)
                    # return groupby virtual object and continue iteration
                    if isinstance(_gen, Generator) and not _gen.gi_yieldfrom:
                        key_obj = _gen.send(vobj)
                    else:
                        key_obj = next(_gen)
            except StopIteration:
                del _gen

    def _persist_multiple(self, args: 'GroupByCallbackArgs', obj: Any) \
            -> Optional[GroupBySource]:
        # if custom key mapping function defined, use that first
        res = self.config.eval_key_obj_fn(on=args.record,
                                          context={'X': obj, 'ARGS': args})
        if isinstance(res, (list, tuple)):
            for k in res:
                self._persist(args, k)  # 1-to-n replacement
            return None
        return self._persist(args, res)  # normal & null replacement

    def _persist(self, args: 'GroupByCallbackArgs', obj: Any) \
            -> Optional[GroupBySource]:
        ''' Update internal state. Return grouping parent. '''
        if not isinstance(obj, (str, bool, int, float)) and obj is not None:
            raise ValueError(
                'Unsupported groupby yield type for [{}]:'
                ' {} (expected str, got {})'.format(
                    self.config.key, obj, type(obj).__name__))

        if obj is None:
            # if obj is not set, test if config.replace_none_key is set
            slug = self.config.replace_none_key
            obj = slug
        else:
            # if obj is set, apply config.key_map  (convert int -> str)
            slug = self.config.slugify(str(obj)) or None
        # if neither custom mapping succeeded, do not process further
        if not slug or obj is None:
            return None
        # update internal object storage
        alt = args.record.alt
        if slug not in self._state[alt]:
            src = GroupBySource(self._root_record[alt], slug, self.config)
            self._state[alt][slug] = src
        else:
            src = self._state[alt][slug]

        src.append_child(args.record, obj)
        # reverse reference
        VGroups.of(args.record).add(args.key, src)
        return src

    def remember(self, record: 'Record') -> None:
        self._rmmbr.append(record)

    def iter_sources(self) -> Iterator[GroupBySource]:
        ''' Prepare and yield GroupBySource elements. '''
        for x in self._rmmbr:
            self.process(x)
        del self._rmmbr
        for vobj_list in self._state.values():
            for vobj in vobj_list.values():
                yield vobj.finalize()
        # cleanup. remove this code if you'd like to iter twice
        del self._model_reader
        del self._root_record
        del self._state

    def __repr__(self) -> str:
        return '<GroupByWatcher key="{}" enabled={}>'.format(
            self.config.key, self.config.enabled)
