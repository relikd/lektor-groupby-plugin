from inifile import IniFile
from lektor.environment import Expression
from lektor.context import Context
from lektor.utils import slugify as _slugify
from typing import (
    TYPE_CHECKING, Set, Dict, Optional, Union, Any, List, Generator
)
from .util import split_strip
if TYPE_CHECKING:
    from lektor.sourceobj import SourceObject


AnyConfig = Union['Config', IniFile, Dict]


class ConfigError(Exception):
    ''' Used to print a Lektor console error. '''

    def __init__(
        self, key: str, field: str, expr: str, error: Union[Exception, str]
    ):
        self.key = key
        self.field = field
        self.expr = expr
        self.error = error

    def __str__(self) -> str:
        return 'Invalid config for [{}.{}] = "{}"  –  Error: {}'.format(
            self.key, self.field, self.expr, repr(self.error))


class Config:
    '''
    Holds information for GroupByWatcher and GroupBySource.
    This object is accessible in your template file ({{this.config}}).

    Available attributes:
    key, root, slug, template, enabled, dependencies, fields, key_map
    '''

    def __init__(
        self,
        key: str, *,
        root: Optional[str] = None,  # default: "/"
        slug: Optional[str] = None,  # default: "{attr}/{group}/index.html"
        template: Optional[str] = None,  # default: "groupby-{attr}.html"
        replace_none_key: Optional[str] = None,  # default: None
        key_obj_fn: Optional[str] = None,  # default: None
    ) -> None:
        self.key = key
        self.root = (root or '/').rstrip('/') or '/'
        self.slug = slug or (key + '/{key}/')  # key = GroupBySource.key
        self.template = template or f'groupby-{self.key}.html'
        self.replace_none_key = replace_none_key
        self.key_obj_fn = key_obj_fn
        # editable after init
        self.enabled = True
        self.dependencies = set()  # type: Set[str]
        self.fields = {}  # type: Dict[str, Any]
        self.key_map = {}  # type: Dict[str, str]
        self.pagination = {}  # type: Dict[str, Any]
        self.order_by = None  # type: Optional[List[str]]

    def slugify(self, k: str) -> str:
        ''' key_map replace and slugify. '''
        rv = self.key_map.get(k, k)
        return _slugify(rv) or rv  # the `or` allows for example "_"

    def set_fields(self, fields: Optional[Dict[str, Any]]) -> None:
        '''
        The fields dict is a mapping of attrib = Expression values.
        Each dict key will be added to the GroupBySource virtual object.
        Each dict value is passed through jinja context first.
        '''
        self.fields = fields or {}

    def set_key_map(self, key_map: Optional[Dict[str, str]]) -> None:
        ''' This mapping replaces group keys before slugify. '''
        self.key_map = key_map or {}

    def set_pagination(
        self,
        enabled: Optional[bool] = None,
        per_page: Optional[int] = None,
        url_suffix: Optional[str] = None,
        items: Optional[str] = None,
    ) -> None:
        ''' Used for pagination. '''
        self.pagination = dict(
            enabled=enabled,
            per_page=per_page,
            url_suffix=url_suffix,
            items=items,
        )

    def set_order_by(self, order_by: Optional[str]) -> None:
        ''' If specified, children will be sorted according to keys. '''
        self.order_by = split_strip(order_by or '', ',') or None

    def __repr__(self) -> str:
        txt = '<GroupByConfig'
        for x in ['enabled', 'key', 'root', 'slug', 'template', 'key_obj_fn']:
            txt += ' {}="{}"'.format(x, getattr(self, x))
        txt += f' fields="{", ".join(self.fields)}"'
        if self.order_by:
            txt += ' order_by="{}"'.format(' ,'.join(self.order_by))
        return txt + '>'

    @staticmethod
    def from_dict(key: str, cfg: Dict[str, str]) -> 'Config':
        ''' Set config fields manually. Allowed: key, root, slug, template. '''
        return Config(
            key=key,
            root=cfg.get('root'),
            slug=cfg.get('slug'),
            template=cfg.get('template'),
            replace_none_key=cfg.get('replace_none_key'),
            key_obj_fn=cfg.get('key_obj_fn'),
        )

    @staticmethod
    def from_ini(key: str, ini: IniFile) -> 'Config':
        ''' Read and parse ini file. Also adds dependency tracking. '''
        cfg = ini.section_as_dict(key)  # type: Dict[str, str]
        conf = Config.from_dict(key, cfg)
        conf.enabled = ini.get_bool(key + '.enabled', True)
        conf.dependencies.add(ini.filename)
        conf.set_fields(ini.section_as_dict(key + '.fields'))
        conf.set_key_map(ini.section_as_dict(key + '.key_map'))
        conf.set_pagination(
            enabled=ini.get_bool(key + '.pagination.enabled', None),
            per_page=ini.get_int(key + '.pagination.per_page', None),
            url_suffix=ini.get(key + '.pagination.url_suffix'),
            items=ini.get(key + '.pagination.items'),
        )
        conf.set_order_by(ini.get(key + '.children.order_by', None))
        return conf

    @staticmethod
    def from_any(key: str, config: AnyConfig) -> 'Config':
        assert isinstance(config, (Config, IniFile, Dict))
        if isinstance(config, Config):
            return config
        elif isinstance(config, IniFile):
            return Config.from_ini(key, config)
        elif isinstance(config, Dict):
            return Config.from_dict(key, config)

    # -----------------------------------
    #          Field Expressions
    # -----------------------------------

    def _make_expression(self, expr: Any, *, on: 'SourceObject', field: str) \
            -> Union[Expression, Any]:
        ''' Create Expression and report any config error. '''
        if not isinstance(expr, str):
            return expr
        try:
            return Expression(on.pad.env, expr)
        except Exception as e:
            raise ConfigError(self.key, field, expr, e)

    def eval_field(self, attr: str, *, on: 'SourceObject') \
            -> Union[Expression, Any]:
        ''' Create an expression for a custom defined user field. '''
        # do not `gather_dependencies` because fields are evaluated on the fly
        # dependency tracking happens whenever a field is accessed
        return self._make_expression(
            self.fields[attr], on=on, field='fields.' + attr)

    def eval_slug(self, key: str, *, on: 'SourceObject') -> Optional[str]:
        ''' Either perform a "{key}" substitution or evaluate expression. '''
        cfg_slug = self.slug
        if not cfg_slug:
            return None
        if '{key}' in cfg_slug:
            if key:
                return cfg_slug.replace('{key}', key)
            else:
                raise ConfigError(self.key, 'slug', cfg_slug,
                                  'Cannot replace {key} with None')
                return None
        else:
            # TODO: do we need `gather_dependencies` here too?
            expr = self._make_expression(cfg_slug, on=on, field='slug')
            return expr.evaluate(on.pad, this=on, alt=on.alt) or None

    def eval_key_obj_fn(self, *, on: 'SourceObject', context: Dict) -> Any:
        '''
        If `key_obj_fn` is set, evaluate field expression.
        Note: The function does not check whether `key_obj_fn` is set.
        Return: A Generator result is automatically unpacked into a list.
        '''
        exp = self._make_expression(self.key_obj_fn, on=on, field='key_obj_fn')
        with Context(pad=on.pad) as ctx:
            with ctx.gather_dependencies(self.dependencies.add):
                res = exp.evaluate(on.pad, this=on, alt=on.alt, values=context)
        if isinstance(res, Generator):
            res = list(res)  # unpack for 1-to-n replacement
        return res
