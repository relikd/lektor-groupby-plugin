# -*- coding: utf-8 -*-
from lektor.pluginsystem import Plugin
from typing import Generator
import re
from lektor_groupby import GroupBy, GroupByCallbackArgs


class AdvancedGroupByPlugin(Plugin):
    def on_groupby_before_build_all(self, groupby: GroupBy, builder, **extra):
        # load config
        config = self.get_config()
        regex = config.get('testC.pattern.match')
        try:
            regex = re.compile(regex)
        except Exception as e:
            print('inlinetags.regex not valid: ' + str(e))
            return

        watcher = groupby.add_watcher('testC', config)  # tracks dependency

        @watcher.grouping()
        def _replace(args: GroupByCallbackArgs) -> Generator[str, str, None]:
            # args.field assumed to be Markdown
            obj = args.field.source
            slugify_map = {}  # type Dict[str, str]
            for match in regex.finditer(obj):
                tag = match.group(1)
                key = yield tag
                print('[advanced] slugify:', tag, '->', key)
                slugify_map[tag] = key

            def _fn(match: re.Match) -> str:
                tag = match.group(1)
                return f'<a href="/advanced/{slugify_map[tag]}/">{tag}</a>'
            args.field.source = regex.sub(_fn, obj)
