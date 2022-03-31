# Usage

Overview:
- the [quick config](#quick-config) example shows how you can use the plugin config to setup a quick and easy tagging system.
- the [simple example](#simple-example) goes into detail how this plugin works.
- the [advanced example](#advanced-example) touches on the potentials of the plugin.



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
slug = config/{group}.html
template = example-config.html
split = ' '
```

The configuration parameter are:

1. The section title (`testA`) must be one of the attribute variables we defined in our model.
2. The `root` parameter (`/`) is the root page of the groupby.
   All results will be placed under this directory, e.g., `/tags/tagname/`.
   If you use `root = /blog`, the results path will be `/blog/tags/tagname/`.
   The groupby plugin will traverse all sub-pages wich contain the attribute `testA`.
3. The `slug` parameter (`config/{group}.html`) is where the results are placed.
   In our case, the path resolves to `config/tagname.html`.
   The default value is `{attrib}/{group}/index.html` which would resolve to `testA/tagname/index.html`.
4. The `template`parameter (`example-config.html`) is used to render the results page.
   If no explicit template is set, the default template `groupby-testA.html` will be used.
   Where `testA` is replaced with whatever attribute you chose.
5. The `split` parameter (`' '`) will be used as string delimiter.
   Fields of type `strings` and `checkboxes` are already lists and don't need splitting.
   The split is only relevant for fields of type `string` or `text`.
   These single-line fields are then expanded to lists as well.
   If you do not provide the `split` option, the whole field value will be used as tagname.


You can have multiple listeners, e.g., one for `/blog/` and another for `/projects/`.
Just create as many custom attributes as you like, each having its own section.

In your template file you have access to the children (pages) and their tags.
The emitted `extras` for the child is a list of original tagnames.

```jinja2
{%- for child, extras in this.children.items() %}
<li>Page: {{ child.path }}, Tags: {{ extras }}</li>
{%- endfor %}
```



## Simple example

Relevant files:
```
packages/simple-example/lektor_simple.py
templates/example-simple.html
```

```python
def on_groupby_after_build_all(self, groupby, builder, **extra):
    @groupby.watch('/blog', 'testB', slug='simple/{group}/index.html',
                   template='example-simple.html', flatten=True)
    def convert_simple_example(args):
        value = args.field  # list, since model is 'strings' type
        for tag in value: 
            yield slugify(tag), {'val': tag, 'tags_in_page': len(value)}

        # page = args.record  # extract additional info from source
        # fieldKey, flowIndex, flowKey = args.key  # or get field index
        # if flowIndex is None:
        #     obj = page[fieldKey]
        # else:
        #     obj = page[fieldKey].blocks[flowIndex].get(flowKey)
```

This example is roughly equivalent to the config file example.
The parameters of the `@groupby.watch` function (`root`, `attribute`, `slug`, `template`) correspond to the same config parameters described above.
There is a new `flatten` parameter:

- Flatten determines how Flow elements are processed.
  If `False`, the callback function is called once per Flow element.
  If `True` (default), the callback is called for all Flow-Blocks of the Flow individually.
  The attribute `testB` can be attached to either the Flow or a Flow-Block regardless.

The `args` parameter of the `convert_simple_example()` function is a named tuple, it has three attributes:

1. The `record` points to the `Page` source which contains the tag.
2. The `key` tuple `(field-key, flow-index, flow-key)` tells which field is processed.
   For Flow types, `flow-index` and `flow-key` are set, otherwise they are `None`.
3. The `field` value is the content of the processed field.
   The field value is reoughly equivalent to the following:

```python
args.page[fieldKey].blocks[flowIndex].get(flowKey)
```

The callback body **can** produce groupings but does not have to.
If you choose to produce an entry, you have to `yield` a tuple pair of `(groupkey, extra-info)`.
`groupkey` is used to combine & cluster pages and must be URL-safe.
The `extra-info` is passed through to your template file.
You can yield more than one entry per source or filter / ignore pages if you don't yield anything.

The template file can access and display the `extra-info`:

```jinja2
{%- for child, extras in this.children.items() %}
<b>Page: {{ child.title }}<b>
<ul>
{%- for extra in extras %}
<li>Name: {{ extra.val }}, Tag count: {{ extra.tags_in_page }}</li>
{%- endfor %}
</ul>
{%- endfor %}
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
    regex = re.compile(self.get_config().get('match'))
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
```

One **important** thing to notice is, we use `on_groupby_before_build_all` to register our callback function.
This is required because we would like to modify the source **before** it is written to disk.
If you look back to the [simple example](#simple-example), we used `on_groupby_after_build_all` because we did not care when it is executed.
Generally, it makes little difference which one you use (`on-after` is likely less busy).
Just know that you can process the source before or after it is build.

For Markdown fields, we can modify the `source` attribute directly.
All other field typed need to be accessed via `args.record` key indirection.

```ini
match = {{([^}]{1,32})}}
```

Lastly, the config file contains a regular expression which matches `{{` + any string less than 32 characters + `}}`.
Notice, the parenthesis (`()`) will match the inner part but the replace function (`re.sub`) will remove the `{{}}` too.

If the user changes the regex pattern in the config file, we need to rebuild all tags.
For this purpose we need to track changes to the config file.
This is done by calling:

```python
@groupby.depends_on(file1, file2, ...)
```
