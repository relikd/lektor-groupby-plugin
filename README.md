# Lektor Plugin: groupby

A generic grouping / clustering plugin.
Can be used for tagging or similar tasks.
The grouping algorithm is performed once.
Contrary to, at least, cubic runtime if doing the same with Pad queries.

To install this plugin, modify your Lektor project file:

```ini
[packages]
lektor-groupby = 0.9.1
```

Optionally, enable a basic config:

```ini
[tags]
root = /
slug = tag/{group}.html
template = tag.html
split = ' '
```

Or dive into plugin development...

For usage examples, refer to the [examples](https://github.com/relikd/lektor-groupby-plugin/tree/main/examples) readme.
