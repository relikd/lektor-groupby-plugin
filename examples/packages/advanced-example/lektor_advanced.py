# -*- coding: utf-8 -*-
from lektor.pluginsystem import Plugin
from lektor.utils import slugify
import re


class AdvancedGroupByPlugin(Plugin):
    def on_groupby_before_build_all(self, groupby, builder, **extra):
        # load config
        regex = self.get_config().get('match')
        try:
            regex = re.compile(regex)
        except Exception as e:
            print('inlinetags.regex not valid: ' + str(e))
            return

        # since we load and use a config file, we need to track the dependency
        @groupby.depends_on(self.config_filename)
        @groupby.watch('/', 'testC', slug='advanced/{group}/',
                       template='example-advanced.html')
        def convert_replace_example(args):
            # args.field assumed to be Markdown
            obj = args.field.source
            for match in regex.finditer(obj):
                tag = match.group(1)
                yield slugify(tag), tag

            def _fn(match: re.Match) -> str:
                tag = match.group(1)
                return f'<a href="/advanced/{slugify(tag)}/">{tag}</a>'
            args.field.source = regex.sub(_fn, obj)
