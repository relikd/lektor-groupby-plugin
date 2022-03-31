# -*- coding: utf-8 -*-
from lektor.pluginsystem import Plugin
from lektor.utils import slugify


class SimpleGroupByPlugin(Plugin):
    def on_groupby_after_build_all(self, groupby, builder, **extra):
        @groupby.watch('/blog', 'testB', slug='simple/{group}/index.html',
                       template='example-simple.html', flatten=True)
        def convert_simple_example(args):
            # Yield groups
            value = args.field  # list type since model is 'strings' type
            for tag in value:
                yield slugify(tag), {'val': tag, 'tags_in_page': len(value)}
            # Everything below is just for documentation purposes
            page = args.record  # extract additional info from source
            fieldKey, flowIndex, flowKey = args.key  # or get field index
            if flowIndex is None:
                obj = page[fieldKey]
            else:
                obj = page[fieldKey].blocks[flowIndex].get(flowKey)
            print('page:', page)
            print(' obj:', obj)
            print()
