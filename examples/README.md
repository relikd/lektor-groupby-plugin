# Usage

Overview:
- [quick config example](#quick-config) shows how you can use the plugin config to setup a quick and easy tagging system.
- [simple example](#simple-example) goes into detail how to use it in your own plugin.
- [advanced example](#advanced-example) touches on the potentials of the plugin.
- [Misc](#misc) shows other use-cases.



## About

To use the groupby plugin you have to add an attribute to your model file.
In our case you can refer to the `models/page.ini` model:

```ini
[fields.tags]
label = Tags
type = strings
testA = true
testB = true

[fields.body]
label = Body
type = markdown
testC = true
```

We did define three custom attributes `testA`, `testB`, and `testC`.
You may add custom attributes to all of the fields.
It is crucial that the value of the custom attribute is set to true.
The attribute name is later used for grouping.



## Quick config

Relevant files:
```
configs/groupby.ini
templates/example-config.html
```

The easiest way to add tags to your site is by defining the `groupby.ini` config file.

```ini
[testA]
root = /
slug = config/{key}.html
template = example-config.html
split = ' '
enabled = True

[testA.fields]
title = "Tagged: " ~ this.group

[testA.key_map]
Blog = News
```

The configuration parameter are:

1. The section title (`testA`) must be one of the attribute variables we defined in our model.
2. The `root` parameter (`/`) is the root page of the groupby.
   All results will be placed under this directory, e.g., `/tags/tagname/`.
   If you use `root = /blog`, the results path will be `/blog/tags/tagname/`.
   The groupby plugin will traverse all sub-pages wich contain the attribute `testA`.
3. The `slug` parameter (`config/{key}.html`) is where the results are placed.
   In our case, the path resolves to `config/tagname.html`.
   The default value is `{attrib}/{key}/index.html` which would resolve to `testA/tagname/index.html`.
   If this field contains `{key}`, it just replaces the value with the group-key.
   In all other cases the field value is evaluated in a jinja context.
4. The `template`parameter (`example-config.html`) is used to render the results page.
   If no explicit template is set, the default template `groupby-testA.html` will be used.
   Where `testA` is replaced with whatever attribute you chose.
5. The `split` parameter (`' '`) will be used as string delimiter.
   Fields of type `strings` and `checkboxes` are already lists and don't need splitting.
   The split is only relevant for fields of type `string` or `text`.
   These single-line fields are then expanded to lists as well.
   If you do not provide the `split` option, the whole field value will be used as tagname.
6. The `enabled` parameter allows you to quickly disable the grouping.


You can have multiple listeners, e.g., one for `/blog/` and another for `/projects/`.
Just create as many custom attributes as you like, each having its own section.

There are two additional config mappings, `.fields` and `.key_map`.
Key-value pairs in `.fields` will be added as attributes to your grouping.
You can access them in your template (e.g., `{{this.title}}`).
All of the `.fields` values are evaluted in a jinja context, so be cautious when using plain strings. 

The built-in field attributes are:

- `group`: returned group name, e.g., "A Title?"
- `key`: slugified group value, e.g., "a-title"
- `slug`: url path after root node, e.g. "config/a-title.html" (can be `None`)
- `record`: parent node, e.g., `Page(path="/")`
- `children`: dictionary of `{record: extras}` pairs
- `first_child`: first page
- `first_extra`: first extra
- `config`: configuration object (see below)

Without any changes, the `key` value will just be `slugify(group)`.
However, the other mapping `.key_map` will replace `group` with whatever replacement value is provided in the `.key_map` and then slugified.
You could, for example, add a `C# = c-sharp` mapping, which would otherwise just be slugified to `c`.
This is equivalent to `slugify(key_map.get(group))`.

The `config` attribute contains the values that created the group:

- `key`: attribute key, e.g., `TestA`
- `root`: as provided by init, e.g., `/`
- `slug`: the raw value, e.g., `config/{key}.html`
- `template`: as provided by init, e.g., `example-config.html`
- `enabled`: boolean
- `dependencies`: path to config file (if initialized from config)
- `fields`: raw values from `TestA.fields`
- `key_map`: raw values from `TestA.key_map`

In your template file you have access to the attributes, config, and children (pages):

```jinja2
<h2>{{ this.title }}</h2>
<p>Key: {{ this.key }}, Attribute: {{ this.config.key }}</p>
<ul>
{%- for child in this.children %}
<li>Page: {{ child.path }}</li>
{%- endfor %}
</ul>
```



## Simple example

Relevant files:
```
packages/simple-example/lektor_simple.py
templates/example-simple.html
```

```python
def on_groupby_before_build_all(self, groupby, builder, **extra):
    watcher = groupby.add_watcher('testB', {
        'root': '/blog',
        'slug': 'simple/{key}/index.html',
        'template': 'example-simple.html',
    })
    watcher.config.set_key_map({'Foo': 'bar'})
    watcher.config.set_fields({'date': datetime.now()})

    @watcher.grouping(flatten=True)
    def convert_simple_example(args):
        # Yield groups
        value = args.field  # type: list # since model is 'strings' type
        for tag in value:
            yield tag, {'tags_in_page': value}
```

This example is roughly equivalent to the config example above – the parameters of the `groupby.add_watcher` function correspond to the same config parameters.
Additionally, you can set other types in `set_fields` (all strings are evaluated in jinja context!).

`@watcher.grouping` sets the callback to generate group keys.
It has one optional flatten parameter:

- `flatten` determines how Flow elements are processed.
  If `False`, the callback function is called once per Flow element.
  If `True` (default), the callback is called for all Flow-Blocks of the Flow individually.
  The attribute `testB` can be attached to either the Flow or a Flow-Block regardless.

The `args` parameter of the `convert_simple_example()` function is a named tuple, it has three attributes:

1. The `record` points to the `Page` record that contains the tag.
2. The `key` tuple `(field-key, flow-index, flow-key)` tells which field is processed.
   For Flow types, `flow-index` and `flow-key` are set, otherwise they are `None`.
3. The `field` value is the content of the processed field.
   The field value is equivalent to the following:

```python
k = args.key
field = args.record[k.fieldKey].blocks[k.flowIndex].get(k.flowKey)
```

The callback body **can** produce groupings but does not have to.
If you choose to produce an entry, you have to `yield` a string or tuple pair `(group, extra-info)`.
`group` is slugified (see above) and then used to combine & cluster pages.
The `extra-info` (optional) is passed through to your template file.
You can yield more than one entry per source.
Or ignore pages if you don't yield anything.

The template file can access and display the `extra-info`:

```jinja2
<p>Custom field date: {{this.date}}</p>
<ul>
{%- for child, extras in this.children.items() -%}
{%- set etxra = (extras|first).tags_in_page %}
<li>{{etxra|length}} tags on page "{{child.path}}": {{etxra}}</li>
{%- endfor %}
</ul>
```



## Advanced example

Relevant files:
```
configs/advanced.ini
packages/advanced-example/lektor_advanced.py
templates/example-advanced.html
```

The following example is similar to the previous one.
Except that it loads a config file and replaces in-text occurrences of `{{Tagname}}` with `<a href="/tag/">Tagname</a>`.

```python
def on_groupby_before_build_all(self, groupby, builder, **extra):
    # load config
    config = self.get_config()
    regex = config.get('testC.pattern.match')
    try:
        regex = re.compile(regex)
    except Exception as e:
        print('inlinetags.regex not valid: ' + str(e))
        return

    # load config directly (which also tracks dependency)
    watcher = groupby.add_watcher('testC', config)

    @watcher.grouping()
    def convert_replace_example(args):
        # args.field assumed to be Markdown
        obj = args.field.source
        slugify_map = {}  # type Dict[str, str]
        for match in regex.finditer(obj):
            tag = match.group(1)
            key = yield tag
            print('[advanced] slugify:', tag, '->', key)
            slugify_map[tag] = key

        def _fn(match: re.Match) -> str:
            tag = match.group(1)
            return f'<a href="/advanced/{slugify_map[tag]}/">{tag}</a>'
        args.field.source = regex.sub(_fn, obj)
```

Notice, `add_watcher` accepts a config file as parameter which keeps also track of dependencies and rebuilds pages when you edit the config file.
Further, the `yield` call returns the slugified group-key.
First, you do not need to slugify it yourself and second, potential replacements from `key_map` are already handled.

For Markdown fields, we can modify the `source` attribute directly.
All other field types need to be accessed via `args.record` key indirection (see [simple example](#simple-example)).

```ini
[testC]
root = /
slug = "advanced/{}/".format(this.key)
template = example-advanced.html

[testC.pattern]
match = {{([^}]{1,32})}}
```

The config file takes the same parameters as the [config example](#quick-config).
As you can see, `slug` is evaluated in jinja context.

We introduced a new config option `testC.pattern.match`.
This regular expression matches `{{` + any string less than 32 characters + `}}`.
Notice, the parenthesis (`()`) will match only the inner part but the replace function (`re.sub`) will remove the `{{}}`.



## Misc

It was shortly mentioned above that slugs can be `None` (only if manually set to `slug = None`).
This is useful if you do not want to create subpages but rather an index page containing all groups.
This can be done in combination with the next use-case:

```jinja2
{%- for x in this|vgroups('TestA', 'TestB', recursive=True)|unique|sort %} 
<a href="{{ x|url }}">({{ x.group }})</a>
{%- endfor %} 
```

You can query the groups of any parent node (including those without slug).
The keys (`'TestA', 'TestB'`) can be omitted which will return all groups of all attributes (you can still filter them with `x.config.key == 'TestC'`).
Refer to `templates/page.html` for usage.
