"""Nokturno pro Home Assistant — hledání ve WebShare, Sosáči a Luně, přehrání v Kodi.

Služby vracejí data (`response_variable`), takže s nimi umí pracovat dashboard,
skripty i hlasový asistent. Přehrávání v Kodi jde přes doplněk `plugin.video.nokturno`,
aby si Kodi vedl evidenci zhlédnuto/rozkoukáno; ostatní přehrávače dostanou přímé URL.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import time
import urllib.parse
from datetime import timedelta

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.components.http.auth import async_sign_path
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started
from homeassistant.loader import async_get_integration

from .const import (
    CONF_DOWNLOAD_DIR,
    CONF_EXTERNAL_HOST,
    CONF_STATS_ENABLED,
    CONF_SYNC_KEY,
    STATS_INTERVAL_HOURS,
    CONF_KODI_ENTITY,
    CONF_NOTIFY_TARGET,
    CONF_TRAKT_ID,
    CONF_TRAKT_SECRET,
    DEFAULT_DOWNLOAD_DIR,
    DOMAIN,
    EVENT_DOWNLOAD_DONE,
    EVENT_NEW_EPISODE,
    KODI_PLUGIN,
    SERVICE_CHECK_SERIES,
    SERVICE_CLEAR_CACHE,
    SERVICE_CLEAR_HISTORY,
    SERVICE_CONTINUE,
    SERVICE_CANCEL_DOWNLOAD,
    SERVICE_START_DOWNLOAD,
    SERVICE_DELETE_FILE,
    SERVICE_DOWNLOAD,
    SERVICE_DETAIL,
    SERVICE_EPISODES,
    SERVICE_PLAY,
    SERVICE_RESOLVE,
    SERVICE_SEARCH,
    SERVICE_SHARE_FILE,
    SERVICE_SEEN,
    SERVICE_TRAKT_AUTH,
    SERVICE_TRAKT_LIST,
    SERVICE_TRAKT_WATCHED,
    SERVICE_WANT,
    SERVICE_TORRENT,
    SERVICE_TORRENTS,
    SERVICE_SEND_LINK,
    SERVICE_STREAMS,
    SERVICE_WATCH,
    SIGNAL_DOWNLOADS,
    SIGNAL_TRAKT,
    SIGNAL_WATCHLIST,
    TRAKT_INTERVAL_HOURS,
    WATCH_INTERVAL_HOURS,
    EVENT_TRAKT_AVAILABLE,
)
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .downloader import Downloader
from .lib.stats import COLLECT_URL, Stats
from .lib.sync import apply_changes, collect_changes
from .engine import Engine, NokturnoError, _fold, split_episode_id

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

TRAKT_MAX = 40  # kolik titulů ze seznamu Traktu kontrolovat (každý = dotaz na všechny zdroje)

CARD_FILE = "www/nokturno-card.js"
CARD_URL = "/nokturno/nokturno-card.js"

SEARCH_SCHEMA = vol.Schema({
    vol.Required("query"): cv.string,
    vol.Optional("type", default="movie"): vol.In(["movie", "series", "webshare", "catalog", "catalog_series"]),
    vol.Optional("limit", default=20): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
})

STREAMS_SCHEMA = vol.Schema({
    vol.Optional("id"): cv.string,
    vol.Optional("query"): cv.string,
    vol.Optional("type", default="movie"): vol.In(["movie", "series"]),
    vol.Optional("alt"): vol.Any(cv.string, None),
    vol.Optional("series"): vol.Any(cv.string, None),
    vol.Optional("season"): vol.Any(vol.Coerce(int), None),
    vol.Optional("episode"): vol.Any(vol.Coerce(int), None),
    # jen pro čítače: karta název i rok zná, takže se kvůli nim nemusí znovu
    # sahat na metadata (`title`/`year` na výběr streamů nemají žádný vliv)
    vol.Optional("title"): vol.Any(cv.string, None),
    vol.Optional("year"): vol.Any(cv.string, vol.Coerce(int), None),
})

PLAY_SCHEMA = STREAMS_SCHEMA.extend({
    vol.Optional("id"): cv.string,
    vol.Optional("query"): cv.string,
    vol.Optional("name"): vol.Any(cv.string, None),
    vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids,
    vol.Optional("stream"): vol.Any(vol.Coerce(int), None),
    vol.Optional("url"): vol.Any(cv.string, None),
    vol.Optional("direct", default=False): cv.boolean,
})

RESOLVE_SCHEMA = STREAMS_SCHEMA.extend({
    vol.Optional("stream"): vol.Any(vol.Coerce(int), None),
    vol.Optional("url"): vol.Any(cv.string, None),
})

DOWNLOAD_SCHEMA = RESOLVE_SCHEMA.extend({
    vol.Optional("name"): vol.Any(cv.string, None),
})

SEND_LINK_SCHEMA = RESOLVE_SCHEMA.extend({
    vol.Required("notify_service"): cv.string,
    vol.Optional("name"): vol.Any(cv.string, None),
    vol.Optional("title", default="Nokturno"): cv.string,
})

DETAIL_SCHEMA = vol.Schema({
    vol.Required("id"): cv.string,
    vol.Optional("type", default="movie"): vol.In(["movie", "series"]),
})

EPISODES_SCHEMA = vol.Schema({
    vol.Required("id"): cv.string,
    vol.Optional("season"): vol.Any(vol.Coerce(int), None),
})

CANCEL_SCHEMA = vol.Schema({vol.Required("download_id"): cv.string})
START_SCHEMA = vol.Schema({vol.Required("download_id"): cv.string})

DELETE_SCHEMA = vol.Schema({vol.Required("path"): cv.string})

SHARE_SCHEMA = vol.Schema({
    vol.Required("path"): cv.string,
    vol.Optional("notify_service"): vol.Any(cv.string, None),
    vol.Optional("hours", default=24): vol.All(vol.Coerce(int), vol.Range(min=1, max=24 * 30)),
})

TORRENTS_SCHEMA = STREAMS_SCHEMA.extend({
    # kolik streamů karta už ukazuje — torrenty na ně navazují číslováním
    vol.Optional("offset", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=500)),
})

TORRENT_SCHEMA = vol.Schema({
    vol.Required("url"): cv.string,          # magnet nebo odkaz na .torrent z Prowlarru
    vol.Optional("name"): vol.Any(cv.string, None),
})

WANT_SCHEMA = vol.Schema({
    vol.Optional("id"): cv.string,
    vol.Optional("query"): cv.string,
    # `series` u uloženého dílu — jeho id samo o sobě metadata seriálu nenajde
    vol.Optional("series"): vol.Any(cv.string, None),
    vol.Optional("type", default="movie"): vol.In(["movie", "series"]),
    vol.Optional("title"): vol.Any(cv.string, None),
    vol.Optional("year"): vol.Any(vol.Coerce(int), None),
    vol.Optional("alt"): vol.Any(cv.string, None),
    vol.Optional("poster"): vol.Any(cv.string, None),
    vol.Optional("remove", default=False): cv.boolean,
})

WATCH_SCHEMA = vol.Schema({
    vol.Required("id"): cv.string,
    vol.Optional("title"): vol.Any(cv.string, None),
    vol.Optional("alt"): vol.Any(cv.string, None),
    vol.Optional("poster"): vol.Any(cv.string, None),
    vol.Optional("remove", default=False): cv.boolean,
})

CONTINUE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTITY_ID): cv.string})

SEEN_SCHEMA = vol.Schema({vol.Optional("id"): vol.Any(cv.string, None)})

TRAKT_WATCHED_SCHEMA = vol.Schema({
    vol.Required("id"): cv.string,
    vol.Optional("season"): vol.Any(vol.Coerce(int), None),
    vol.Optional("episode"): vol.Any(vol.Coerce(int), None),
    vol.Optional("remove", default=False): cv.boolean,
})


def _entry_data(hass: HomeAssistant) -> dict:
    """Data jediného config entry (integrace se zakládá jen jednou)."""
    data = hass.data.get(DOMAIN) or {}
    if not data:
        raise HomeAssistantError("Integrace Nokturno není nastavená.")
    return next(iter(data.values()))


def episode_target(engine: Engine, call_data: dict) -> tuple[str, str, str | None, str | None]:
    """Z parametrů služby udělá (typ, id k přehrání, id seriálu, alt id)."""
    ctype = call_data.get("type", "movie")
    item_id = call_data["id"]
    series = call_data.get("series")
    alt = call_data.get("alt")
    season, episode = call_data.get("season"), call_data.get("episode")
    if season is not None and episode is not None and ":" not in str(item_id).rsplit(":", 2)[-1]:
        base = series or item_id
        api = engine.api_for(base)
        found = None
        if hasattr(api, "episode_id"):
            try:
                found = api.episode_id(base, int(season), int(episode))
            except Exception:  # noqa: BLE001 – Luna používá tvar id:S:E
                found = None
        item_id = found or f"{base}:{int(season)}:{int(episode)}"
        series = base
        ctype = "series"
    return ctype, item_id, series, alt


def android_play_intent(url: str, mime: str = "video/*") -> str:
    """Android Intent URI, co telefonu nabídne přehrávače (VLC, MX Player…),
    ne jen otevření v prohlížeči.

    Syntaxe `intent:<scheme>://…` (jedno dvojtečka, scheme součástí opaque
    části) telefon spolehlivě neparsuje — spadne to na fallback (otevře se
    v prohlížeči jako obyčejný odkaz), přesně to, co dřív dělala. Správný
    tvar je `intent://<zbytek bez schématu>#Intent;scheme=<schema>;…;end`
    (scheme se předává zvlášť v Intent fragmentu). `S.browser_fallback_url`
    navíc dá Androidu vlastní odkaz pro případ, že žádný přehrávač intent
    nezachytí, místo aby spoléhal na implicitní chování prohlížeče.

    `async_sign_path()` vrací URL s cestou v čitelné, NEzakódované podobě
    (mezery a diakritika v názvu souboru zůstávají doslova) — normální HTTP
    klient/prohlížeč si je zakóduje sám při sestavení požadavku, ale tady jde
    o text vkládaný do URI schématu intentu, který se dál neupravuje. Bez
    zakódování se odkaz na první mezeře/nediakritickém znaku rozbije a
    přehrávač na telefonu ohlásí, že místo nejde přehrát. Odkazy z ostatních
    zdrojů (WebShare/Sosáč/Luna) už zakódované bývají — `unquote` před
    `quote` z toho dělá idempotentní krok, ať se nezakóduje podruhé."""
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/")
    query = urllib.parse.quote(urllib.parse.unquote(parts.query), safe="=&")
    opaque = urllib.parse.urlunsplit(("", parts.netloc, path, query, parts.fragment)).lstrip("/")
    # `S.browser_fallback_url` je hodnota uvnitř Intent fragmentu, ne URI samo
    # o sobě — Android ji chce zakódovanou celou naráz (`http%3A%2F%2F…`), ne
    # jako URI s jednotlivě escapnutou cestou jako `opaque` výše. Musí se
    # sestavit ze surových (rozbalených) částí, jinak by se %20 zakódovalo
    # podruhé na %2520 a fallback by mířil na neexistující adresu.
    raw_url = urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, urllib.parse.unquote(parts.path),
         urllib.parse.unquote(parts.query), parts.fragment))
    fallback = urllib.parse.quote(raw_url, safe="")
    return (f"intent://{opaque}#Intent;scheme={parts.scheme};"
            f"action=android.intent.action.VIEW;type={mime};"
            f"S.browser_fallback_url={fallback};end")


def kodi_url(ctype, item_id, series, alt, stream) -> str:
    """`plugin://` odkaz — Kodi přehraje vybraný stream a zapíše si zhlédnuto."""
    params = {"action": "play", "type": ctype, "id": item_id, "url": stream["url"]}
    if series:
        params["series"] = series
    if alt:
        params["alt"] = alt
    if stream.get("subtitles"):
        params["subs"] = "|".join(stream["subtitles"])
    return KODI_PLUGIN + "?" + urllib.parse.urlencode(params)


async def async_phone_owners(hass: HomeAssistant) -> dict[str, str]:
    """Vlastníci telefonů `{entry_id: jméno}` — jsou jen v `data.user_id` entry mobile_app.

    Čtení uživatele je async, proto se dělá jednou při startu; samotný seznam
    dostupných notify služeb se skládá až v senzoru (mobile_app se načítá později).
    """
    owners = {}
    for mobile in hass.config_entries.async_entries("mobile_app"):
        user_id = mobile.data.get("user_id")
        if not user_id:
            continue
        user = await hass.auth.async_get_user(user_id)
        if user:
            owners[mobile.entry_id] = user.name
    return owners


async def async_tailscale_running(hass: HomeAssistant) -> bool | None:
    """Běží na instanci addon Tailscale? `None` znamená, že se to nedá zjistit.

    Nevědomost nesmí adresu mimo síť zahodit — bez Supervisoru (instalace Core)
    se stav addonů zjistit nedá a uživatel ji přesto vyplnil záměrně."""
    try:
        from homeassistant.components.hassio import get_supervisor_client

        addons = (await get_supervisor_client(hass).addons.list()).addons
    except Exception as err:  # noqa: BLE001 – bez Supervisoru prostě nevíme
        _LOGGER.debug("seznam addonů: %s", err)
        return None
    # `state` je výčet, ne řetězec — porovnání s „started“ napřímo je vždy False
    return any("tailscale" in (a.slug or "")
               and str(getattr(a.state, "value", a.state)) == "started" for a in addons)


def kodi_endpoints(hass: HomeAssistant, entity_id: str | None = None) -> list[dict]:
    """Všechna Kodi v domácnosti: JSON-RPC adresa, přihlášení a jejich media_player entita.

    Dvě config entries na stejný host (např. `coreelec` a `coreelec_2`) se berou jako jedno Kodi.
    """
    registry = er.async_get(hass)
    players = {}
    for reg in registry.entities.values():
        if reg.platform == "kodi" and reg.domain == "media_player" and reg.config_entry_id:
            players.setdefault(reg.config_entry_id, reg.entity_id)
    out, seen = [], set()
    for entry in hass.config_entries.async_entries("kodi"):
        data = entry.data
        host = f"{data.get('host')}:{data.get('port', 8080)}"
        player = players.get(entry.entry_id)
        if entity_id and player != entity_id:
            continue
        if host in seen:
            continue
        seen.add(host)
        scheme = "https" if data.get("ssl") else "http"
        out.append({
            "entity_id": player,
            "name": entry.title,
            "url": f"{scheme}://{host}/jsonrpc",
            "auth": (data.get("username"), data.get("password")) if data.get("username") else None,
        })
    return out


async def _kodi_continue_one(hass: HomeAssistant, kodi: dict) -> list[dict]:
    session = async_get_clientsession(hass)
    payload = {"jsonrpc": "2.0", "id": 1, "method": "Files.GetDirectory", "params": {
        "directory": f"{KODI_PLUGIN}?action=continue", "media": "video",
        "properties": ["title", "thumbnail", "art", "year", "plot", "season", "episode", "showtitle"],
    }}
    kwargs = {"json": payload, "timeout": 30}
    if kodi["auth"]:
        import aiohttp
        kwargs["auth"] = aiohttp.BasicAuth(*kodi["auth"])
    async with session.post(kodi["url"], **kwargs) as resp:
        data = await resp.json(content_type=None)
    if "error" in data:
        raise HomeAssistantError(f"{kodi['name']}: {data['error'].get('message')}")
    items = []
    for f in (data.get("result") or {}).get("files") or []:
        art = f.get("art") or {}
        items.append({
            "label": f.get("label") or f.get("title") or "",
            "title": re.sub(r"\s*\(\d{4}\)\s*$", "", f.get("title") or f.get("label") or ""),
            "file": f.get("file"),
            "thumbnail": kodi_image(art.get("thumb") or art.get("poster") or f.get("thumbnail") or ""),
            "fanart": kodi_image(art.get("landscape") or art.get("fanart") or ""),
            "year": f.get("year") or (re.search(r"\((\d{4})\)\s*$", f.get("label") or "") or [None, None])[1],
            "plot": (f.get("plot") or "")[:400],
            "series": f.get("showtitle") or "",
            "season": f.get("season"),
            "episode": f.get("episode"),
            # odkud to je — karta pustí pokračování na tomtéž Kodi
            "entity_id": kodi["entity_id"],
            "player": kodi["name"],
        })
    return items


def _art_by_title(engine: Engine, items: list[dict]) -> None:
    """Obrázky k položkám bez nich (Sosáč) — podle názvu a roku z TMDB přes Lunu (v executoru)."""
    from .lib.enrich import enrich_one

    for item in items:
        if item.get("fanart") or item.get("thumbnail"):
            continue
        is_episode = bool(item.get("series"))
        meta = {"name": item["series"] if is_episode else item["title"], "year": "" if is_episode else (item.get("year") or "")}
        enrich_one(meta, engine.luna, engine.store, "series" if is_episode else "movie")
        item["fanart"] = meta.get("background") or ""
        item["thumbnail"] = meta.get("poster") or ""


async def kodi_continue(hass: HomeAssistant, entity_id: str | None, engine: Engine | None = None) -> list[dict]:
    """„Pokračovat ve sledování" ze všech Kodi (nebo jen z jednoho), vypnutá se přeskočí."""
    import asyncio

    kodis = kodi_endpoints(hass, entity_id)
    if not kodis:
        raise HomeAssistantError("Kodi není v Home Assistantu nastavené.")
    results = await asyncio.gather(*(_kodi_continue_one(hass, k) for k in kodis), return_exceptions=True)
    items = []
    seen = {}
    for kodi, result in zip(kodis, results):
        if isinstance(result, Exception):
            _LOGGER.debug("rozkoukané z %s: %s", kodi["name"], result)
            continue
        for item in result:
            key = (
                (item.get("title") or "").strip().lower(),
                item.get("year"),
                (item.get("series") or "").strip().lower(),
                item.get("season"),
                item.get("episode"),
            )
            existing = seen.get(key)
            if existing is None:
                seen[key] = item
                item["players"] = [{"entity_id": item["entity_id"], "player": item["player"]}]
                items.append(item)
            else:
                # stejný titul rozehraný na víc Kodi – necháme jednu položku, karta nabídne výběr zdroje
                existing["players"].append({"entity_id": item["entity_id"], "player": item["player"]})
    if engine and any(not (i.get("fanart") or i.get("thumbnail")) for i in items):
        await hass.async_add_executor_job(_art_by_title, engine, items)
    return items


