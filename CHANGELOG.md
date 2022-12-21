# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/0.9.8/),
and this project does adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

### Fixed
- No duplicate `GroupBySource` entries in `vgroups` filter (while keeping sort order)



## [0.9.9] – 2022-12-21

### Fixed
- Keep original sorting order in `vgroups` filter if no `order_by` is set



## [0.9.8] – 2022-12-20

### Added
- Support for Alternatives
- Support for Pagination
- Support for additional yield types (str, int, float, bool)
- Support for sorting `GroupBySource` children
- Support for sorting `vgroups` filter
- Config option `.replace_none_key` to replace `None` with another value
- Config option `.key_obj_fn` (function) can be used to map complex objects to simple values (e.g., list of strings -> count as int). In your jinja template you may use `X` (the object) and `ARGS` (the `GroupByCallbackArgs`).
- New property `supports_pagination` (bool) for `GroupBySource`
- Partial building. Only process `Watcher` which are used during template rendering.
- Rebuild `GroupBySource` only once after a `Record` update

### Changed
- Use `Query` for children instead of `Record` list
- Rename `GroupBySource.group` to `GroupBySource.key_obj`
- Yield return `GroupBySource` during `watcher.grouping()` instead of slugified key
- Postpone `Record` processing until `make_once()`
- Allow preprocessing with `pre_build=True` as optional parameter for `groupby.add_watcher()` (useful for modifying source before build)
- Evaluate `fields` attributes upon access, not initialization (this comes with a more fine-grained dependency tracking)
- Resolver groups virtual pages per groupby config key (before it was just a list of all groupby sources mixed together)
- Refactor pruning by adding a `VirtualPruner` vobj
- Pruning is performed directly on the database
- `GroupBySource.path` may include a page number suffix `/2`
- `GroupBySource.url_path` may include a page number and custom `url_suffix`

### Removed
- `GroupingCallback` may no longer yield an extra object. The usage was cumbersome and can be replaced with the `.fields` config option.

### Fixed
- `GroupBySource` not updated on template edit
- `most_used_key` with empty list
- Don't throw exception if `GroupBySource` is printed before finalize
- Hotfix for Lektor issue #1085 by avoiding `TypeError`
- Add missing dependencies during `vgroups` filter
- Include model-fields with null value on yield



## [0.9.7] – 2022-04-22

### Changed
- Refactor `GroupBySource` init method
- Decouple `fields` expression processing from init

### Fixed
- Keep order of groups intact



## [0.9.6] – 2022-04-13

### Added
- Set extra-info default to the model-key that generated the group.
- Reuse previously declared `fields` attributes in later `fields`.

### Changed
- Thread-safe building. Each groupby is performed on the builder which initiated the build.
- Deferred building. The groupby callback is only called when it is accessed for the first time.
- Build-on-access. If there are no changes, no groupby build is performed.

### Fixed
- Inconsistent behavior due to concurrent building (see above)
- Case insensitive default group sort
- Using the split config-option now trims whitespace
- `most_used_key` working properly



## [0.9.5] – 2022-04-07

### Fixed
- Allow model instances without flow-blocks



## [0.9.4] – 2022-04-06

### Fixed
- Error handling for GroupBySource `__getitem__` by raising `__missing__`
- Reuse GroupBySource if two group names result in the same slug



## [0.9.3] – 2022-04-06

### Added
- Config option `.fields` can add arbitrary attributes to the groupby
- Config option `.key_map` allows to replace keys with other values (e.g., "C#" -> "C-Sharp")
- Set `slug = None` to prevent rendering of groupby pages
- Query groupby of children

### Changed
- Another full refactoring, constantly changing, everything is different ... again



## [0.9.2] – 2022-04-01

### Fixed
- Prevent duplicate processing of records



## [0.9.1] – 2022-03-31

### Added
- Example project
- Before- and after-init hooks
- More type hints (incl. bugfixes)

### Changed
- Encapsulate logic into separate classes

### Fixed
- Concurrency issues by complete refactoring
- Virtual path and remove virtual path resolver



## [0.9] – 2022-03-27

### Fixed
- Groupby is now generated before main page
- PyPi readme



## [0.8] – 2022-03-25

Initial release


[Unreleased]: https://github.com/relikd/lektor-groupby-plugin/compare/v0.9.9...HEAD
[0.9.9]: https://github.com/relikd/lektor-groupby-plugin/compare/v0.9.8...v0.9.9
[0.9.8]: https://github.com/relikd/lektor-groupby-plugin/compare/v0.9.7...v0.9.8
[0.9.7]: https://github.com/relikd/lektor-groupby-plugin/compare/v0.9.6...v0.9.7
[0.9.6]: https://github.com/relikd/lektor-groupby-plugin/compare/v0.9.5...v0.9.6
[0.9.5]: https://github.com/relikd/lektor-groupby-plugin/compare/v0.9.4...v0.9.5
[0.9.4]: https://github.com/relikd/lektor-groupby-plugin/compare/v0.9.3...v0.9.4
[0.9.3]: https://github.com/relikd/lektor-groupby-plugin/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/relikd/lektor-groupby-plugin/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/relikd/lektor-groupby-plugin/compare/v0.9...v0.9.1
[0.9]: https://github.com/relikd/lektor-groupby-plugin/compare/v0.8...v0.9
[0.8]: https://github.com/relikd/lektor-groupby-plugin/releases/tag/v0.8
