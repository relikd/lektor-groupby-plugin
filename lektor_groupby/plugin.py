from lektor.db import Page  # isinstance
from lektor.pluginsystem import Plugin  # subclass
from typing import TYPE_CHECKING, Iterator, Any
from .backref import GroupByRef, VGroups
from .groupby import GroupBy
from .pruner import prune
from .resolver import Resolver
from .vobj import VPATH, GroupBySource, GroupByBuildProgram
if TYPE_CHECKING:
    from lektor.builder import Builder, BuildState
    from lektor.sourceobj import SourceObject
    from .watcher import GroupByCallbackArgs


class GroupByPlugin(Plugin):
    name = 'GroupBy Plugin'
    description = 'Cluster arbitrary records with field attribute keyword.'

    def on_setup_env(self, **extra: Any) -> None:
        self.has_changes = False
        self.resolver = Resolver(self.env)
        self.env.add_build_program(GroupBySource, GroupByBuildProgram)
        self.env.jinja_env.filters.update(vgroups=VGroups.iter)

    def on_before_build(
        self, builder: 'Builder', source: 'SourceObject', **extra: Any
    ) -> None:
        # before-build may be called before before-build-all (issue #1017)
        # make sure it is always evaluated first
        if isinstance(source, Page):
            self._init_once(builder)

    def on_after_build(self, build_state: 'BuildState', **extra: Any) -> None:
        if build_state.updated_artifacts:
            self.has_changes = True

    def on_after_build_all(self, builder: 'Builder', **extra: Any) -> None:
        # only rebuild if has changes (bypass idle builds)
        # or the very first time after startup (url resolver & pruning)
        if self.has_changes or not self.resolver.has_any:
            self._init_once(builder).build_all(builder)  # updates resolver
            self.has_changes = False

    def on_after_prune(self, builder: 'Builder', **extra: Any) -> None:
        # TODO: find a better way to prune unreferenced elements
        prune(builder, VPATH, self.resolver.files)

    # ------------
    #   internal
    # ------------

    def _init_once(self, builder: 'Builder') -> GroupBy:
        try:
            return GroupByRef.of(builder)
        except AttributeError:
            groupby = GroupBy(self.resolver)
            GroupByRef.set(builder, groupby)

        self._load_quick_config(groupby)
        # let other plugins register their @groupby.watch functions
        self.emit('before-build-all', groupby=groupby, builder=builder)
        groupby.queue_all(builder)
        return groupby

    def _load_quick_config(self, groupby: GroupBy) -> None:
        ''' Load config file quick listeners. '''
        config = self.get_config()
        for key in config.sections():
            if '.' in key:  # e.g., key.fields and key.key_map
                continue

            watcher = groupby.add_watcher(key, config)
            split = config.get(key + '.split')  # type: str

            @watcher.grouping()
            def _fn(args: 'GroupByCallbackArgs') -> Iterator[str]:
                val = args.field
                if isinstance(val, str):
                    val = map(str.strip, val.split(split)) if split else [val]
                if isinstance(val, (list, map)):
                    yield from val