def kodi_image(value: str) -> str:
    """Kodi obaluje obrázky do `image://<zakódované URL>/` — prohlížeč potřebuje holé URL.
    Mrtvé náhledy Sosáče (movies.sosac.tv, 404) radši vynechat, karta ukáže podklad."""
    if not value:
        return ""
    if value.startswith("image://"):
        value = urllib.parse.unquote(value[len("image://"):].rstrip("/"))
    if not value.startswith("http") or "movies.sosac.tv" in value:
        return ""
    return value


async def async_register_card(hass: HomeAssistant) -> None:
    """Naservíruje kartu a načte ji v prohlížeči — bez ručního přidávání do zdrojů Lovelace."""
    base = os.path.dirname(__file__)
    path = os.path.join(base, CARD_FILE)
    if not os.path.exists(path):
        return
    def _version():
        try:
            with open(os.path.join(base, "manifest.json"), encoding="utf-8") as handle:
                return json.load(handle).get("version", "0")
        except OSError:
            return "0"

    version = await hass.async_add_executor_job(_version)  # čtení souboru mimo event loop
    try:
        await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, path, True)])
    except Exception as err:  # noqa: BLE001 – opakovaná registrace při reloadu
        _LOGGER.debug("statická cesta %s: %s", CARD_URL, err)
    # verze v dotazu shodí cache prohlížeče, jakmile se integrace aktualizuje
    url = f"{CARD_URL}?v={version}"
    # Karta patří do Lovelace resources, ne do extra_module_url: to se vyhodnotí ještě
    # před tím, než si frontend nasadí vlastní registr prvků (scoped custom elements),
    # a taková karta pak pro HA „neexistuje“ (hui-error-card: Custom element doesn't exist).
    try:
        registered = await async_register_resource(hass, url)
    except Exception as err:  # noqa: BLE001 – YAML mód Lovelace nebo starší HA
        _LOGGER.debug("Lovelace resource: %s", err)
        registered = False
    if not registered:  # YAML mód Lovelace – jiná cesta ke kartě není
        add_extra_js_url(hass, url)


