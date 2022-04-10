from lektor.builder import Builder  # typing
from lektor.db import Page  # typing
from lektor.pluginsystem import Plugin  # subclass
from lektor.sourceobj import SourceObject  # typing

from typing import List, Optional, Iterator, Any
from .vobj import GroupBySource, GroupByBuildProgram, VPATH, VGroups
from .groupby import GroupBy
from .pruner import prune
from .watcher import GroupByCallbackArgs  # typing


class GroupByPlugin(Plugin):
    name = 'GroupBy Plugin'
    description = 'Cluster arbitrary records with field attribute keyword.'

    def on_setup_env(self, **extra: Any) -> None:
        self.creator = GroupBy()
        self.env.add_build_program(GroupBySource, GroupByBuildProgram)
        self.env.jinja_env.filters.update(vgroups=VGroups.iter)

        # resolve /tag/rss/ -> /tag/rss/index.html (local server only)
        @self.env.urlresolver
        def a(node: SourceObject, parts: List[str]) -> Optional[GroupBySource]:
            return self.creator.resolve_dev_server_path(node, parts)

        # resolve virtual objects in admin UI
        @self.env.virtualpathresolver(VPATH.lstrip('@'))
        def b(node: SourceObject, parts: List[str]) -> Optional[GroupBySource]:
            return self.creator.resolve_virtual_path(node, parts)

    def _load_quick_config(self) -> None:
        ''' Load config file quick listeners. '''
        config = self.get_config()
        for key in config.sections():
            if '.' in key:  # e.g., key.fields and key.key_map
                continue

            watcher = self.creator.add_watcher(key, config)
            split = config.get(key + '.split')  # type: str

            @watcher.grouping()
            def _fn(args: GroupByCallbackArgs) -> Iterator[str]:
                val = args.field
                if isinstance(val, str):
                    val = map(str.strip, val.split(split)) if split else [val]
                if isinstance(val, (list, map)):
                    yield from val

    def on_before_build_all(self, builder: Builder, **extra: Any) -> None:
        self.creator.clear_previous_results()
        self._load_quick_config()
        # let other plugins register their @groupby.watch functions
        self.emit('before-build-all', groupby=self.creator, builder=builder)
        self.config_dependencies = self.creator.get_dependencies()
        self.creator.make_cluster(builder)

    def on_before_build(self, source: SourceObject, **extra: Any) -> None:
        # before-build may be called before before-build-all (issue #1017)
        # make sure it is evaluated immediatelly
        if isinstance(source, Page):
            self.creator.queue_now(source)

    def on_after_build_all(self, builder: Builder, **extra: Any) -> None:
        self.creator.build_all(builder)

    def on_after_prune(self, builder: Builder, **extra: Any) -> None:
        # TODO: find a better way to prune unreferenced elements
        prune(builder, VPATH)
