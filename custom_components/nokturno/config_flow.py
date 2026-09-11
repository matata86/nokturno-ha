"""Nastavení integrace — účty zdrojů a předvolby přehrávání."""

from __future__ import annotations

import secrets

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DOWNLOAD_DIR,
    CONF_PROWLARR_URL,
    CONF_PROWLARR_KEY,
    CONF_QBIT_URL,
    CONF_QBIT_USER,
    CONF_QBIT_PASS,
    CONF_STATS_ENABLED,
    CONF_SYNC_KEY,
    DEFAULT_PROWLARR_URL,
    DEFAULT_QBIT_URL,
    CONF_EXTERNAL_HOST,
    CONF_NOTIFY_TARGET,
    CONF_TRAKT_ID,
    CONF_TRAKT_SECRET,
    CONF_HIDE_SD,
    CONF_KODI_ENTITY,
    CONF_LUNA_TOKEN,
    CONF_LUNA_URL,
    CONF_MAX_BITRATE,
    CONF_PREF_LANG,
    CONF_PREF_SURROUND,
    CONF_SORT,
    CONF_STREAMUJ_PASS,
    CONF_STREAMUJ_USER,
    CONF_WS_PASS,
    CONF_HS_ENABLED,
    CONF_SUB_WARN_DAYS,
    CONF_WS_USER,
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_LUNA_URL,
    DEFAULT_SORT,
    DOMAIN,
    LANGS,
    SORT_ORDERS,
)

ACCOUNT_KEYS = [CONF_WS_USER, CONF_WS_PASS, CONF_STREAMUJ_USER, CONF_STREAMUJ_PASS,
                CONF_LUNA_URL, CONF_LUNA_TOKEN, CONF_SYNC_KEY]

ACCOUNTS = {
    vol.Optional(CONF_WS_USER, default=""): str,
    vol.Optional(CONF_WS_PASS, default=""): str,
    vol.Optional(CONF_STREAMUJ_USER, default=""): str,
    vol.Optional(CONF_STREAMUJ_PASS, default=""): str,
    vol.Optional(CONF_LUNA_URL, default=DEFAULT_LUNA_URL): str,
    vol.Optional(CONF_LUNA_TOKEN, default=""): str,
}


def preferences_schema(data: dict) -> vol.Schema:
    """Předvolby přehrávání — stejné jako v Kodi doplňku."""
    return vol.Schema({
        vol.Optional(CONF_KODI_ENTITY, default=data.get(CONF_KODI_ENTITY, "")):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="media_player")),
        vol.Optional(CONF_PREF_LANG, default=data.get(CONF_PREF_LANG, "CZ")):
            selector.SelectSelector(selector.SelectSelectorConfig(options=[l or "—" for l in LANGS])),
        vol.Optional(CONF_PREF_SURROUND, default=data.get(CONF_PREF_SURROUND, False)): bool,
        vol.Optional(CONF_HIDE_SD, default=data.get(CONF_HIDE_SD, False)): bool,
        vol.Optional(CONF_MAX_BITRATE, default=data.get(CONF_MAX_BITRATE, 0)):
            vol.All(vol.Coerce(float), vol.Range(min=0, max=2000)),
        vol.Optional(CONF_SORT, default=data.get(CONF_SORT, DEFAULT_SORT)):
            selector.SelectSelector(selector.SelectSelectorConfig(options=SORT_ORDERS)),
        vol.Optional(CONF_DOWNLOAD_DIR, default=data.get(CONF_DOWNLOAD_DIR, DEFAULT_DOWNLOAD_DIR)): str,
        vol.Optional(CONF_EXTERNAL_HOST, default=data.get(CONF_EXTERNAL_HOST, "")): str,
        vol.Optional(CONF_NOTIFY_TARGET, default=data.get(CONF_NOTIFY_TARGET, "")): str,
        vol.Optional(CONF_TRAKT_ID, default=data.get(CONF_TRAKT_ID, "")): str,
        vol.Optional(CONF_TRAKT_SECRET, default=data.get(CONF_TRAKT_SECRET, "")): str,
        # Torrenty jako poslední možnost: hledá Prowlarr, stahuje qBittorrent.
        # Prázdná adresa nebo klíč = torrenty se v detailu titulu vůbec neobjeví.
        vol.Optional(CONF_PROWLARR_URL, default=data.get(CONF_PROWLARR_URL, DEFAULT_PROWLARR_URL)): str,
        vol.Optional(CONF_PROWLARR_KEY, default=data.get(CONF_PROWLARR_KEY, "")): str,
        vol.Optional(CONF_QBIT_URL, default=data.get(CONF_QBIT_URL, DEFAULT_QBIT_URL)): str,
        vol.Optional(CONF_QBIT_USER, default=data.get(CONF_QBIT_USER, "")): str,
        vol.Optional(CONF_QBIT_PASS, default=data.get(CONF_QBIT_PASS, "")): str,
        # HellSpy je veřejný, účet nepotřebuje — proto jen přepínač mezi předvolbami
        vol.Optional(CONF_HS_ENABLED, default=data.get(CONF_HS_ENABLED, False)): bool,
        # 0 = upozornění na konec předplatného WebShare vypnuté
        vol.Optional(CONF_SUB_WARN_DAYS, default=data.get(CONF_SUB_WARN_DAYS, 5)):
            vol.All(vol.Coerce(int), vol.Range(min=0, max=14)),
        vol.Optional(CONF_STATS_ENABLED, default=data.get(CONF_STATS_ENABLED, True)): bool,
    })


class NokturnoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Jediná instance — účty v prvním kroku, předvolby ve druhém."""

    VERSION = 1

    def __init__(self):
        self._data = {}

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            self._data = dict(user_input)
            return await self.async_step_preferences()
        return self.async_show_form(step_id="user", data_schema=vol.Schema(ACCOUNTS))

    async def async_step_preferences(self, user_input=None):
        if user_input is not None:
            if user_input.get(CONF_PREF_LANG) == "—":
                user_input[CONF_PREF_LANG] = ""
            # klíč pro synchronizaci Kodi doplňků — vzniká jednou, uživatel si ho opíše do Kodi
            self._data.setdefault(CONF_SYNC_KEY, secrets.token_hex(6))
            return self.async_create_entry(title="Nokturno", data=self._data, options=user_input)
        return self.async_show_form(step_id="preferences", data_schema=preferences_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return NokturnoOptionsFlow()


class NokturnoOptionsFlow(OptionsFlow):
    """Změna účtů i předvoleb po instalaci (účty patří do `data`, zbytek do `options`)."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            if user_input.get(CONF_PREF_LANG) == "—":
                user_input[CONF_PREF_LANG] = ""
            accounts = {key: user_input.pop(key) for key in ACCOUNT_KEYS if key in user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data={**self.config_entry.data, **accounts}
            )
            return self.async_create_entry(title="", data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema({
            vol.Optional(key, default=current.get(key, DEFAULT_LUNA_URL if key == CONF_LUNA_URL else "")): str
            for key in ACCOUNT_KEYS
        }).extend(preferences_schema(current).schema)
        return self.async_show_form(step_id="init", data_schema=schema)