async def async_register_resource(hass: HomeAssistant, url: str) -> bool:
    """Zapíše kartu mezi Lovelace resources; False = nejde to (YAML mód)."""
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    if resources is None:
        return False
    if not getattr(resources, "loaded", True):
        await resources.async_load()
    for item in resources.async_items():
        if str(item.get("url", "")).split("?")[0] == CARD_URL:
            if item["url"] != url:
                await resources.async_update_item(item["id"], {"url": url})
            return True
    await resources.async_create_item({"res_type": "module", "url": url})
    return True


class NokturnoSyncView(HomeAssistantView):
    """Střed synchronizace pro Kodi doplňky (viz lib/sync.py).

    Bez přihlášení HA — Kodi nemá jak vzít token uživatele; místo toho vlastní
    klíč z nastavení integrace v hlavičce `X-Nokturno-Key`. Data jsou jen
    zhlédnuto/rozkoukané/Můj seznam, nic se tím nedá spustit ani přehrát.
    """

    url = "/api/nokturno/sync"
    name = "api:nokturno:sync"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def post(self, request):
        try:
            data = _entry_data(self.hass)
        except HomeAssistantError:
            return self.json({"error": "integrace není nastavená"}, status_code=503)
        key = data["entry"].data.get(CONF_SYNC_KEY) or ""
        if not key or request.headers.get("X-Nokturno-Key") != key:
            return self.json({"error": "špatný klíč"}, status_code=403)
        try:
            body = await request.json()
        except ValueError:
            return self.json({"error": "neplatný JSON"}, status_code=400)
        store = data["engine"].store
        since = int(body.get("since") or 0)

        def work():
            applied = apply_changes(store, body.get("changes"))
            return {"now": int(time.time()), "applied": applied, "changes": collect_changes(store, since)}

        result = await self.hass.async_add_executor_job(work)
        _LOGGER.debug("sync %s: přijato %s, vráceno %s", body.get("device"), result["applied"],
                      len(result["changes"]["watched"]) + len(result["changes"]["favlog"]))
        return self.json(result)


def _encode_signed(signed: str) -> str:
    """Zakóduje část cesty podepsaného odkazu (mezery, diakritika), query ponechá."""
    path, sep, query = signed.partition("?")
    return urllib.parse.quote(path, safe="/") + sep + query


