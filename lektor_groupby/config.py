from inifile import IniFile
from lektor.utils import slugify

from typing import Set, Dict, Optional, Union, Any

AnyConfig = Union['Config', IniFile, Dict]


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
    ) -> None:
        self.key = key
        self.root = (root or '/').rstrip('/') or '/'
        self.slug = slug or (key + '/{key}/')  # key = GroupBySource.key
        self.template = template or f'groupby-{self.key}.html'
        # editable after init
        self.enabled = True
        self.dependencies = set()  # type: Set[str]
        self.fields = {}  # type: Dict[str, Any]
        self.key_map = {}  # type: Dict[str, str]

    def slugify(self, k: str) -> str:
        ''' key_map replace and slugify. '''
        return slugify(self.key_map.get(k, k))  # type: ignore[no-any-return]

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

    def __repr__(self) -> str:
        txt = '<GroupByConfig'
        for x in ['key', 'root', 'slug', 'template', 'enabled']:
            txt += ' {}="{}"'.format(x, getattr(self, x))
        txt += f' fields="{", ".join(self.fields)}"'
        return txt + '>'

    @staticmethod
    def from_dict(key: str, cfg: Dict[str, str]) -> 'Config':
        ''' Set config fields manually. Allowed: key, root, slug, template. '''
        return Config(
            key=key,
            root=cfg.get('root'),
            slug=cfg.get('slug'),
            template=cfg.get('template'),
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
