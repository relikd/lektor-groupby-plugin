from lektor.reporter import reporter, style


def report_config_error(key: str, field: str, val: str, e: Exception) -> None:
    ''' Send error message to Lektor reporter. Indicate which field is bad. '''
    msg = '[ERROR] invalid config for [{}.{}] = "{}",  Error: {}'.format(
        key, field, val, repr(e))
    try:
        reporter._write_line(style(msg, fg='red'))
    except Exception:
        print(msg)  # fallback in case Lektor API changes
