'''
Usage:
  VirtualSourceObject.produce_artifacts()
    -> remember url and later supply as `current_urls`
  VirtualSourceObject.build_artifact()
    -> `get_ctx().record_virtual_dependency(VirtualPruner())`
'''
from lektor.reporter import reporter  # report_pruned_artifact
from lektor.sourceobj import VirtualSourceObject  # subclass
from lektor.utils import prune_file_and_folder
import os
from typing import TYPE_CHECKING, Set, List, Iterable
if TYPE_CHECKING:
    from lektor.builder import Builder
    from sqlite3 import Connection


class VirtualPruner(VirtualSourceObject):
    ''' Indicate that a generated VirtualSourceObject has pruning support. '''
    VPATH = '/@VirtualPruner'

    def __init__(self) -> None:
        self._path = VirtualPruner.VPATH  # if needed, add suffix variable

    @property
    def path(self) -> str:  # type: ignore[override]
        return self._path


def prune(builder: 'Builder', current_urls: Iterable[str]) -> None:
    ''' Removes previously generated, but now unreferenced Artifacts. '''
    dest_dir = builder.destination_path
    con = builder.connect_to_database()
    try:
        previous = _query_prunable(con)
        current = _normalize_urls(current_urls)
        to_be_pruned = previous.difference(current)
        for file in to_be_pruned:
            reporter.report_pruned_artifact(file)  # type: ignore
            prune_file_and_folder(os.path.join(
                dest_dir, file.strip('/').replace('/', os.path.sep)), dest_dir)
        # if no exception raised, update db to remove obsolete references
        _prune_db_artifacts(con, list(to_be_pruned))
    finally:
        con.close()


# ---------------------------
#   Internal helper methods
# ---------------------------

def _normalize_urls(urls: Iterable[str]) -> Set[str]:
    cache = set()
    for url in urls:
        if url.endswith('/'):
            url += 'index.html'
        cache.add(url.lstrip('/'))
    return cache


def _query_prunable(conn: 'Connection') -> Set[str]:
    ''' Query database for artifacts that have the VirtualPruner dependency '''
    cur = conn.cursor()
    cur.execute('SELECT artifact FROM artifacts WHERE source = ?',
                [VirtualPruner.VPATH])
    return set(x for x, in cur.fetchall())


def _prune_db_artifacts(conn: 'Connection', urls: List[str]) -> None:
    ''' Remove obsolete artifact references from database. '''
    MAX_VARS = 999  # Default SQLITE_MAX_VARIABLE_NUMBER.
    cur = conn.cursor()
    for i in range(0, len(urls), MAX_VARS):
        batch = urls[i: i + MAX_VARS]
        cur.execute('DELETE FROM artifacts WHERE artifact in ({})'.format(
            ','.join(['?'] * len(batch))), batch)
        conn.commit()
