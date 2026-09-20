"""Náhrada `homeassistant` a `voluptuous` pro testy bez nainstalovaného Home Assistantu.

Instaluje se do `sys.modules` jen to, co integrace importuje na úrovni modulu —
tolik, aby šel `custom_components.nokturno` naimportovat a otestovat jeho čisté
pomocné funkce. Když je skutečný Home Assistant k dispozici, nechá se být.
"""
import enum
import sys
import types


def _module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    if "." in name:
        mod.__path__ = []   # ať se dají importovat podmoduly
    sys.modules[name] = mod
    return mod


def _noop(*_args, **_kwargs):
    return None


def _decorator(fn):
    return fn


# --- voluptuous ----------------------------------------------------------------

class _Marker:
    def __init__(self, schema, default=None, **_kw):
        self.schema, self.default = schema, default

    def __hash__(self):
        return hash(self.schema)

    def __eq__(self, other):
        return isinstance(other, _Marker) and other.schema == self.schema

    def __repr__(self):
        return f"{type(self).__name__}({self.schema!r})"


class Optional(_Marker):
    pass


class Required(_Marker):
    pass


class Schema:
    def __init__(self, schema, **_kw):
        self.schema = schema

    def extend(self, other, **_kw):
        merged = dict(self.schema)
        merged.update(other)
        return Schema(merged)

    def __call__(self, data):
        return data


def _passthrough(*args, **_kw):
    return args[0] if len(args) == 1 else args


def install_voluptuous():
    if "voluptuous" in sys.modules:
        return
    try:
        import voluptuous  # noqa: F401
        return
    except ImportError:
        pass
    _module("voluptuous", Schema=Schema, Optional=Optional, Required=Required,
            All=_passthrough, Any=_passthrough, Coerce=_passthrough, In=_passthrough,
            Range=_passthrough, Length=_passthrough, Invalid=ValueError)


# --- homeassistant -------------------------------------------------------------

class SupportsResponse(enum.Enum):
    NONE = "none"
    OPTIONAL = "optional"
    ONLY = "only"


class Platform(str, enum.Enum):
    SENSOR = "sensor"


class HomeAssistantError(Exception):
    pass


class Unauthorized(HomeAssistantError):
    def __init__(self, context=None, permission=None):
        super().__init__(permission or "unauthorized")
        self.context, self.permission = context, permission


class ConfigEntry:
    def __init__(self, data=None, options=None, entry_id="test"):
        self.data, self.options, self.entry_id = dict(data or {}), dict(options or {}), entry_id
        self.title = "Nokturno"


class ConfigFlow:
    def __init_subclass__(cls, domain=None, **kwargs):
        cls.domain = domain


class OptionsFlow:
    pass


class HomeAssistantView:
    requires_auth = True

    def json(self, data, status_code=200):
        return (status_code, data)


class StaticPathConfig:
    def __init__(self, *args, **kwargs):
        self.args = args


class SensorEntity:
    hass = None

    def async_write_ha_state(self):
        pass

    def async_on_remove(self, fn):
        pass


def DeviceInfo(**kwargs):
    return dict(kwargs)


class _Selector:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class TextSelector(_Selector):
    pass


class TextSelectorType(enum.Enum):
    TEXT = "text"
    PASSWORD = "password"


async def _async_noop(*_args, **_kwargs):
    return None


def async_redact_data(data, to_redact):
    """Jako v HA: hodnoty pod uvedenými klíči nahradí `**REDACTED**`, rekurzivně."""
    if isinstance(data, dict):
        return {k: ("**REDACTED**" if k in to_redact and v not in ("", None) else async_redact_data(v, to_redact))
                for k, v in data.items()}
    if isinstance(data, list):
        return [async_redact_data(v, to_redact) for v in data]
    return data


def install_homeassistant():
    if "homeassistant" in sys.modules:
        return
    try:
        import homeassistant  # noqa: F401
        return
    except ImportError:
        pass
    _module("homeassistant")
    _module("homeassistant.components")
    _module("homeassistant.components.frontend", add_extra_js_url=_noop)
    _module("homeassistant.components.http", HomeAssistantView=HomeAssistantView, StaticPathConfig=StaticPathConfig)
    _module("homeassistant.components.http.auth", async_sign_path=_noop)
    _module("homeassistant.components.http.ban", process_wrong_login=_async_noop)
    _module("homeassistant.components.diagnostics", async_redact_data=async_redact_data)
    _module("homeassistant.components.sensor", SensorEntity=SensorEntity)
    _module("homeassistant.config_entries", ConfigEntry=ConfigEntry, ConfigFlow=ConfigFlow, OptionsFlow=OptionsFlow)
    _module("homeassistant.const", ATTR_ENTITY_ID="entity_id", Platform=Platform,
            EVENT_HOMEASSISTANT_STARTED="homeassistant_started", EVENT_SERVICE_REGISTERED="service_registered")
    _module("homeassistant.core", HomeAssistant=object, ServiceCall=object, SupportsResponse=SupportsResponse,
            callback=_decorator)
    _module("homeassistant.exceptions", HomeAssistantError=HomeAssistantError, Unauthorized=Unauthorized)
    _module("homeassistant.components.persistent_notification", async_create=_noop, async_dismiss=_noop)
    _module("homeassistant.helpers")
    _module("homeassistant.helpers.config_validation", string=str, boolean=bool, ensure_list=list,
            comp_entity_ids=str)
    _module("homeassistant.helpers.entity_registry", async_get=_noop)
    _module("homeassistant.helpers.selector", EntitySelector=_Selector, EntitySelectorConfig=_Selector,
            SelectSelector=_Selector, SelectSelectorConfig=_Selector,
            TextSelector=TextSelector, TextSelectorConfig=_Selector, TextSelectorType=TextSelectorType)
    _module("homeassistant.helpers.aiohttp_client", async_get_clientsession=_noop)
    _module("homeassistant.helpers.dispatcher", async_dispatcher_connect=_noop, async_dispatcher_send=_noop)
    _module("homeassistant.helpers.entity", DeviceInfo=DeviceInfo)
    _module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    _module("homeassistant.helpers.event", async_track_time_interval=_noop)
    _module("homeassistant.helpers.network", NoURLAvailableError=HomeAssistantError, get_url=_noop)
    _module("homeassistant.helpers.start", async_at_started=_noop)
    _module("homeassistant.loader", async_get_integration=_noop)
    _module("homeassistant.util", slugify=lambda s: "".join(c if c.isalnum() else "_" for c in str(s).lower()))
    _module("homeassistant.util.dt", now=_noop)


def install():
    install_voluptuous()
    install_homeassistant()
