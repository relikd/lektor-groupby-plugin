from lektor.assets import Asset  # isinstance
from lektor.db import Record  # isinstance
from lektor.pluginsystem import Plugin  # subclass
from typing import TYPE_CHECKING, Set, Iterator, Any
from .backref import GroupByRef, VGroups
from .groupby import GroupBy
from .pruner import prune
from .resolver import Resolver
from .vobj import GroupBySource, GroupByBuildProgram
if TYPE_CHECKING:
    from lektor.builder import Builder, BuildState
    from lektor.sourceobj import SourceObject
    from .watcher import GroupByCallbackArgs


class GroupByPlugin(Plugin):
    name = 'GroupBy Plugin'
    description = 'Cluster arbitrary records with field attribute keyword.'

    def on_setup_env(self, **extra: Any) -> None:
        self.resolver = Resolver(self.env)
        self.env.add_build_program(GroupBySource, GroupByBuildProgram)
        self.env.jinja_env.filters.update(vgroups=VGroups.iter)
        # kep track of already rebuilt GroupBySource artifacts
        self._is_build_all = False
        self._has_been_built = set()  # type: Set[str]

    def on_before_build_all(self, **extra: Any) -> None:
        self._is_build_all = True

    def on_before_build(
        self, builder: 'Builder', source: 'SourceObject', **extra: Any
    ) -> None:
        # before-build may be called before before-build-all (issue #1017)
        if isinstance(source, Asset):
            return
        # make GroupBySource available before building any Record artifact
        groupby = self._init_once(builder)
        # special handling for self-building of GroupBySource artifacts
        if isinstance(source, GroupBySource):
            if groupby.isBuilding:  # build is during groupby.build_all()
                self._has_been_built.add(source.path)
            elif source.path not in self._has_been_built:
                groupby.build_all(builder, source)  # needs rebuilding

    def on_after_build(
        self, source: 'SourceObject', build_state: 'BuildState', **extra: Any
    ) -> None:
        # a normal page update. We may need to re-build our GroupBySource
        if not self._is_build_all and isinstance(source, Record):
            if build_state.updated_artifacts:
                # TODO: instead of clear(), only remove affected GroupBySource
                #       ideally, identify which file has triggered the re-build
                self._has_been_built.clear()

    def on_after_build_all(self, builder: 'Builder', **extra: Any) -> None:
        # by now, most likely already built. So, build_all() is a no-op
        self._init_once(builder).build_all(builder)
        self._is_build_all = False

    def on_after_prune(self, builder: 'Builder', **extra: Any) -> None:
        # TODO: find a better way to prune unreferenced elements
        prune(builder, self.resolver.files)

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
                if isinstance(val, str) and val != '':
                    val = map(str.strip, val.split(split)) if split else [val]
                elif isinstance(val, (bool, int, float)):
                    val = [val]
                elif not val:  # after checking for '', False, 0, and 0.0
                    val = [None]
                if isinstance(val, (list, map)):
                    yield from val
