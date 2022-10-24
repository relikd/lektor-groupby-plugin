from lektor.reporter import reporter, style

from typing import List, Dict


def report_config_error(key: str, field: str, val: str, e: Exception) -> None:
    ''' Send error message to Lektor reporter. Indicate which field is bad. '''
    msg = '[ERROR] invalid config for [{}.{}] = "{}",  Error: {}'.format(
        key, field, val, repr(e))
    try:
        reporter._write_line(style(msg, fg='red'))
    except Exception:
        print(msg)  # fallback in case Lektor API changes


def most_used_key(keys: List[str]) -> str:
    ''' Find string with most occurrences. '''
    if len(keys) < 3:
        return keys[0] if keys else ''  # TODO: first vs last occurrence
    best_count = 0
    best_key = ''
    tmp = {}  # type: Dict[str, int]
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
