from lektor.builder import Builder  # typing
from lektor.db import Page  # typing
from lektor.pluginsystem import Plugin  # subclass
from lektor.sourceobj import SourceObject  # typing

from typing import Iterator, Any
from .vobj import GroupBySource, GroupByBuildProgram, VPATH, VGroups
from .groupby import GroupBy
from .pruner import prune
from .resolver import Resolver
from .watcher import GroupByCallbackArgs  # typing


class GroupByPlugin(Plugin):
    name = 'GroupBy Plugin'
    description = 'Cluster arbitrary records with field attribute keyword.'

    def on_setup_env(self, **extra: Any) -> None:
        self.resolver = Resolver(self.env)
        self.env.add_build_program(GroupBySource, GroupByBuildProgram)
        self.env.jinja_env.filters.update(vgroups=VGroups.iter)

    def _load_quick_config(self, groupby: GroupBy) -> None:
        ''' Load config file quick listeners. '''
        config = self.get_config()
        for key in config.sections():
            if '.' in key:  # e.g., key.fields and key.key_map
                continue

            watcher = groupby.add_watcher(key, config)
            split = config.get(key + '.split')  # type: str

            @watcher.grouping()
            def _fn(args: GroupByCallbackArgs) -> Iterator[str]:
                val = args.field
                if isinstance(val, str):
                    val = map(str.strip, val.split(split)) if split else [val]
                if isinstance(val, (list, map)):
                    yield from val

    def _init_once(self, builder: Builder) -> GroupBy:
        try:
            return builder.__groupby  # type:ignore[attr-defined,no-any-return]
        except AttributeError:
            groupby = GroupBy()
            builder.__groupby = groupby  # type: ignore[attr-defined]

        self.resolver.reset()
        self._load_quick_config(groupby)
        # let other plugins register their @groupby.watch functions
        self.emit('before-build-all', groupby=groupby, builder=builder)
        self.config_dependencies = groupby.get_dependencies()
        groupby.queue_all(builder)
        groupby.make_cluster(builder, self.resolver)
        return groupby

    def on_before_build(self, builder: Builder, source: SourceObject,
                        **extra: Any) -> None:
        # before-build may be called before before-build-all (issue #1017)
        # make sure it is evaluated immediatelly
        if isinstance(source, Page):
            self._init_once(builder)

    def on_after_build_all(self, builder: Builder, **extra: object) -> None:
        self._init_once(builder).build_all(builder)

    def on_after_prune(self, builder: Builder, **extra: object) -> None:
        # TODO: find a better way to prune unreferenced elements
        prune(builder, VPATH)
