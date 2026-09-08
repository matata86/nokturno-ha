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

from .const import DOMAIN, SIGNAL_DOWNLOADS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    add_entities([NokturnoDownloadsSensor(entry, data["downloader"], data.get("owners") or {})])


class NokturnoDownloadsSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Stahování"
    _attr_icon = "mdi:download"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "souborů"

    def __init__(self, entry: ConfigEntry, downloader, owners):
        self._downloader = downloader
        self._owners = owners
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
        # mobile_app se registruje až po nás — stav přepíšeme, jakmile jeho notify služby naskočí
        self.async_on_remove(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, lambda _e: self._updated())
        )

        @callback
        def _service_added(event) -> None:
            if event.data.get("domain") == "notify":
                self._updated()

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
        return sum(1 for job in self._downloader.jobs.values() if job["status"] in ("queued", "running"))

    @property
    def extra_state_attributes(self) -> dict:
        jobs = sorted(self._downloader.jobs.values(), key=lambda j: j["started"], reverse=True)
        running = next((j for j in jobs if j["status"] == "running"), None)
        return {
            "downloads": [
                {k: job[k] for k in ("id", "name", "status", "percent", "done", "size", "path", "error")}
                for job in jobs[:20]
            ],
            "current": running["name"] if running else "",
            "percent": running["percent"] if running else 0,
            "directory": self._downloader.directory,
            "files": self._downloader.files,
            # karta z toho plní výběr mobilu (u koho který telefon je)
            "notify_targets": self.notify_targets,
        }
