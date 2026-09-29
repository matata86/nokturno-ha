"""Nokturno 9.0.2 – jen v původním repozitáři. Integrace se přestěhovala do
nokturno-app/nokturno-ha; tahle verze nic nedělá, jen to ohlásí v Opravách a na kartě."""
from __future__ import annotations

import logging
import os

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

_LOGGER = logging.getLogger(__name__)

DOMAIN = "nokturno"
VERSION = "9.0.2"
NOVE_REPO = "https://github.com/nokturno-app/nokturno-ha"
CARD_FILE = "www/nokturno-card.js"
CARD_URL = "/nokturno/nokturno-card.js"


async def async_register_card(hass: HomeAssistant) -> None:
    """Karta na stejné adrese jako dřív, ať ji dashboardy najdou a ukážou upozornění."""
    path = os.path.join(os.path.dirname(__file__), CARD_FILE)
    try:
        await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, path, True)])
    except Exception as err:  # noqa: BLE001 – opakovaná registrace při reloadu
        _LOGGER.debug("statická cesta %s: %s", CARD_URL, err)
    url = f"{CARD_URL}?v={VERSION}"
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    try:
        if resources is None:
            raise LookupError
        if not getattr(resources, "loaded", True):
            await resources.async_load()
        for item in resources.async_items():
            if str(item.get("url", "")).split("?")[0] == CARD_URL:
                if item["url"] != url:
                    await resources.async_update_item(item["id"], {"url": url})
                return
        await resources.async_create_item({"res_type": "module", "url": url})
    except Exception:  # noqa: BLE001 – YAML mód Lovelace
        add_extra_js_url(hass, url)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await async_register_card(hass)
    ir.async_create_issue(
        hass, DOMAIN, "prestehovano", is_fixable=False, is_persistent=False,
        severity=ir.IssueSeverity.ERROR, translation_key="prestehovano",
        translation_placeholders={"url": NOVE_REPO}, learn_more_url=NOVE_REPO)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
