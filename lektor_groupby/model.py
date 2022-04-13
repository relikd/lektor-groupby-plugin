from lektor.db import Database, Record  # typing
from lektor.types.flow import Flow, FlowType
from lektor.utils import bool_from_string
from typing import Set, Dict, Tuple, Any, NamedTuple, Optional, Iterator


class FieldKeyPath(NamedTuple):
    fieldKey: str
    flowIndex: Optional[int] = None
    flowKey: Optional[str] = None


class ModelReader:
    '''
    Find models and flow-models which contain attribute.
    Flows are either returned directly (flatten=False) or
    expanded so that each flow-block is yielded (flatten=True)
    '''

    def __init__(self, db: Database, attr: str, flatten: bool = False) -> None:
        self.flatten = flatten
        self._flows = {}  # type: Dict[str, Set[str]]
        self._models = {}  # type: Dict[str, Dict[str, str]]
        # find flow blocks containing attribute
        for key, flow in db.flowblocks.items():
            tmp1 = set(f.name for f in flow.fields
                       if bool_from_string(f.options.get(attr, False)))
            if tmp1:
                self._flows[key] = tmp1
        # find models and flow-blocks containing attribute
        for key, model in db.datamodels.items():
            tmp2 = {}  # Dict[str, str]
            for field in model.fields:
                if bool_from_string(field.options.get(attr, False)):
                    tmp2[field.name] = '*'  # include all children
                elif isinstance(field.type, FlowType) and self._flows:
                    # only processed if at least one flow has attr
                    fbs = field.type.flow_blocks
                    # if fbs == None, all flow-blocks are allowed
                    if fbs is None or any(x in self._flows for x in fbs):
                        tmp2[field.name] = '?'  # only some flow blocks
            if tmp2:
                self._models[key] = tmp2

    def read(self, record: Record) -> Iterator[Tuple[FieldKeyPath, Any]]:
        ''' Enumerate all fields of a Record with attrib = True. '''
        assert isinstance(record, Record)
        for r_key, subs in self._models.get(record.datamodel.id, {}).items():
            field = record[r_key]
            if not field:
                continue
            if subs == '*':  # either normal field or flow type (all blocks)
                if self.flatten and isinstance(field, Flow):
                    for i, flow in enumerate(field.blocks):
                        flowtype = flow['_flowblock']
                        for f_key, block in flow._data.items():
                            if f_key.startswith('_'):  # e.g., _flowblock
                                continue
                            yield FieldKeyPath(r_key, i, f_key), block
                else:
                    yield FieldKeyPath(r_key), field
            else:  # always flow type (only some blocks)
                for i, flow in enumerate(field.blocks):
                    flowtype = flow['_flowblock']
                    for f_key in self._flows.get(flowtype, []):
                        yield FieldKeyPath(r_key, i, f_key), flow[f_key]
