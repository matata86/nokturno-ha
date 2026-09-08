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
import urllib.parse
from datetime import timedelta

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_DOWNLOAD_DIR,
    CONF_KODI_ENTITY,
    CONF_NOTIFY_TARGET,
    DEFAULT_DOWNLOAD_DIR,
    DOMAIN,
    EVENT_DOWNLOAD_DONE,
    EVENT_NEW_EPISODE,
    KODI_PLUGIN,
    SERVICE_CHECK_SERIES,
    SERVICE_CLEAR_HISTORY,
    SERVICE_CONTINUE,
    SERVICE_CANCEL_DOWNLOAD,
    SERVICE_DELETE_FILE,
    SERVICE_DOWNLOAD,
    SERVICE_EPISODES,
    SERVICE_PLAY,
    SERVICE_RESOLVE,
    SERVICE_SEARCH,
    SERVICE_SEND_LINK,
    SERVICE_STREAMS,
    SERVICE_WATCH,
    SIGNAL_WATCHLIST,
    WATCH_INTERVAL_HOURS,
)
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .downloader import Downloader
from .engine import Engine, NokturnoError

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

CARD_FILE = "www/nokturno-card.js"
CARD_URL = "/nokturno/nokturno-card.js"

SEARCH_SCHEMA = vol.Schema({
    vol.Required("query"): cv.string,
    vol.Optional("type", default="movie"): vol.In(["movie", "series", "webshare"]),
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

EPISODES_SCHEMA = vol.Schema({
    vol.Required("id"): cv.string,
    vol.Optional("season"): vol.Any(vol.Coerce(int), None),
})

CANCEL_SCHEMA = vol.Schema({vol.Required("download_id"): cv.string})

DELETE_SCHEMA = vol.Schema({vol.Required("path"): cv.string})

WATCH_SCHEMA = vol.Schema({
    vol.Required("id"): cv.string,
    vol.Optional("title"): vol.Any(cv.string, None),
    vol.Optional("alt"): vol.Any(cv.string, None),
    vol.Optional("poster"): vol.Any(cv.string, None),
    vol.Optional("remove", default=False): cv.boolean,
})

CONTINUE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTITY_ID): cv.string})


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
    for kodi, result in zip(kodis, results):
        if isinstance(result, Exception):
            _LOGGER.debug("rozkoukané z %s: %s", kodi["name"], result)
            continue
        items.extend(result)
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
    add_extra_js_url(hass, url)
    # extra_module_url žije v index.html, který si mobilní aplikace drží v cache;
    # Lovelace resources čte frontend živě — proto kartu zapíšeme i tam (stejná URL = modul se načte jednou)
    try:
        await async_register_resource(hass, url)
    except Exception as err:  # noqa: BLE001 – YAML mód Lovelace nebo starší HA
        _LOGGER.debug("Lovelace resource: %s", err)


