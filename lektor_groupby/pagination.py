from lektor import datamodel
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from lektor.pagination import Pagination
    from lektor.sourceobj import SourceObject


class PaginationConfig(datamodel.PaginationConfig):
    # because original method does not work for virtual sources.
    @staticmethod
    def get_record_for_page(source: 'SourceObject', page_num: int) -> Any:
        for_page = getattr(source, '__for_page__', None)
        if callable(for_page):
            return for_page(page_num)
        return datamodel.PaginationConfig.get_record_for_page(source, page_num)

    if TYPE_CHECKING:
        def get_pagination_controller(self, source: 'SourceObject') \
                -> 'Pagination':
            ...
