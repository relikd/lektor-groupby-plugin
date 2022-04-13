'''
Static collector for build-artifact urls.
All non-tracked VPATH-urls will be pruned after build.
'''
from lektor.reporter import reporter  # report_pruned_artifact
from lektor.utils import prune_file_and_folder
from typing import TYPE_CHECKING, Set, Iterable
if TYPE_CHECKING:
    from lektor.builder import Builder


def _normalize_url_cache(url_cache: Iterable[str]) -> Set[str]:
    cache = set()
    for url in url_cache:
        if url.endswith('/'):
            url += 'index.html'
        cache.add(url.lstrip('/'))
    return cache


def prune(builder: 'Builder', vpath: str, url_cache: Iterable[str]) -> None:
    '''
    Remove previously generated, unreferenced Artifacts.
    All urls in url_cache must have a trailing "/index.html" (instead of "/")
    and also, no leading slash, "blog/index.html" instead of "/blog/index.html"
    '''
    vpath = '@' + vpath.lstrip('@')  # just in case of user error
    dest_path = builder.destination_path
    url_cache = _normalize_url_cache(url_cache)
    con = builder.connect_to_database()
    try:
        with builder.new_build_state() as build_state:
            for url, file in build_state.iter_artifacts():
                if url.lstrip('/') in url_cache:
                    continue  # generated in this build-run
                infos = build_state.get_artifact_dependency_infos(url, [])
                for artifact_name, _ in infos:
                    if vpath not in artifact_name:
                        continue  # we only care about our Virtuals
                    reporter.report_pruned_artifact(url)
                    prune_file_and_folder(file.filename, dest_path)
                    build_state.remove_artifact(url)
                    break  # there is only one VPATH-entry per source
    finally:
        con.close()
