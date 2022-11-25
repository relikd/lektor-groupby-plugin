# adapting https://github.com/dairiki/lektorlib/blob/master/lektorlib/query.py
from lektor.constants import PRIMARY_ALT
from lektor.db import Query  # subclass
from typing import TYPE_CHECKING, List, Optional, Generator, Iterable
if TYPE_CHECKING:
    from lektor.db import Record, Pad


class FixedRecordsQuery(Query):
    def __init__(
        self, pad: 'Pad', child_paths: Iterable[str], alt: str = PRIMARY_ALT
    ):
        ''' Query with a pre-defined list of children of type Record. '''
        super().__init__('/', pad, alt=alt)
        self.__child_paths = [x.lstrip('/') for x in child_paths]

    def _get(
        self, path: str, persist: bool = True, page_num: Optional[int] = None
    ) -> Optional['Record']:
        ''' Internal getter for a single Record. '''
        if path not in self.__child_paths:
            return None
        if page_num is None:
            page_num = self._page_num
        return self.pad.get(  # type: ignore[no-any-return]
            path, alt=self.alt, page_num=page_num, persist=persist)

    def _iterate(self) -> Generator['Record', None, None]:
        ''' Iterate over internal set of Record elements. '''
        # ignore self record dependency from super()
        for path in self.__child_paths:
            record = self._get(path, persist=False)
            if record is None:
                if self._page_num is not None:
                    # Sanity check: ensure the unpaginated version exists
                    unpaginated = self._get(path, persist=False, page_num=None)
                    if unpaginated is not None:
                        # Requested explicit page_num, but source does not
                        # support pagination.  Punt and skip it.
                        continue
                raise RuntimeError('could not load source for ' + path)

            is_attachment = getattr(record, 'is_attachment', False)
            if self._include_attachments and not is_attachment \
                    or self._include_pages and is_attachment:
                continue
            if self._matches(record):
                yield record

    def get_order_by(self) -> Optional[List[str]]:
        ''' Return list of attribute strings for sort order. '''
        # ignore datamodel ordering from super()
        return self._order_by  # type: ignore[no-any-return]

    def count(self) -> int:
        ''' Count matched objects. '''
        if self._pristine:
            return len(self.__child_paths)
        return super().count()  # type: ignore[no-any-return]

    @property
    def total(self) -> int:
        ''' Return total entries count (without any filter). '''
        return len(self.__child_paths)

    def get(self, path: str, page_num: Optional[int] = None) \
            -> Optional['Record']:
        ''' Return Record with given path '''
        if path in self.__child_paths:
            return self._get(path, page_num=page_num)
        return None

    def __bool__(self) -> bool:
        if self._pristine:
            return len(self.__child_paths) > 0
        return super().__bool__()

    if TYPE_CHECKING:
        def request_page(self, page_num: Optional[int]) -> 'FixedRecordsQuery':
            ...
