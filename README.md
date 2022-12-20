# Lektor Plugin: groupby

A generic grouping / clustering plugin.
Can be used for tagging or similar tasks.
The grouping algorithm is performed once.
Contrary to, at least, cubic runtime if doing the same with Pad queries.

Install this plugin or modify your Lektor project file:

```sh
lektor plugin add groupby
```

Optionally, enable a basic config:

```ini
[tags]
root = /
slug = tag/{key}.html
template = tag.html
split = ' '
```

Or dive into plugin development...

For usage examples, refer to the [examples](https://github.com/relikd/lektor-groupby-plugin/tree/main/examples) readme.