class NokturnoFilesView(HomeAssistantView):
    """Seznam souborů stažených integrací — pro položku „Staženo v HA" v Kodi doplňku.

    Vrací podepsané RELATIVNÍ odkazy (`async_sign_path`); absolutní adresu si
    doplněk složí z adresy, přes kterou k HA přistupuje (může to být i Nabu Casa,
    pak odkaz hraje i mimo domácí síť). Ověření stejným klíčem jako `/sync`.
    """

    url = "/api/nokturno/files"
    name = "api:nokturno:files"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request):
        from datetime import timedelta as _timedelta

        from homeassistant.components import media_source

        try:
            data = _entry_data(self.hass)
        except HomeAssistantError:
            return self.json({"error": "integrace není nastavená"}, status_code=503)
        key = data["entry"].data.get(CONF_SYNC_KEY) or ""
        if not key or request.headers.get("X-Nokturno-Key") != key:
            return self.json({"error": "špatný klíč"}, status_code=403)
        downloader = data["downloader"]
        await downloader.async_refresh_files()
        out = []
        for f in sorted(downloader.files, key=lambda x: x.get("modified") or 0, reverse=True):
            rel = os.path.relpath(os.path.abspath(f["path"]), "/media").replace(os.sep, "/")
            try:
                resolved = await media_source.async_resolve_media(
                    self.hass, f"media-source://media_source/local/{rel}", None)
            except Exception as err:  # noqa: BLE001 – mimo media_dirs apod.
                _LOGGER.debug("soubor %s nejde nabídnout: %s", f["path"], err)
                continue
            out.append({
                "name": f["name"],
                "size": f.get("size") or 0,
                "subtitles": f.get("subtitles") or 0,
                # podpis platí pár hodin; seznam se stahuje čerstvý při každém otevření.
                # async_sign_path vrací cestu NEzakódovanou (mezery, diakritika) — část
                # cesty je nutné zakódovat, query s podpisem nechat; HA si cestu před
                # ověřením podpisu dekóduje zpět, takže %20 == mezera a podpis sedí
                "path": _encode_signed(async_sign_path(self.hass, resolved.url, _timedelta(hours=6))),
            })
        return self.json({"files": out})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await async_register_card(hass)
    # starší instalace klíč nemají — doplnit jednou (spustí to jeden reload přes update listener)
    if not entry.data.get(CONF_SYNC_KEY):
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_SYNC_KEY: secrets.token_hex(6)})
    if not hass.data.get(f"{DOMAIN}_sync_view"):
        hass.http.register_view(NokturnoSyncView(hass))
        hass.http.register_view(NokturnoFilesView(hass))
        hass.data[f"{DOMAIN}_sync_view"] = True
    options = {**entry.data, **entry.options}
    if options.get(CONF_EXTERNAL_HOST) and await async_tailscale_running(hass) is False:
        _LOGGER.warning("addon Tailscale neběží — odkazy mimo síť se nebudou přepisovat")
        options = {**options, CONF_EXTERNAL_HOST: ""}
    engine = await hass.async_add_executor_job(
        Engine, options, hass.config.path(f".storage/{DOMAIN}")
    )
    # čítače leží vedle ostatních dat integrace; Stats si soubor drží sám
    stats = await hass.async_add_executor_job(Stats, hass.config.path(f".storage/{DOMAIN}"))
    stats_version = str((await async_get_integration(hass, DOMAIN)).version or "")
    downloader = Downloader(hass, options.get(CONF_DOWNLOAD_DIR) or DEFAULT_DOWNLOAD_DIR,
                            store=engine.store)
    # odkazy z WebShare po pár hodinách vyprší — po restartu si downloader vyžádá nový
    downloader.resolver = engine.resolve
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "engine": engine,
        "downloader": downloader,
        "entry": entry,
        "owners": await async_phone_owners(hass),
        "stats_send": None,   # doplní se níž, až closure existuje
    }

    async def notify(title, message, url=None):
        """Oznámení: do mobilu z nastavení, jinak do oznámení HA."""
        target = (options.get(CONF_NOTIFY_TARGET) or "").split(".")[-1]
        if target and hass.services.has_service("notify", target):
            data = {"title": title, "message": message}
            if url:
                data["data"] = {"url": url, "clickAction": url}
            await hass.services.async_call("notify", target, data, blocking=False)
            return
        await hass.services.async_call("persistent_notification", "create",
                                       {"title": title, "message": message, "notification_id": f"{DOMAIN}_{abs(hash(message)) % 10_000}"},
                                       blocking=False)

    async def _download_done(job):
        hass.bus.async_fire(EVENT_DOWNLOAD_DONE, {"name": job["name"], "path": job["path"], "size": job["size"]})
        await notify("Nokturno — staženo", f"{job['name']} je připravený v Médiích.")

    downloader.on_done = _download_done

    # --- Trakt.tv -------------------------------------------------------------

    def trakt():
        """Klient Traktu, nebo None, když nejsou vyplněné údaje aplikace."""
        from .lib.trakt_api import TraktApi

        if not options.get(CONF_TRAKT_ID) or not options.get(CONF_TRAKT_SECRET):
            return None
        return TraktApi(options[CONF_TRAKT_ID], options[CONF_TRAKT_SECRET],
                        tokens=engine.store.load("trakt", {}),
                        on_tokens=lambda data: engine.store.save("trakt", data))

    async def handle_trakt_auth(call: ServiceCall):
        """Přihlášení kódem: pošle kód do oznámení a na pozadí čeká na potvrzení."""
        from .lib.trakt_api import TraktError

        api = trakt()
        if api is None:
            raise HomeAssistantError("Nejsou vyplněné Client ID a Secret aplikace na Trakt.tv.")
        try:
            code = await hass.async_add_executor_job(api.device_code)
        except TraktError as err:
            raise HomeAssistantError(f"Trakt: {err}") from err
        await notify("Nokturno — přihlášení k Trakt.tv",
                     f"Otevři {code.get('verification_url')} a zadej kód {code.get('user_code')}",
                     code.get("verification_url"))

        async def _wait():
            try:
                await hass.async_add_executor_job(api.poll_token, code["device_code"])
            except TraktError as err:
                await notify("Nokturno — Trakt.tv", f"Přihlášení se nepovedlo: {err}")
                return
            await notify("Nokturno — Trakt.tv", "Účet je propojený.")

        hass.async_create_background_task(_wait(), "nokturno_trakt_auth")
        return {"user_code": code.get("user_code"), "url": code.get("verification_url")}

    def trakt_cache():
        return engine.store.load("trakt_list", {})

    def wantlist():
        """Vlastní seznam „chci vidět" — funguje i bez Traktu (ten od 7/2026 chce VIP)."""
        return engine.store.load("wantlist", {})

    async def handle_want(call: ServiceCall):
        """Titul do seznamu k zhlédnutí. Bez `id` stačí `query` — název se hlídá,
        dokud se titul v některém zdroji neobjeví (film, který ještě nikde není)."""
        data = wantlist()
        query = (call.data.get("query") or "").strip()
        wid = call.data.get("id") or (f"q:{query.lower()}" if query else "")
        if not wid:
            raise HomeAssistantError("Chybí `id` nebo `query`.")
        if call.data.get("remove"):
            data.pop(wid, None)
            # senzor čte uloženou kontrolu, ne wantlist — bez tohohle by položka v kartě zůstala
            cache = trakt_cache()
            if cache.pop(wid, None) is not None:
                await hass.async_add_executor_job(engine.store.save, "trakt_list", cache)
        else:
            item = data.get(wid) or {"id": wid, "added": dt_util.now().isoformat()}
            item.update({k: call.data[k] for k in ("type", "title", "year", "alt", "poster", "series")
                         if call.data.get(k)})
            item.setdefault("type", "movie")
            if query:
                item["query"] = query
                item.setdefault("title", query)
            data[wid] = item
        await hass.async_add_executor_job(engine.store.save, "wantlist", data)
        async_dispatcher_send(hass, SIGNAL_TRAKT)
        if not call.data.get("remove"):
            hass.async_create_task(check_trakt())
        return {"count": len(data), "watching": wid in data}

    async def check_trakt(_now=None):
        """Seznam „k zhlédnutí" z Traktu + kontrola, co už jde pustit.

        Jednou denně; když titul, který stream neměl, ho nově má, přijde oznámení.
        """
        items = list(wantlist().values())
        api = trakt()
        if api is not None and api.logged_in():
            for kind in ("movies", "shows"):
                try:
                    items += await hass.async_add_executor_job(api.watchlist, kind)
                except Exception as err:  # noqa: BLE001 – výpadek Traktu nesmí shodit kontrolu
                    _LOGGER.debug("trakt watchlist %s: %s", kind, err)
        if not items:
            # i prázdný seznam se musí propsat — jinak by v kartě zůstala odebraná položka
            if trakt_cache():
                await hass.async_add_executor_job(engine.store.save, "trakt_list", {})
                async_dispatcher_send(hass, SIGNAL_TRAKT)
            return {}
        known = trakt_cache()
        fresh, newly = {}, []
        seen_ids = set()
        for item in items[:TRAKT_MAX]:
            if item["id"] in seen_ids:  # týž titul ve vlastním seznamu i na Traktu
                continue
            seen_ids.add(item["id"])
            before = known.get(item["id"]) or {}
            target, alt = item["id"], item.get("alt")
            if str(target).startswith("q:"):
                # ruční položka — zkusit, jestli už titul některý zdroj zná
                try:
                    found = await hass.async_add_executor_job(
                        engine.search, item.get("type", "movie"), item.get("query") or item.get("title") or "", 5)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("hledání %s: %s", item.get("query"), err)
                    found = []
                # hledání vrací i nepodobné tituly („Duna 3" → „Vánoční prázdniny"),
                # takže bereme jen shodu, kde jsou všechna slova dotazu v názvu
                wanted = [w for w in re.split(r"[^\w]+", _fold(item.get("query") or "")) if len(w) > 2]
                hit = next((f for f in found
                            if not wanted or all(w in _fold(f.get("title") or "") for w in wanted)), None)
                if hit is None:
                    fresh[item["id"]] = {**item, "streams": 0, "best": "", "pending": True,
                                         "checked": dt_util.now().isoformat()}
                    continue
                target, alt = hit["id"], hit.get("alt")
                item = {**item, "title": hit.get("title") or item.get("title"), "year": hit.get("year") or item.get("year"),
                        "poster": hit.get("poster") or item.get("poster"), "found_id": hit["id"], "alt": alt}
            try:
                streams = await hass.async_add_executor_job(
                    engine.streams_or_torrents, item["type"], target, alt, item.get("series"))
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("trakt streamy %s: %s", item["id"], err)
                streams = []
            record = {**item, "type": item.get("type", "movie"), "streams": len(streams),
                      "best": streams[0]["label"] if streams else "",
                      # titul zatím jen na trackeru — pustit ho znamená napřed stáhnout
                      "torrent": bool(streams) and all(s.get("kind") == "torrent" for s in streams),
                      "checked": dt_util.now().isoformat()}
            if streams and not before.get("streams") and before:
                newly.append(record)
            fresh[item["id"]] = record
        await hass.async_add_executor_job(engine.store.save, "trakt_list", fresh)
        async_dispatcher_send(hass, SIGNAL_TRAKT)
        for record in newly:
            hass.bus.async_fire(EVENT_TRAKT_AVAILABLE, {k: record[k] for k in ("id", "title", "type", "streams")})
            await notify("Nokturno — už je k dispozici",
                         f"{record['title']}{f' ({record['year']})' if record.get('year') else ''} má nově {record['streams']} streamů.")
        return fresh

    async def handle_trakt_list(call: ServiceCall):
        fresh = await check_trakt()
        items = sorted(fresh.values(), key=lambda i: (not i.get("streams"), i.get("title") or ""))
        return {"count": len(items), "available": sum(1 for i in items if i.get("streams")), "items": items}

    async def handle_trakt_watched(call: ServiceCall):
        from .lib.trakt_api import TraktError

        api = trakt()
        if api is None or not api.logged_in():
            raise HomeAssistantError("Trakt.tv není propojený (spusť nokturno.trakt_auth).")
        base_id, season, episode = split_episode_id(call.data["id"])
        season = call.data.get("season", season)
        episode = call.data.get("episode", episode)
        func = api.unmark_watched if call.data.get("remove") else api.mark_watched
        try:
            await hass.async_add_executor_job(func, base_id, season, episode)
        except TraktError as err:
            raise HomeAssistantError(f"Trakt: {err}") from err
        return {"id": base_id, "season": season, "episode": episode, "removed": call.data.get("remove", False)}

    async def trakt_scrobble_start(ctype, item_id):
        """Po spuštění přehrávání dá Traktu vědět, co se hraje (jen když je propojený)."""
        api = trakt()
        if api is None or not api.logged_in():
            return
        base_id, season, episode = split_episode_id(item_id)
        try:
            await hass.async_add_executor_job(api.scrobble, "start", base_id, 0, season, episode)
        except Exception as err:  # noqa: BLE001 – Trakt nesmí shodit přehrávání
            _LOGGER.debug("trakt scrobble: %s", err)

    # --- sledované seriály ----------------------------------------------------

    def watchlist():
        # soubor je po startu v paměti (viz předčtení níže), tady už se na disk nesahá
        return engine.store.load("watchlist", {})

    async def watchlist_save(data):
        await hass.async_add_executor_job(engine.store.save, "watchlist", data)
        async_dispatcher_send(hass, SIGNAL_WATCHLIST)

    def _latest_aired(episodes):
        """Poslední odvysílaná epizoda (bez speciálů a bez budoucích termínů)."""
        today = dt_util.now().date().isoformat()
        aired = [e for e in episodes if e.get("season") and (not e.get("released") or e["released"][:10] <= today)]
        if not aired:
            return None
        last = max(aired, key=lambda e: (e["season"], e["episode"]))
        return {"season": last["season"], "episode": last["episode"], "title": last.get("title") or "",
                "id": last.get("id"), "released": (last.get("released") or "")[:10]}

    async def check_series(_now=None):
        """Projde sledované seriály: nový díl se hlásí, až když má stream (ne jen když byl odvysílán).

        `latest` = poslední odvysílaný podle metadat, `available` = nejnovější díl se streamem.
        Zkouší se jen díly novější než dosud dostupný, nejvýš tři nejnovější (každý dotaz stojí pár sekund).
        """
        data = watchlist()
        changed = False
        for sid, item in list(data.items()):
            try:
                episodes = await hass.async_add_executor_job(engine.episodes, sid, None)
            except (NokturnoError, Exception) as err:  # noqa: BLE001 – jeden seriál nesmí zastavit zbytek
                _LOGGER.debug("kontrola %s: %s", sid, err)
                continue
            latest = _latest_aired(episodes)
            if not latest:
                continue
            if latest != item.get("latest"):
                item["latest"] = latest
                changed = True
            known = item.get("available") or {}
            known_key = (known.get("season", 0), known.get("episode", 0))
            today = dt_util.now().date().isoformat()
            aired = sorted((e for e in episodes if e.get("season") and (not e.get("released") or e["released"][:10] <= today)),
                           key=lambda e: (e["season"], e["episode"]))
            budget = [6]  # kolik dotazů na streamy si jedna kontrola seriálu může dovolit

            async def options(ep):
                """Čím se dá díl pustit — streamy, a když žádné nejsou, torrenty."""
                if budget[0] <= 0:
                    return []
                budget[0] -= 1
                try:
                    return await hass.async_add_executor_job(
                        engine.streams_or_torrents, "series", ep["id"], item.get("alt"), sid)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("streamy %s: %s", ep["id"], err)
                    return []

            def describe(ep, opts=()):
                return {"season": ep["season"], "episode": ep["episode"], "title": ep.get("title") or "",
                        "id": ep["id"], "released": (ep.get("released") or "")[:10],
                        # díl jen na trackeru — karta to má říct, stažení chvíli trvá
                        "torrent": bool(opts) and all(o.get("kind") == "torrent" for o in opts)}

            found = None
            if not known:
                # poprvé: od nejnovější sezóny zpět, poslední díl sezóny — první sezóna se streamem vyhrává
                last_per_season = {}
                for ep in aired:
                    last_per_season[ep["season"]] = ep
                for season in sorted(last_per_season, reverse=True)[:3]:
                    opts = await options(last_per_season[season])
                    if opts:
                        found = describe(last_per_season[season], opts)
                        known_key = (season, last_per_season[season]["episode"])
                        break
            # pak po dílech dopředu — díly přibývají postupně, první chybějící ukončí hledání
            for ep in (e for e in aired if (e["season"], e["episode"]) > known_key):
                opts = await options(ep)
                if not opts:
                    break
                found = describe(ep, opts)
            if found:
                first_check = "available" not in item and "checked" not in item
                item["available"] = found
                if not first_check:  # při zařazení jen zapamatovat, hlásit až další
                    item["new"] = found
                    hass.bus.async_fire(EVENT_NEW_EPISODE, {"id": sid, "title": item.get("title"), **found})
                    await notify("Nokturno — nový díl ke sledování",
                                 f"{item.get('title')}: {found['season']}x{found['episode']:02d} {found['title']}".strip())
                changed = True
            item["checked"] = dt_util.now().isoformat()
            changed = True
        if changed:
            await watchlist_save(data)
        return data

    async def handle_watch(call: ServiceCall):
        data = watchlist()
        sid = call.data["id"]
        if call.data.get("remove") or (sid in data and not call.data.get("title")):
            data.pop(sid, None)
            await watchlist_save(data)
            return {"watching": False, "count": len(data)}
        entry_item = data.get(sid) or {"id": sid}
        entry_item.update({k: call.data[k] for k in ("title", "alt", "poster") if call.data.get(k)})
        entry_item.setdefault("added", dt_util.now().isoformat())
        data[sid] = entry_item
        await watchlist_save(data)
        hass.async_create_task(check_series())
        return {"watching": True, "count": len(data)}

    async def handle_check_series(call: ServiceCall):
        data = await check_series()
        return {"count": len(data), "series": list(data.values())}

    async def handle_continue(call: ServiceCall):
        items = await kodi_continue(hass, call.data.get(ATTR_ENTITY_ID), engine)
        return {"count": len(items), "items": items}

    async def handle_seen(call: ServiceCall):
        """Označí nový díl (u jednoho nebo všech seriálů) za viděný — zhasne v kartě i v senzoru."""
        data = watchlist()
        sid = call.data.get("id")
        changed = False
        for key, item in data.items():
            if (sid in (None, key)) and item.get("new"):
                item.pop("new", None)
                changed = True
        if changed:
            await watchlist_save(data)
        return {"count": sum(1 for i in data.values() if i.get("new"))}

    async def handle_clear_history(call: ServiceCall):
        await hass.async_add_executor_job(engine.clear_history)
        async_dispatcher_send(hass, SIGNAL_WATCHLIST)

    async def handle_clear_cache(call: ServiceCall):
        """Vymaže cache API (hledání, streamy, katalogy) — ne historii ani Můj seznam."""
        await hass.async_add_executor_job(engine.store.clear_cache)

    async def poll_torrents(_now=None):
        """Průběh torrentů z qBittorrentu do fronty stahování.

        Klient o sobě sám nedá vědět, takže se na něj ptáme — ale jen když je
        co sledovat, jinak by to zbytečně tikalo každých pár sekund navěky."""
        rows = await hass.async_add_executor_job(engine.torrent_jobs)
        if rows == downloader.torrents:
            return
        downloader.torrents = rows
        async_dispatcher_send(hass, SIGNAL_DOWNLOADS)
        # dokončený torrent zmizí z fronty a objeví se jako soubor ve složce
        await downloader.async_refresh_files()

    def _stats_send(force=False):
        """Blokující — patří do executoru. Nikdy nevyhodí výjimku ven."""
        if not options.get(CONF_STATS_ENABLED, True):
            return
        if not force and not stats.due():
            return
        ok, why = stats.send(
            COLLECT_URL,
            version=stats_version, platform="Home Assistant",
            kodi=hass.config.as_dict().get("version", ""),
            lang=(hass.config.language or "")[:8],
            agent="HomeAssistant nokturno",
        )
        if not ok:
            _LOGGER.debug("statistiky neodeslány: %s", why)

    def _note_view(item_id, title="", year=None, kind="movie"):
        """Zobrazení streamů titulu — stejná událost jako v Kodi doplňku."""
        if not options.get(CONF_STATS_ENABLED, True):
            return
        stats.note_use()
        if item_id:
            stats.note_play(item_id, title or "", year, kind)

    async def stats_tick(_now=None):
        await hass.async_add_executor_job(_stats_send)

    entry.async_on_unload(async_track_time_interval(hass, stats_tick, timedelta(hours=STATS_INTERVAL_HOURS)))
    # Interval se poprvé ozve až za šest hodin, takže nová instalace se v přehledu
    # objevila nejdřív po nich — a když se mezitím restartovalo HA, tak vůbec.
    # Hlásíme se proto hned po startu, stejně jako služba v Kodi doplňku; `stats.due()`
    # uvnitř `_stats_send` drží odstup, aby se restartem nedalo posílat častěji.
    entry.async_on_unload(async_at_started(hass, stats_tick))
    hass.data[DOMAIN][entry.entry_id]["stats_send"] = _stats_send
    entry.async_on_unload(async_track_time_interval(hass, poll_torrents, timedelta(seconds=5)))
    entry.async_on_unload(async_track_time_interval(hass, check_series, timedelta(hours=WATCH_INTERVAL_HOURS)))
    entry.async_on_unload(async_track_time_interval(hass, check_trakt, timedelta(hours=TRAKT_INTERVAL_HOURS)))

    async def _in_executor(func, *args):
        try:
            return await hass.async_add_executor_job(func, *args)
        except NokturnoError as err:
            raise HomeAssistantError(str(err)) from err

    async def _with_query(call_data):
        """`query` místo `id`: najde první výsledek a doplní id/alt — pro hlasovku jedním krokem."""
        if call_data.get("id") or call_data.get("url") or not call_data.get("query"):
            return call_data
        ctype = "series" if call_data.get("type") == "series" else "movie"
        found = await _in_executor(engine.find_first, ctype, call_data["query"])
        data = dict(call_data)
        data["id"] = found["id"]
        data["alt"] = found.get("alt")
        data["type"] = ctype
        if ctype == "series" and data.get("season") is None:
            # bez čísla dílu první epizoda první sezóny
            data["season"], data["episode"] = 1, 1
        return data

    async def _streams(call_data):
        call_data = await _with_query(call_data)
        if not call_data.get("id"):
            raise HomeAssistantError("Chybí `id` titulu nebo `query`.")
        ctype, item_id, series, alt = episode_target(engine, call_data)
        return ctype, item_id, series, alt, await _in_executor(engine.streams, ctype, item_id, alt, series)

    async def _chosen_stream(call_data):
        """Vybraný stream (`stream` index) nebo přímé `url`, jinak nejlepší. `query` místo `id` se dohledá."""
        call_data = await _with_query(call_data)
        if not call_data.get("id") and not call_data.get("url"):
            raise HomeAssistantError("Chybí `id` titulu, `query` nebo `url` streamu.")
        if call_data.get("url"):
            return None, None, None, None, {"url": call_data["url"], "label": "", "subtitles": []}
        ctype, item_id, series, alt, streams = await _streams(call_data)
        if not streams:
            raise HomeAssistantError("Pro tento titul se nenašel žádný stream.")
        index = call_data.get("stream")
        if index is not None and not 0 <= int(index) < len(streams):
            raise HomeAssistantError(f"Stream č. {index} neexistuje (nalezeno {len(streams)}).")
        return ctype, item_id, series, alt, streams[int(index or 0)]

    # --- služby -------------------------------------------------------------

    async def handle_search(call: ServiceCall):
        kind = call.data.get("type", "movie")
        limit = call.data.get("limit", 20)
        if kind == "webshare":
            results = await _in_executor(engine.search_webshare, call.data["query"], limit)
        elif kind.startswith("catalog"):
            # databáze filmů — najde i tituly, které zatím žádný zdroj nemá
            results = await _in_executor(engine.search_catalog,
                                         "series" if kind == "catalog_series" else "movie", call.data["query"], limit)
        else:
            results = await _in_executor(engine.search, kind, call.data["query"], limit)
        if results:
            await hass.async_add_executor_job(engine.add_history, call.data["query"])
            async_dispatcher_send(hass, SIGNAL_WATCHLIST)
        return {"count": len(results), "results": results}

    async def handle_streams(call: ServiceCall):
        ctype, item_id, series, _alt, streams = await _streams(call.data)
        year = call.data.get("year")
        await hass.async_add_executor_job(
            _note_view, item_id, call.data.get("title") or "",
            int(year) if str(year or "").isdigit() else None,
            "series" if series or ctype == "series" else "movie",
        )
        return {"count": len(streams), "streams": streams}

    async def handle_torrents(call: ServiceCall):
        """Torrenty titulu z trackerů. Zvlášť od streamů: trackery odpovídají
        v řádu sekund, takže se hledá až když si o to karta řekne."""
        call_data = await _with_query(dict(call.data))
        if not call_data.get("id"):
            raise HomeAssistantError("Chybí `id` titulu nebo `query`.")
        ctype, item_id, series, _alt = episode_target(engine, call_data)
        rows = await _in_executor(engine.torrents, ctype, item_id, series,
                                  int(call.data.get("offset") or 0))
        return {"count": len(rows), "streams": rows}

    async def handle_detail(call: ServiceCall):
        """Detail titulu z databáze filmů (popis, plakát) — pro tituly, které zdroje nemají."""
        return await _in_executor(engine.catalog_detail, call.data.get("type", "movie"), call.data["id"])

    async def handle_episodes(call: ServiceCall):
        episodes = await _in_executor(engine.episodes, call.data["id"], call.data.get("season"))
        seasons = sorted({e["season"] for e in episodes})
        return {"count": len(episodes), "seasons": seasons, "episodes": episodes}

    async def handle_resolve(call: ServiceCall):
        _c, _i, _s, _a, stream = await _chosen_stream(call.data)
        # odkaz je určený pro cizí přehrávač → rovnou v podobě funkční i mimo domácí síť
        url = await _in_executor(engine.resolve, stream.get("ws_url") or stream["url"], True)
        return {"url": url, "label": stream.get("label", ""), "subtitles": stream.get("subtitles") or []}

    async def handle_play(call: ServiceCall):
        call_data = await _with_query(call.data)
        ctype, item_id, series, alt, stream = await _chosen_stream(call_data)
        targets = call_data.get(ATTR_ENTITY_ID) or options.get(CONF_KODI_ENTITY)
        if not targets:
            raise HomeAssistantError("Není zadaný přehrávač (entity_id) ani výchozí Kodi v nastavení.")
        if isinstance(targets, str):
            targets = [targets]
        registry = er.async_get(hass)
        for entity_id in targets:
            # Kodi umí plugin:// — přehraje přes doplněk Nokturno, takže titul skončí
            # v „Pokračovat ve sledování“ a resume drží v Kodi; ostatní potřebují přímé URL
            entry_reg = registry.async_get(entity_id)
            is_kodi = bool(entry_reg and entry_reg.platform == "kodi")
            plugin_ok = is_kodi and not call_data.get("direct")
            if plugin_ok and str(stream.get("url", "")).startswith("ws:"):
                # soubor z fulltextu WebShare — doplněk má vlastní akci, odkaz si přeloží sám
                media_id = KODI_PLUGIN + "?" + urllib.parse.urlencode({
                    "action": "play_ws", "ident": stream["url"][3:],
                    "name": call_data.get("name") or stream.get("label") or "",
                })
            elif plugin_ok and item_id:
                # titulky z WebShare musí do Kodi už jako http odkazy (doplněk `ws:` nepřekládá)
                resolved = dict(stream)
                resolved["subtitles"] = [await _in_executor(engine.resolve, u) for u in (stream.get("subtitles") or [])]
                media_id = kodi_url(ctype, item_id, series, alt, resolved)
            else:
                media_id = await _in_executor(engine.resolve, stream["url"])
            await hass.services.async_call(
                "media_player", "play_media",
                {ATTR_ENTITY_ID: entity_id, "media_content_type": "video", "media_content_id": media_id},
                blocking=True,
            )
        if item_id:
            hass.async_create_task(trakt_scrobble_start(ctype, item_id))
        return {"stream": stream.get("label", ""), "entity_id": targets}

    async def handle_download(call: ServiceCall):
        ctype, item_id, series, alt, stream = await _chosen_stream(call.data)
        url = await _in_executor(engine.resolve, stream["url"])
        name = call.data.get("name")
        if not name and item_id:
            meta, video = await _in_executor(engine.meta, ctype, item_id, series)
            name = (video or {}).get("title") or meta.get("_title") or meta.get("name") or item_id
            if video:
                name = f"{meta.get('name') or ''} {int(video.get('season') or 0)}x" \
                       f"{int(video.get('episode') or 0):02d} {video.get('title') or ''}".strip()
        needed = float(stream.get("size_gb") or 0)
        if needed and downloader.free_gb and needed > downloader.free_gb - 0.5:
            raise HomeAssistantError(f"Na disku je jen {downloader.free_gb:.1f} GB, soubor má {needed:.1f} GB.")
        subs = [await _in_executor(engine.resolve, u) for u in (stream.get("subtitles") or [])]
        job = downloader.add(url, name or "nokturno", {"stream": stream.get("label", "")},
                             subtitles=subs, source_url=stream.get("url", ""))
        return {"download_id": job["id"], "path": job["path"], "name": job["name"]}

    async def handle_send_link(call: ServiceCall):
        _c, _i, _s, _a, stream = await _chosen_stream(call.data)
        url = await _in_executor(engine.resolve, stream.get("ws_url") or stream["url"], True)
        name = call.data.get("name") or stream.get("label") or "Nokturno"
        title = call.data.get("title", "Nokturno")
        raw = call.data["notify_service"]
        short = raw.split(".")[-1]
        # `notify.sm_s921b` bývá entita nové notify platformy, odesílá až `notify.mobile_app_sm_s921b`
        # odkazy na streamy nemají příponu, takže by je Android stáhl jako neznámý soubor;
        # intent s typem video/* místo toho nabídne přehrávače (VLC, MX Player…)
        play_uri = android_play_intent(url)
        for service in (short, f"mobile_app_{short}"):
            if hass.services.has_service("notify", service):
                await hass.services.async_call("notify", service, {
                    "title": title,
                    "message": f"{name}\n{url}",
                    "data": {
                        "url": play_uri,
                        "clickAction": play_uri,
                        "actions": [
                            {"action": "URI", "title": "Přehrát", "uri": play_uri},
                            {"action": "URI", "title": "Otevřít odkaz", "uri": url},
                        ],
                    },
                }, blocking=True)
                return {"url": url, "play_uri": play_uri, "notify_service": f"notify.{service}"}
        entity_id = raw if raw.startswith("notify.") else f"notify.{short}"
        if hass.states.get(entity_id) is None:
            raise HomeAssistantError(f"Notifikační služba ani entita „{raw}“ neexistuje.")
        # entita umí jen text — odkaz proto rovnou do zprávy
        await hass.services.async_call("notify", "send_message", {
            ATTR_ENTITY_ID: entity_id, "title": title, "message": f"{name}\n{url}",
        }, blocking=True)
        return {"url": url, "notify_service": entity_id}

    async def handle_cancel(call: ServiceCall):
        job_id = call.data["download_id"]
        # torrent nedrží fronta integrace, ale qBittorrent — zrušit ho znamená
        # odebrat ho z klienta i s rozdělanými daty
        if str(job_id).startswith("qb:"):
            await hass.async_add_executor_job(engine.cancel_torrent, str(job_id)[3:])
            downloader.torrents = [t for t in downloader.torrents if t["id"] != job_id]
            async_dispatcher_send(hass, SIGNAL_DOWNLOADS)
            return
        downloader.remove(job_id)

    async def handle_start_download(call: ServiceCall):
        """Ruční „spustit" u čekající položky — jede hned, souběžně s tím, co už stahuje."""
        job_id = call.data["download_id"]
        if not downloader.start_now(job_id):
            raise HomeAssistantError("Položka už nečeká ve frontě.")

    async def handle_share_file(call: ServiceCall):
        """Odkaz na stažený soubor přes veřejnou adresu HA (Nabu Casa), volitelně rovnou do mobilu."""
        from datetime import timedelta as _timedelta

        from homeassistant.components import media_source
        from homeassistant.helpers.network import get_url

        path = os.path.abspath(call.data["path"])
        root = os.path.abspath(downloader.directory)
        if os.path.commonpath([path, root]) != root or not os.path.exists(path):
            raise HomeAssistantError(f"Soubor {call.data['path']} ve složce pro stahování není.")
        rel = os.path.relpath(path, "/media").replace(os.sep, "/")
        try:
            resolved = await media_source.async_resolve_media(
                hass, f"media-source://media_source/local/{rel}", None)
        except Exception as err:  # noqa: BLE001 – složka mimo media_dirs apod.
            raise HomeAssistantError(f"Soubor nejde sdílet přes Média: {err}") from err
        signed = async_sign_path(hass, resolved.url, _timedelta(hours=call.data["hours"]))
        try:
            base_url = get_url(hass, prefer_external=True, allow_cloud=True)
        except Exception:  # noqa: BLE001 – bez externí adresy aspoň vnitřní
            base_url = get_url(hass, prefer_external=False)
        url = base_url.rstrip("/") + signed
        target = (call.data.get("notify_service") or options.get(CONF_NOTIFY_TARGET) or "").split(".")[-1]
        name = os.path.basename(path)
        if target:
            play_uri = android_play_intent(url)
            for service in (target, f"mobile_app_{target}"):
                if hass.services.has_service("notify", service):
                    await hass.services.async_call("notify", service, {
                        "title": "Nokturno — stažený film",
                        "message": f"{name}\n{url}",
                        "data": {"url": play_uri, "clickAction": play_uri,
                                 "actions": [{"action": "URI", "title": "Přehrát", "uri": play_uri},
                                             {"action": "URI", "title": "Otevřít odkaz", "uri": url}]},
                    }, blocking=True)
                    break
        return {"url": url, "name": name, "hours": call.data["hours"]}

    async def handle_torrent(call: ServiceCall):
        """Zařadí torrent do stahování v qBittorrentu. Video se pak objeví
        ve složce stahování jako každý jiný stažený soubor."""
        name = (call.data.get("name") or "").strip()
        await hass.async_add_executor_job(engine.download_torrent, call.data["url"], name)
        return {"queued": True, "name": name}

    async def handle_delete_file(call: ServiceCall):
        path = call.data["path"]
        # film ze staženého torrentu by v klientu zůstal seedovat a po smazání
        # hlásil chybějící data — odebrat ho, ale mazání souboru na tom nestojí
        try:
            await hass.async_add_executor_job(engine.forget_torrent, path)
        except Exception as err:  # noqa: BLE001 – klient nemusí běžet
            _LOGGER.debug("torrent k %s nejde odebrat: %s", path, err)
        try:
            await downloader.async_delete(path)
        except (OSError, ValueError) as err:
            raise HomeAssistantError(f"Smazání selhalo: {err}") from err

    services = (
        (SERVICE_SEARCH, handle_search, SEARCH_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_STREAMS, handle_streams, STREAMS_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_EPISODES, handle_episodes, EPISODES_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_DETAIL, handle_detail, DETAIL_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_RESOLVE, handle_resolve, RESOLVE_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_PLAY, handle_play, PLAY_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_DOWNLOAD, handle_download, DOWNLOAD_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_SEND_LINK, handle_send_link, SEND_LINK_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_CANCEL_DOWNLOAD, handle_cancel, CANCEL_SCHEMA, SupportsResponse.NONE),
        (SERVICE_START_DOWNLOAD, handle_start_download, START_SCHEMA, SupportsResponse.NONE),
        (SERVICE_DELETE_FILE, handle_delete_file, DELETE_SCHEMA, SupportsResponse.NONE),
        (SERVICE_SHARE_FILE, handle_share_file, SHARE_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_CONTINUE, handle_continue, CONTINUE_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_WATCH, handle_watch, WATCH_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_CHECK_SERIES, handle_check_series, vol.Schema({}), SupportsResponse.OPTIONAL),
        (SERVICE_CLEAR_HISTORY, handle_clear_history, vol.Schema({}), SupportsResponse.NONE),
        (SERVICE_CLEAR_CACHE, handle_clear_cache, vol.Schema({}), SupportsResponse.NONE),
        (SERVICE_SEEN, handle_seen, SEEN_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_TRAKT_AUTH, handle_trakt_auth, vol.Schema({}), SupportsResponse.OPTIONAL),
        (SERVICE_TRAKT_LIST, handle_trakt_list, vol.Schema({}), SupportsResponse.OPTIONAL),
        (SERVICE_WANT, handle_want, WANT_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_TORRENTS, handle_torrents, TORRENTS_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_TORRENT, handle_torrent, TORRENT_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_TRAKT_WATCHED, handle_trakt_watched, TRAKT_WATCHED_SCHEMA, SupportsResponse.OPTIONAL),
    )
    for name, handler, schema, response in services:
        hass.services.async_register(DOMAIN, name, handler, schema=schema, supports_response=response)

    await downloader.async_refresh_files()
    await downloader.async_restore()  # navázat na stahování přerušené restartem
    # sledované seriály a historie do paměti store hned — senzory je čtou z event loopu
    await hass.async_add_executor_job(engine.store.load, "watchlist", {})
    await hass.async_add_executor_job(engine.store.load, "history", [])
    await hass.async_add_executor_job(engine.store.load, "trakt_list", {})
    await hass.async_add_executor_job(engine.store.load, "wantlist", {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        data["downloader"].shutdown()
        # poslední hlášení — jinak by u vypnuté instance chybělo posledních pár hodin
        if data.get("stats_send"):
            await hass.async_add_executor_job(data["stats_send"], True)
        if not hass.data[DOMAIN]:
            for name in (SERVICE_SEARCH, SERVICE_STREAMS, SERVICE_EPISODES, SERVICE_RESOLVE, SERVICE_PLAY,
                         SERVICE_DOWNLOAD, SERVICE_SEND_LINK, SERVICE_CANCEL_DOWNLOAD, SERVICE_START_DOWNLOAD,
                         SERVICE_DELETE_FILE,
                         SERVICE_SHARE_FILE, SERVICE_CONTINUE, SERVICE_WATCH, SERVICE_CHECK_SERIES, SERVICE_CLEAR_HISTORY,
                         SERVICE_CLEAR_CACHE,
                         SERVICE_SEEN, SERVICE_TRAKT_AUTH, SERVICE_TRAKT_LIST, SERVICE_TRAKT_WATCHED,
                         SERVICE_WANT):
                hass.services.async_remove(DOMAIN, name)
    return unloaded
