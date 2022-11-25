from lektor import datamodel
from typing import TYPE_CHECKING, Any, Dict
if TYPE_CHECKING:
    from lektor.environment import Environment
    from lektor.pagination import Pagination
    from lektor.sourceobj import SourceObject


class PaginationConfig(datamodel.PaginationConfig):
    # because original method does not work for virtual sources.
    def __init__(self, env: 'Environment', config: Dict[str, Any], total: int):
        super().__init__(env, **config)
        self._total_items_count = total

    @staticmethod
    def get_record_for_page(record: 'SourceObject', page_num: int) -> Any:
        for_page = getattr(record, '__for_page__', None)
        if callable(for_page):
            return for_page(page_num)
        return datamodel.PaginationConfig.get_record_for_page(record, page_num)

    def count_total_items(self, record: 'SourceObject') -> int:
        ''' Override super() to prevent a record.children query. '''
        return self._total_items_count

    if TYPE_CHECKING:
        def get_pagination_controller(self, record: 'SourceObject') \
                -> 'Pagination':
            ...
