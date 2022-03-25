# Lektor Plugin: groupby

A generic grouping / clustering plugin. Can be used for tagging or similar tasks.

Overview:
- the [basic example](#usage-basic-example) goes into detail how this plugin works.
- the [quick config](#usage-quick-config) example show how you can use the plugin config to setup a quick and easy tagging system.
- the [complex example](#usage-a-slightly-more-complex-example) touches on the potential of what is possible.


## Usage: Basic example

Lets start with a simple example: adding a tags field to your model.
Assuming you have a `blog-entry.ini` that is used for all children of `/blog` path.


#### `models/blog-entry.ini`

```ini
[fields.tags]
label = Tags
type = strings
myvar = true

[fields.body]
label = Content
type = markdown
```

Notice we introduce a new attribute variable: `myvar = true`.
The name can be anything here, we will come to that later.
The only thing that matters is that the value is a boolean and set to true.

Edit your blog entry and add these two new tags:

```
Awesome
Latest News
```

Next, we need a plugin to add the groupby event listener.


#### `packages/test/lektor_my_tags_plugin.py`

```python
def on_groupby_init(self, groupby, **extra):
    @groupby.watch('/blog', 'myvar', flatten=True, template='myvar.html',
                   slug='tag/{group}/index.html')
    def do_myvar(args):
        page = args.record  # extract additional info from source
        fieldKey, flowIndex, flowKey = args.key  # or get field index directly
        # val = page.get(fieldKey).blocks[flowIndex].get(flowKey)
        value = args.field  # list type since model is 'strings' type
        for tag in value:
            yield slugify(tag), {'val': tag, 'tags_in_page': len(value)}
```

There are a few important things here:

1. The first parameter (`'/blog'`) is the root page of the groupby.
   All results will be placed under this directory, e.g., `/blog/tags/clean/`.
   You can also just use `/`, in which case the same path would be `/tags/clean/`.
   Or create multiple listeners, one for `/blog/` and another for `/projects/`, etc.
2. The second parameter (`'myvar'`) must be the same attribute variable we used in our `blog-entry.ini` model.
   The groupby plugin will traverse all models and search for this attribute name.
3. Flatten determines how Flow elements are processed.
   If `False`, the callback function `convert_myvar()` is called once per Flow element (if the Flow element has the `myvar` attribute attached).
   If `True` (default), the callback is called for all Flow blocks individually.
4. The template `myvar.html` is used to render the grouping page.
   This parameter is optional.
   If no explicit template is set, the default template `groupby-myvar.html` would be used. Where `myvar` is replaced with whatever attribute you chose.
5. Finally, the slug `tag/{group}/index.html` is where the result is placed.
   The default value for this parameter is `{attrib}/{group}/index.html`.
   In our case, the default path would resolve to `myvar/awesome/index.html`.
   We explicitly chose to replace the default slug with our own, which ignores the attrib path component and instead puts the result pages inside the `/tag` directory.
   (PS: you could also use for example `t/{group}.html`, etc.)


So much for the `args` parameter.
The callback body **can** produce groupings but does not have to.
If you choose to produce an entry, you have to `yield` a tuple pair of `(groupkey, extra-info)`.
`groupkey` is used to combine & cluster pages and must be URL-safe.
The `extra-info` is passed through to your template file.
You can yield more than one entry per source or filter / ignore pages if you don't yield anything.
Our simple example will generate the output files `tag/awesome/index.html` and `tag/latest-news/index.html`.

Lets take a look at the html next.


#### `templates/myvar.html`

```html
<h2>Path: {{ this | url(absolute=True) }}</h2>
<div>This is: {{this}}</div>
<ul>
	{%- for child in this.children %}
	<li>Page: {{ child.record.path }}, Name: {{ child.extra.val }}, Tag count: {{ child.extra.tags_in_page }}</li>
	{%- endfor %}
</ul>
```

Notice, we can use `child.record` to access the referenced page of the group cluster.
`child.extra` contains the additional information we previously passed into the template.

The final result of `tag/latest-news/index.html`:

```
Path: /tag/latest-news/
This is: <GroupBySource attribute="myvar" group="latest-news" template="myvar.html" slug="tag/latest-news/" children=1>
  -  Page: /blog/barss, Name: Latest News, Tag count: 2
```


## Usage: Quick config

The whole example above can be simplified with a plugin config:

#### `configs/groupby.ini`

```ini
[myvar]
root = /blog/
slug = tag/{group}/index.html
template = myvar.html
split = ' '
```

You still need to add a separate attribute to your model (step 1), but anything else is handled by the config file.
All of these fields are optional and fallback to the default values stated above.

The newly introduced option `split` will be used as string delimiter.
This allows to have a field with `string` type instead of `strings` type.
If you do not provide the `split` option, the whole field value will be used as group key.
Note: split is only used on str fields (`string` type), not lists (`strings` type).

The emitted `extra-info` for the child is the original key value.
E.g., `Latest News,Awesome` with `split = ,` yields `('latest-news', 'Latest News')` and `('awesome', 'Awesome')`.


## Usage: A slightly more complex example

There are situations though, where a simple config file is not enough.
The following plugin will find all model fields with attribute `inlinetags` and search for in-text occurrences of `{{Tagname}}` etc.

```python
from lektor.markdown import Markdown
from lektor.types.formats import MarkdownDescriptor
from lektor.utils import slugify
import re
_regex = re.compile(r'{{([^}]{1,32})}}')

def on_groupby_init(self, groupby, **extra):
    @groupby.watch('/', 'inlinetags', slug='tags/{group}/')
    def convert_inlinetags(args):
        arr = args.field if isinstance(args.field, list) else [args.field]
        for obj in arr:
            if isinstance(obj, (Markdown, MarkdownDescriptor)):
                obj = obj.source
            if isinstance(obj, str) and str:
                for match in _regex.finditer(obj):
                    tag = match.group(1)
                    yield slugify(tag), tag
```

This generic approach does not care what data-type the field value is:
`strings` fields will be expanded and enumerated, Markdown will be unpacked.
You can combine this mere tag-detector with text-replacements to point to the actual tags-page.