async def async_register_resource(hass: HomeAssistant, url: str) -> None:
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    if resources is None:
        return
    if not getattr(resources, "loaded", True):
        await resources.async_load()
    for item in resources.async_items():
        if str(item.get("url", "")).split("?")[0] == CARD_URL:
            if item["url"] != url:
                await resources.async_update_item(item["id"], {"url": url})
            return
    await resources.async_create_item({"res_type": "module", "url": url})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await async_register_card(hass)
    options = {**entry.data, **entry.options}
    engine = await hass.async_add_executor_job(
        Engine, options, hass.config.path(f".storage/{DOMAIN}")
    )
    downloader = Downloader(hass, options.get(CONF_DOWNLOAD_DIR) or DEFAULT_DOWNLOAD_DIR)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "engine": engine,
        "downloader": downloader,
        "entry": entry,
        "owners": await async_phone_owners(hass),
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
            candidates = sorted(
                (e for e in episodes if e.get("season") and (e["season"], e["episode"]) > known_key
                 and (not e.get("released") or e["released"][:10] <= today)),
                key=lambda e: (e["season"], e["episode"]), reverse=True,
            )[:3]
            found = None
            for ep in candidates:
                try:
                    streams = await hass.async_add_executor_job(engine.streams, "series", ep["id"], item.get("alt"), sid)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("streamy %s: %s", ep["id"], err)
                    continue
                if streams:
                    found = {"season": ep["season"], "episode": ep["episode"], "title": ep.get("title") or "",
                             "id": ep["id"], "released": (ep.get("released") or "")[:10], "streams": len(streams)}
                    break
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

    async def handle_clear_history(call: ServiceCall):
        await hass.async_add_executor_job(engine.clear_history)
        async_dispatcher_send(hass, SIGNAL_WATCHLIST)

    entry.async_on_unload(async_track_time_interval(hass, check_series, timedelta(hours=WATCH_INTERVAL_HOURS)))

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
        else:
            results = await _in_executor(engine.search, kind, call.data["query"], limit)
        if results:
            await hass.async_add_executor_job(engine.add_history, call.data["query"])
            async_dispatcher_send(hass, SIGNAL_WATCHLIST)
        return {"count": len(results), "results": results}

    async def handle_streams(call: ServiceCall):
        _ctype, _item, _series, _alt, streams = await _streams(call.data)
        return {"count": len(streams), "streams": streams}

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
        job = downloader.add(url, name or "nokturno", {"stream": stream.get("label", "")}, subtitles=subs)
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
        play_uri = f"intent:{url}#Intent;action=android.intent.action.VIEW;type=video/*;end"
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
        downloader.remove(call.data["download_id"])

    async def handle_delete_file(call: ServiceCall):
        try:
            await downloader.async_delete(call.data["path"])
        except (OSError, ValueError) as err:
            raise HomeAssistantError(f"Smazání selhalo: {err}") from err

    services = (
        (SERVICE_SEARCH, handle_search, SEARCH_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_STREAMS, handle_streams, STREAMS_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_EPISODES, handle_episodes, EPISODES_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_RESOLVE, handle_resolve, RESOLVE_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_PLAY, handle_play, PLAY_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_DOWNLOAD, handle_download, DOWNLOAD_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_SEND_LINK, handle_send_link, SEND_LINK_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_CANCEL_DOWNLOAD, handle_cancel, CANCEL_SCHEMA, SupportsResponse.NONE),
        (SERVICE_DELETE_FILE, handle_delete_file, DELETE_SCHEMA, SupportsResponse.NONE),
        (SERVICE_CONTINUE, handle_continue, CONTINUE_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_WATCH, handle_watch, WATCH_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_CHECK_SERIES, handle_check_series, vol.Schema({}), SupportsResponse.OPTIONAL),
        (SERVICE_CLEAR_HISTORY, handle_clear_history, vol.Schema({}), SupportsResponse.NONE),
    )
    for name, handler, schema, response in services:
        hass.services.async_register(DOMAIN, name, handler, schema=schema, supports_response=response)

    await downloader.async_refresh_files()
    # sledované seriály a historie do paměti store hned — senzory je čtou z event loopu
    await hass.async_add_executor_job(engine.store.load, "watchlist", {})
    await hass.async_add_executor_job(engine.store.load, "history", [])
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
        if not hass.data[DOMAIN]:
            for name in (SERVICE_SEARCH, SERVICE_STREAMS, SERVICE_EPISODES, SERVICE_RESOLVE, SERVICE_PLAY,
                         SERVICE_DOWNLOAD, SERVICE_SEND_LINK, SERVICE_CANCEL_DOWNLOAD, SERVICE_DELETE_FILE,
                         SERVICE_CONTINUE, SERVICE_WATCH, SERVICE_CHECK_SERIES, SERVICE_CLEAR_HISTORY):
                hass.services.async_remove(DOMAIN, name)
    return unloaded
