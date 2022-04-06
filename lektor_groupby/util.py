from lektor.reporter import reporter, style

from typing import List
from itertools import groupby


def report_config_error(key: str, field: str, val: str, e: Exception) -> None:
    ''' Send error message to Lektor reporter. Indicate which field is bad. '''
    msg = '[ERROR] invalid config for [{}.{}] = "{}",  Error: {}'.format(
        key, field, val, repr(e))
    try:
        reporter._write_line(style(msg, fg='red'))
    except Exception:
        print(msg)  # fallback in case Lektor API changes


def most_used_key(keys: List[str]) -> str:
    if len(keys) < 3:
        return keys[0]  # TODO: first vs last occurrence
    best_count = 0
    best_key = ''
    for key, itr in groupby(keys):
        count = sum(1 for i in itr)
        if count > best_count:  # TODO: (>) vs (>=), first vs last occurrence
            best_count = count
            best_key = key
    return best_key
