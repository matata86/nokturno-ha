"""Senzor se stavem stahování (počet aktivních, detail v atributech)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_SERVICE_REGISTERED
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import (CONTINUE_CACHE_KEY, DOMAIN, SIGNAL_ACCOUNTS, SIGNAL_DOWNLOADS, SIGNAL_TRAKT,
                    SIGNAL_WATCHLIST)
from .lib import accounts as accounts_lib


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    add_entities([
        NokturnoDownloadsSensor(entry, data["downloader"], data.get("owners") or {}, data["engine"]),
        NokturnoEpisodesSensor(entry, data["engine"]),
        NokturnoTraktSensor(entry, data["engine"]),
        NokturnoSourcesSensor(entry, data["engine"]),
    ])


class NokturnoDownloadsSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "downloads"
    _attr_icon = "mdi:download"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "souborů"
    # atributy čte jen karta; do recorderu nepatří — stav se přepisuje každé 2 s během
    # stahování a nesl celý výpis složky (desítky MB/den v databázi HA)
    # `current`/`percent`/`speed`/`eta` se během stahování mění každé 2 s a `free_gb` s nimi —
    # do 6.1.4 z toho recorder zapisoval ~1800 řádků `states` za hodinu stahování
    _unrecorded_attributes = frozenset({"downloads", "files", "search_history", "sources", "notify_targets",
                                        "subscription", "stream_progress", "search_progress", "directory",
                                        "continue_cache", "current", "percent", "speed", "eta", "free_gb"})

    def __init__(self, entry: ConfigEntry, downloader, owners, engine):
        self._downloader = downloader
        self._owners = owners
        self._engine = engine
        self._attr_unique_id = f"{entry.entry_id}_downloads"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Nokturno",
            manufacturer="matata86",
            model="WebShare · Sosáč · Luna",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_DOWNLOADS, self._updated)
        )
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_WATCHLIST, self._updated)
        )
        # mobile_app se registruje až po nás — stav přepíšeme, jakmile jeho notify služby naskočí.
        # Posluchače musí být @callback, jinak je HA spustí ve vlákně a async_write_ha_state se pohorší.
        @callback
        def _started(_event) -> None:
            self._updated()

        @callback
        def _service_added(event) -> None:
            if event.data.get("domain") == "notify":
                self._updated()

        self.async_on_remove(self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _started))

        self.async_on_remove(self.hass.bus.async_listen(EVENT_SERVICE_REGISTERED, _service_added))

    @property
    def notify_targets(self) -> list[dict]:
        """Telefony s aplikací HA, na které jde poslat odkaz."""
        targets = []
        for mobile in self.hass.config_entries.async_entries("mobile_app"):
            device = mobile.data.get("device_name") or mobile.title
            service = f"mobile_app_{slugify(device)}"
            if not self.hass.services.has_service("notify", service):
                continue
            targets.append({
                "service": f"notify.{service}",
                "device": device,
                "user": self._owners.get(mobile.entry_id, ""),
            })
        targets.sort(key=lambda t: (t["user"], t["device"]))
        return targets

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        own = sum(1 for job in self._downloader.jobs.values() if job["status"] in ("queued", "running"))
        return own + len(self._downloader.torrents)

    @property
    def extra_state_attributes(self) -> dict:
        jobs = sorted(self._downloader.jobs.values(), key=lambda j: j.get("started") or 0, reverse=True)
        running = next((j for j in jobs if j["status"] == "running"), None)
        # torrenty jdou před vlastní frontu — jsou to ty, které zrovna běží
        rows = self._downloader.torrents + [
            {k: job.get(k) for k in ("id", "name", "status", "percent", "done", "size",
                                     "path", "error", "speed", "eta")}
            for job in jobs[:20]
        ]
        return {
            "downloads": rows,
            "current": running["name"] if running else "",
            "percent": running["percent"] if running else 0,
            "speed": running.get("speed") if running else 0,
            "eta": running.get("eta") if running else None,
            "directory": self._downloader.directory,
            "files": self._downloader.files,
            "free_gb": round(self._downloader.free_gb, 1),
            "search_history": self._engine.history(),
            # karta podle toho pozná, co má nabízet — bez Prowlarru neukazuje
            # tlačítko na hledání torrentů
            "sources": self._engine.sources(),
            # karta z toho plní výběr mobilu (u koho který telefon je)
            "notify_targets": self.notify_targets,
            # dny do vypršení předplatného WebShare — plní `check_subscription` v __init__.py
            "subscription": self._engine.sub_status,
            # postup načítání streamů právě otevřeného titulu — {} když nic neběží
            "stream_progress": self._engine.stream_progress,
            # postup právě probíhajícího hledání titulu — {} když nic neběží
            "search_progress": self._engine.search_progress,
            # poslední živý stav „Pokračovat ve sledování" — karta ho ukáže hned po
            # načtení, než dorazí čerstvá odpověď z živého dotazu na Kodi
            "continue_cache": self._engine.store.load(CONTINUE_CACHE_KEY, []),
        }


class NokturnoEpisodesSensor(SensorEntity):
    """Sledované seriály — kolik jich má nový díl, v atributech seznam."""

    _attr_has_entity_name = True
    _attr_translation_key = "new_episodes"
    _attr_icon = "mdi:television-play"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "seriálů"
    _unrecorded_attributes = frozenset({"series"})

    def __init__(self, entry: ConfigEntry, engine):
        self._engine = engine
        self._attr_unique_id = f"{entry.entry_id}_new_episodes"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_WATCHLIST, self._updated)
        )

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()

    @property
    def _watchlist(self) -> dict:
        return self._engine.store.load("watchlist", {})

    @property
    def native_value(self) -> int:
        return sum(1 for item in self._watchlist.values() if item.get("new"))

    @property
    def extra_state_attributes(self) -> dict:
        items = sorted(self._watchlist.values(), key=lambda i: i.get("title") or "")
        return {
            "series": [
                {k: item.get(k) for k in ("id", "title", "alt", "poster", "latest", "available", "new", "checked")}
                for item in items
            ],
        }


class NokturnoTraktSensor(SensorEntity):
    """Hlídané z Traktu — kolik titulů už má stream."""

    _attr_has_entity_name = True
    _attr_translation_key = "trakt"
    _attr_icon = "mdi:bookmark-check-outline"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "titulů"
    _unrecorded_attributes = frozenset({"items", "favourites"})

    def __init__(self, entry: ConfigEntry, engine):
        self._engine = engine
        self._attr_unique_id = f"{entry.entry_id}_trakt"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_TRAKT, self._updated))
        # „Můj seznam" se mění i mimo Trakt tok — synchronizací z jiného Kodi/Stremia
        # (`NokturnoSyncView` posílá `SIGNAL_WATCHLIST`, ne `SIGNAL_TRAKT`)
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_WATCHLIST, self._updated))

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()

    @property
    def _items(self) -> list[dict]:
        data = self._engine.store.load("trakt_list", {})
        flags = self._engine.store.load("trakt_flags", {})
        items = []
        for item in data.values():
            item = {**item, "flagged": item["id"] in flags}
            items.append(item)
        # lze pustit → kontrolovat dál (má streamy, ale ne v požadované kvalitě) → zatím ne
        return sorted(items, key=lambda i: (not i.get("streams"), i.get("flagged"), i.get("title") or ""))

    @property
    def _favourites(self) -> list[dict]:
        """Můj seznam — lokální oblíbené, sdílené s Kodi/Stremiem přes `favlog`."""
        store = self._engine.store
        items = []
        for key in store.favourites():
            info = store.item(key) or {}
            items.append({
                "id": key,
                "title": info.get("title") or key,
                "year": info.get("year"),
                "poster": info.get("poster"),
                "alt": info.get("alt"),
                "type": info.get("type", "movie"),
            })
        return items

    @property
    def native_value(self) -> int:
        return sum(1 for item in self._items if item.get("streams"))

    @property
    def extra_state_attributes(self) -> dict:
        return {"total": len(self._items), "items": self._items[:60], "favourites": self._favourites[:60]}


class NokturnoSourcesSensor(SensorEntity):
    """Stav účtů napříč zdroji — kolik jich potřebuje zásah, detail v atributech.

    Stejná data, jakými si Kodi kreslí první položku menu (`lib/accounts.py`):
    vypršelé předplatné WebShare, pauza HellSpy po 429, Luna, která neběží, účet
    bez Premium. Věta se skládá až tady — jádro dává kód příčiny a čísla, protože
    Kodi je potřebuje krátké do jednoho řádku a tohle je chce v atributech.

    Hodnota se **nikdy nepočítá po síti**: stav zjišťuje časovač v `__init__.py`
    a tenhle senzor čte jen uložený záznam, aby čtení atributů nezdrželo smyčku
    událostí HA.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "sources"
    _attr_icon = "mdi:server-network"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "zdrojů"
    _unrecorded_attributes = frozenset({"sources", "problems"})

    def __init__(self, entry: ConfigEntry, engine):
        self._engine = engine
        self._attr_unique_id = f"{entry.entry_id}_sources"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_ACCOUNTS, self._updated)
        )

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()

    @property
    def _rows(self) -> list[dict]:
        saved = self._engine.store.load(accounts_lib.STORE, {}) or {}
        return accounts_lib.compose(saved, self._engine.sources())

    @property
    def native_value(self) -> int:
        """Kolik zdrojů potřebuje zásah — 0 znamená, že je všechno v pořádku."""
        return len(accounts_lib.problems(self._rows))

    @property
    def extra_state_attributes(self) -> dict:
        rows = self._rows
        return {
            "sources": [{k: row[k] for k in ("source", "level", "code", "detail", "stale")}
                        for row in rows if row["code"] != "off"],
            "problems": [row["source"] for row in accounts_lib.problems(rows)],
        }
