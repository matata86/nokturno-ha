"""Diagnostika pro „Stáhnout diagnostiku" v HA — bez hesel, klíčů a účtů.

Bez tohohle souboru posílali uživatelé při hlášení chyb `core.config_entries`
i s hesly. Tady jde jen stav integrace: které zdroje jsou nastavené, předplatné
WebShare, počty ve frontě, verze.
"""
from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .config_flow import SECRET_KEYS
from .const import CONF_FS_USER, CONF_ST_EMAIL, CONF_STREAMUJ_USER, CONF_WS_USER, DOMAIN

# hesla a klíče + účty (e-maily, jména) — nic z toho není k ladění potřeba
TO_REDACT = set(SECRET_KEYS) | {CONF_WS_USER, CONF_STREAMUJ_USER, CONF_ST_EMAIL, CONF_FS_USER, "qbit_username",
                                "dav1_username", "dav2_username", "dav3_username"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    data = (hass.data.get(DOMAIN) or {}).get(entry.entry_id) or {}
    engine = data.get("engine")
    downloader = data.get("downloader")
    return {
        "entry": async_redact_data({**entry.data, **entry.options}, TO_REDACT),
        "sources": engine.sources() if engine else None,
        "sub_status": getattr(engine, "sub_status", None),
        "downloads": len(getattr(downloader, "jobs", {}) or {}),
        "torrents": len(getattr(downloader, "torrents", []) or []),
        "files": len(getattr(downloader, "files", []) or []),
        "services": data.get("services") or [],
    }
