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

from .const import DOMAIN, SIGNAL_DOWNLOADS, SIGNAL_TRAKT, SIGNAL_WATCHLIST


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    add_entities([
        NokturnoDownloadsSensor(entry, data["downloader"], data.get("owners") or {}, data["engine"]),
        NokturnoEpisodesSensor(entry, data["engine"]),
        NokturnoTraktSensor(entry, data["engine"]),
    ])


class NokturnoDownloadsSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Stahování"
    _attr_icon = "mdi:download"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "souborů"

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
        }


class NokturnoEpisodesSensor(SensorEntity):
    """Sledované seriály — kolik jich má nový díl, v atributech seznam."""

    _attr_has_entity_name = True
    _attr_name = "Nové díly"
    _attr_icon = "mdi:television-play"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "seriálů"

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
    """Seznam „k zhlédnutí" z Traktu — kolik titulů už má stream."""

    _attr_has_entity_name = True
    _attr_name = "K zhlédnutí"
    _attr_icon = "mdi:bookmark-check-outline"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "titulů"

    def __init__(self, entry: ConfigEntry, engine):
        self._engine = engine
        self._attr_unique_id = f"{entry.entry_id}_trakt"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_TRAKT, self._updated))

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()

    @property
    def _items(self) -> list[dict]:
        data = self._engine.store.load("trakt_list", {})
        return sorted(data.values(), key=lambda i: (not i.get("streams"), i.get("title") or ""))

    @property
    def native_value(self) -> int:
        return sum(1 for item in self._items if item.get("streams"))

    @property
    def extra_state_attributes(self) -> dict:
        return {"total": len(self._items), "items": self._items[:60]}
