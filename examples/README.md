# Usage

Overview:
- [quick config example](#quick-config) shows how you can use the plugin config to setup a quick and easy tagging system.
- [simple example](#simple-example) goes into detail how to use it in your own plugin.
- [advanced example](#advanced-example) touches on the potentials of the plugin.
- [Misc](#misc) shows other use-cases.

After reading this tutorial, have a look at other plugins that use `lektor-groupby`:
- [lektor-inlinetags](https://github.com/relikd/lektor-inlinetags-plugin)


## About

To use the groupby plugin you have to add an attribute to your model file.
For this tutorial you can refer to the [`models/page.ini`](./models/page.ini) model:

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

We define three custom attributes `testA`, `testB`, and `testC`.
You may add custom attributes to all of the fields.
It is crucial that the value of the custom attribute is set to true.
The attribute name is later used for grouping.



## Quick config

Relevant files:

- [`configs/groupby.ini`](./configs/groupby.ini)
- [`templates/example-config.html`](./templates/example-config.html)


The easiest way to add tags to your site is by defining the `groupby.ini` config file.

```ini
[testA]
root = /
slug = config/{key}.html
template = example-config.html
split = ' '
enabled = True
key_obj_fn = (X.upper() ~ ARGS.key.fieldKey) if X else 'empty'
replace_none_key = unknown

[testA.children]
order_by = -title, body

[testA.pagination]
enabled = true
per_page = 5
url_suffix = .page.

[testA.fields]
title = "Tagged: " ~ this.key_obj

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
7. The `key_obj_fn` parameter (jinja2) accepts any function-like snippet or function call.
   The context provides two variables, `X` and `ARGS`.
   The former is the raw value of the grouping, this may be a text field, markdown, or whatever custom type you have provided.
   The latter is a named tuple with `record`, `key`, and `field` values (see [simple example](#simple-example)).
8. The `replace_none_key` parameter (string) is applied after `key_obj_fn` (if provided) and maps empty values to a default value.


You can have multiple listeners, e.g., one for `/blog/` and another for `/projects/`.
Just create as many custom attributes as you like, each having its own section (and subsections).

The `.children` subsection currently has a single config field: `order_by`.
The usual [order-by](https://www.getlektor.com/docs/guides/page-order/) rules apply (comma separated list of keys with `-` for reversed order).
The order-by key can be anything of the page attributes of the children.

The `.pagination` subsection accepts the same configuration options as the Lektor pagination [model](https://www.getlektor.com/docs/models/children/#pagination) and [guide](https://www.getlektor.com/docs/guides/pagination/).
Plus, an additional `url_suffix` parameter if you would like to customize the URL scheme.

The `.fields` subsection is a list of key-value pairs which will be added as attributes to your grouping.
You can access them in your template (e.g., `{{this.title}}`).
All of the `.fields` values are evaluted in a jinja context, so be cautious when using plain strings.
Further, they are evaluated on access and not on define.

The built-in field attributes are:

- `key_obj`: model returned object, e.g., "A Title?"
- `key`: slugified value of `key_obj`, e.g., "a-title"
- `record`: parent node, e.g., `Page(path="/")`
- `slug`: url path under parent node, e.g. "config/a-title.html" (can be `None`)
- `children`: the elements of the grouping (a `Query` of `Record` type)
- `config`: configuration object (see below)

Without any changes, the `key` value will just be `slugify(key_obj)`.
However, the `.key_map` subsection will replace `key_obj` with whatever replacement value is provided in the `.key_map` and then slugify.
You could, for example, add a `C# = c-sharp` mapping, which would otherwise just be slugified to `c`.
This is equivalent to `slugify(key_map.get(key_obj))`.

The `config` attribute contains the values that created the group:

- `key`: attribute key, e.g., `TestA`
- `root`: as provided by init, e.g., `/`
- `slug`: the raw value, e.g., `config/{key}.html`
- `template`: as provided by init, e.g., `example-config.html`
- `key_obj_fn`: as provided by init, e.g., `X.upper() if X else 'empty'`
- `replace_none_key`: as provided by init, e.g., `unknown`
- `enabled`: boolean
- `dependencies`: path to config file (if initialized from config)
- `fields`: raw values from `TestA.fields`
- `key_map`: raw values from `TestA.key_map`
- `pagination`: raw values from `TestA.pagination`
- `order_by`: list of key-strings from `TestA.children.order_by`

In your template file you have access to the config, attributes, fields, and children (Pages):

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

- [`packages/simple-example/lektor_simple.py`](./packages/simple-example/lektor_simple.py)
- [`templates/example-simple.html`](./templates/example-simple.html)


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
            yield tag
```

This example is roughly equivalent to the config example above – the parameters of the `groupby.add_watcher` function correspond to the same config parameters.
Additionally, you can set other types in `set_fields` (all strings are evaluated in jinja context!).
Refer to `lektor_simple.py` for all available configuration options.

The `@watcher.grouping` callback generates all groups for a single watcher-attribute.
The callback body **can** produce groupings but does not have to.
If you choose to produce an entry, you have to `yield` a grouping object (string, int, bool, float, or object).
In any case, `key_obj` is slugified (see above) and then used to combine & cluster pages.
You can yield more than one entry per source.
Or ignore pages if you don't yield anything.

The `@watcher.grouping` decorator takes one optional parameter:

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

Again, you can use all properties in your template.

```jinja2
<p>Custom field date: {{this.date}}</p>
<ul>
{%- for child in this.children %}
<li>page "{{child.path}}" with tags: {{child.tags}}</li>
{%- endfor %}
</ul>
```



## Advanced example

Relevant files:

- [`configs/advanced.ini`](./configs/advanced.ini)
- [`packages/advanced-example/lektor_advanced.py`](./packages/advanced-example/lektor_advanced.py)
- [`templates/example-advanced.html`](./templates/example-advanced.html)


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
    watcher = groupby.add_watcher('testC', config, pre_build=True)

    @watcher.grouping()
    def convert_replace_example(args):
        # args.field assumed to be Markdown
        obj = args.field.source
        url_map = {}  # type Dict[str, str]
        for match in regex.finditer(obj):
            tag = match.group(1)
            vobj = yield tag
            if not hasattr(vobj, 'custom_attr'):
                vobj.custom_attr = []
            vobj.custom_attr.append(tag)
            url_map[tag] = vobj.url_path
            print('[advanced] slugify:', tag, '->', vobj.key)

        def _fn(match: re.Match) -> str:
            tag = match.group(1)
            return f'<a href="{url_map[tag]}">{tag}</a>'
        args.field.source = regex.sub(_fn, obj)
```

Notice, `add_watcher` accepts a config file as parameter which keeps also track of dependencies and rebuilds pages when you edit the config file.
Further, the `yield` call returns a `GroupBySource` virtual object.
You can use this object to add custom static attributes (similar to dynamic attributes with the `.fields` subsection config).

Not all attributes are available at this time, as the grouping is still in progress.
But you can use `vobj.url_path` to get the target URL or `vobj.key` to get the slugified object-key (substitutions from `key_map` are already applied).

Usually, the grouping is postponed until the very end of the build process.
However, in this case we want to modify the source before it is build by Lektor.
For this situation we need to set `pre_build=True` in our `groupby.add_watcher()` call.
All watcher with this flag will be processed before any Page is built.
**Note:** If you can, avoid this performance regression.
The grouping for these watchers will be performed each time you navigate from one page to another.

This example uses a Markdown model type as source.
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
We introduced a new config option `testC.pattern.match`.
This regular expression matches `{{` + any string less than 32 characters + `}}`.
Notice, the parenthesis (`()`) will match only the inner part, thus the replace function (`re.sub`) removes the `{{}}`.



## Misc

### Omit output with empty slugs

It was shortly mentioned above that slugs can be `None` (e.g., manually set to `slug = None`).
This is useful if you do not want to create subpages but rather an index page containing all groups.
You can combine this with the next use-case.


### Index pages & Group query + filter

```jinja2
{%- for x in this|vgroups(keys=['TestA', 'TestB'], fields=[], flows=[], recursive=True, order_by='key_obj') %} 
<a href="{{ x|url }}">({{ x.key_obj }})</a>
{%- endfor %} 
```

You can query the groups of any parent node (including those without slug).
[`templates/page.html`](./templates/page.html) uses this.
The keys (`'TestA', 'TestB'`) can be omitted which will return all groups of all attributes (you can still filter them with `x.config.key == 'TestC'`).
The `fields` and `flows` params are also optional.
With these you can match groups in `args.key.fieldKey` and `args.key.flowKey`.
For example, if you have a “main-tags” field and an “additional-tags” field and you want to show the main-tags in a preview but both tags on a detail page.


### Sorting groups

Sorting is supported for the `vgroups` filter as well as for the children of each group (via config subsection `.children.order_by`).
Coming back to the previous example, `order_by` can be either a comma-separated string of keys or a list of strings.
Again, same [order-by](https://www.getlektor.com/docs/guides/page-order/) rules apply as for any other Lektor `Record`.
Only this time, the attributes of the `GroupBy` object are used for sorting (including those you defined in the `.fields` subsection).


### Pagination

You may use the `.pagination` subsection or `watcher.config.set_pagination()` to configure a pagination controller.
The `url_path` of a paginated Page depends on your `slug` value.
If the slug ends on `/` or `/index.html`, Lektor will append `page/2/index.html` to the second page.
If the slug contains a `.` (e.g. `/a/{key}.html`), Lektor will insert `page2` in front of the extension (e.g., `/a/{key}page2.html`).
If you supply a different `url_suffix`, for example “.X.”, those same two urls will become `.X./2/index.html` and `/a/{key}.X.2.html` respectively.
