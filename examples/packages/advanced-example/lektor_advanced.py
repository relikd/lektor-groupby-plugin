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

        # load config directly (which also tracks dependency)
        watcher = groupby.add_watcher('testC', config, pre_build=True)

        @watcher.grouping()
        def _replace(args: GroupByCallbackArgs) -> Generator[str, str, None]:
            # args.field assumed to be Markdown
            obj = args.field.source
            url_map = {}  # type Dict[str, str]
            for match in regex.finditer(obj):
                tag = match.group(1)
                vobj = yield tag
                if not hasattr(vobj, 'custom_attr'):
                    vobj.custom_attr = []
                # update static custom attribute
                vobj.custom_attr.append(tag)
                url_map[tag] = vobj.url_path
                print('[advanced] slugify:', tag, '->', vobj.key)

            def _fn(match: re.Match) -> str:
                tag = match.group(1)
                return f'<a href="{url_map[tag]}">{tag}</a>'
            args.field.source = regex.sub(_fn, obj)
