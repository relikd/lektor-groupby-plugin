from lektor.reporter import reporter, style
from typing import List, Dict, Optional, TypeVar
from typing import Callable, Any, Union, Generic

T = TypeVar('T')


def report_config_error(key: str, field: str, val: str, e: Exception) -> None:
    ''' Send error message to Lektor reporter. Indicate which field is bad. '''
    msg = '[ERROR] invalid config for [{}.{}] = "{}",  Error: {}'.format(
        key, field, val, repr(e))
    try:
        reporter._write_line(style(msg, fg='red'))
    except Exception:
        print(msg)  # fallback in case Lektor API changes


def most_used_key(keys: List[T]) -> Optional[T]:
    ''' Find string with most occurrences. '''
    if len(keys) < 3:
        return keys[0] if keys else None  # TODO: first vs last occurrence
    best_count = 0
    best_key = None
    tmp = {}  # type: Dict[T, int]
    for k in keys:
        num = (tmp[k] + 1) if k in tmp else 1
        tmp[k] = num
        if num > best_count:  # TODO: (>) vs (>=), first vs last occurrence
            best_count = num
            best_key = k
    return best_key


def split_strip(data: str, delimiter: str = ',') -> List[str]:
    ''' Split by delimiter and strip each str separately. Omit if empty. '''
    ret = []
    for x in data.split(delimiter):
        x = x.strip()
        if x:
            ret.append(x)
    return ret


def insert_before_ext(data: str, ins: str, delimiter: str = '.') -> str:
    ''' Insert text before last index of delimeter (or at the end). '''
    assert delimiter in data, 'Could not insert before delimiter: ' + delimiter
    idx = data.rindex(delimiter)
    return data[:idx] + ins + data[idx:]


def build_url(parts: List[str]) -> str:
    ''' Build URL similar to lektor.utils.build_url '''
    url = ''
    for comp in parts:
        txt = str(comp).strip('/')
        if txt:
            url += '/' + txt
    if '.' not in url.rsplit('/', 1)[-1]:
        url += '/'
    return url or '/'
