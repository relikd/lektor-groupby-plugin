# -*- coding: utf-8 -*-
from lektor.pluginsystem import Plugin
from typing import Iterator, Tuple
from datetime import datetime
from lektor_groupby import GroupBy, GroupByCallbackArgs


class SimpleGroupByPlugin(Plugin):
    def on_groupby_before_build_all(self, groupby: GroupBy, builder, **extra):
        watcher = groupby.add_watcher('testB', {
            'root': '/blog',
            'slug': 'simple/{key}/index.html',
            'template': 'example-simple.html',
            'key_obj_fn': 'X.upper() if X else "empty"',
            'replace_none_key': 'unknown',
        })
        watcher.config.set_key_map({'Foo': 'bar'})
        watcher.config.set_fields({'date': datetime.now()})
        watcher.config.set_order_by('-title,body')
        watcher.config.set_pagination(
            enabled=True,
            per_page=1,
            url_suffix='p',
        )

        @watcher.grouping(flatten=True)
        def fn_simple(args: GroupByCallbackArgs) -> Iterator[Tuple[str, dict]]:
            # Yield groups
            value = args.field  # type: list # since model is 'strings' type
            for tag in value:
                yield tag
            # Everything below is just for documentation purposes
            page = args.record  # extract additional info from source
            fieldKey, flowIndex, flowKey = args.key  # or get field index
            if flowIndex is None:
                obj = page[fieldKey]
            else:
                obj = page[fieldKey].blocks[flowIndex].get(flowKey)
            print('[simple] page:', page)
            print('[simple]  obj:', obj)
            print('[simple] ')
