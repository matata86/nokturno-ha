"""Nastavení integrace — účty zdrojů a předvolby přehrávání."""

from __future__ import annotations

import secrets

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .engine import STORAGE_OPTIONS
from .const import (
    CONF_CZ_ENABLED,
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
    CONF_ST_EMAIL,
    CONF_ST_PASS,
    CONF_FS_USER,
    CONF_FS_PASS,
    CONF_STREAMUJ_USER,
    CONF_TMDB_KEY,
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

# vlastní úložiště (WebDAV), až tři — adresa, jméno, heslo, název; klíče drží jádro
STORAGE_KEYS = [key for slot in STORAGE_OPTIONS for key in slot]
# účty a klíče patří do `entry.data`, ne do options — od 2026-09-14 i Trakt, Prowlarr a qBittorrent
ACCOUNT_KEYS = [CONF_WS_USER, CONF_WS_PASS, CONF_STREAMUJ_USER, CONF_STREAMUJ_PASS, CONF_ST_EMAIL, CONF_ST_PASS,
                CONF_FS_USER, CONF_FS_PASS, CONF_LUNA_URL, CONF_LUNA_TOKEN, CONF_SYNC_KEY, CONF_TMDB_KEY,
                CONF_TRAKT_ID, CONF_TRAKT_SECRET, CONF_PROWLARR_URL, CONF_PROWLARR_KEY,
                CONF_QBIT_URL, CONF_QBIT_USER, CONF_QBIT_PASS, *STORAGE_KEYS]
# ve formuláři skrytě — každé otevření Nastavení dřív ukázalo všech dvanáct hesel čitelně
SECRET_KEYS = frozenset({CONF_WS_PASS, CONF_STREAMUJ_PASS, CONF_ST_PASS, CONF_FS_PASS, CONF_LUNA_TOKEN, CONF_TMDB_KEY, CONF_SYNC_KEY,
                         CONF_TRAKT_SECRET, CONF_PROWLARR_KEY, CONF_QBIT_PASS,
                         *(key for slot in STORAGE_OPTIONS for key in slot if key.endswith("_password"))})
ACCOUNT_DEFAULTS = {CONF_LUNA_URL: DEFAULT_LUNA_URL, CONF_PROWLARR_URL: DEFAULT_PROWLARR_URL,
                    CONF_QBIT_URL: DEFAULT_QBIT_URL}


def _heslo():
    return selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


def accounts_schema(current: dict) -> dict:
    """Pole účtů pro oba formuláře — hesla a klíče jako skryté vstupy."""
    return {
        vol.Optional(key, default=current.get(key, ACCOUNT_DEFAULTS.get(key, ""))): _heslo() if key in SECRET_KEYS else str
        for key in ACCOUNT_KEYS
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
        # Trakt, Prowlarr a qBittorrent jsou účty → ACCOUNT_KEYS (entry.data), ne tady
        # HellSpy je veřejný, účet nepotřebuje — proto jen přepínač mezi předvolbami
        vol.Optional(CONF_HS_ENABLED, default=data.get(CONF_HS_ENABLED, True)): bool,
        # CZtor účet do formuláře nepatří — zařízení se spáruje PINem v dalším kroku (`CztorPairing`)
        vol.Optional(CONF_CZ_ENABLED, default=data.get(CONF_CZ_ENABLED, False)): bool,
        # 0 = upozornění na konec předplatného WebShare vypnuté
        vol.Optional(CONF_SUB_WARN_DAYS, default=data.get(CONF_SUB_WARN_DAYS, 5)):
            vol.All(vol.Coerce(int), vol.Range(min=0, max=14)),
        vol.Optional(CONF_STATS_ENABLED, default=data.get(CONF_STATS_ENABLED, True)): bool,
    })


class CztorPairing:
    """Krok „CZtor": PIN z webu cztor.com/activate. Heslo účtu integrace nikdy nevidí,
    tokeny si drží úložiště jádra v `.storage/nokturno` (tam je čte i `Engine`).

    Zapnutý přepínač bez spárování otevře tenhle krok; formulář se uloží až po
    spárování, nebo když uživatel CZtor v kroku vypne."""

    _cz_pending: dict | None = None
    _cz_pin: dict | None = None

    def _cztor(self):
        from .lib.cztor_api import CztorApi
        from .lib.store import Store
        return CztorApi(Store(self.hass.config.path(f".storage/{DOMAIN}")), device_name="Nokturno (Home Assistant)")

    async def _cztor_needs_pairing(self, user_input) -> bool:
        if not user_input.get(CONF_CZ_ENABLED):
            return False
        api = await self.hass.async_add_executor_job(self._cztor)
        return not await self.hass.async_add_executor_job(api.paired)

    async def async_step_cztor(self, user_input=None):
        from .lib.cztor_api import CztorError
        api = await self.hass.async_add_executor_job(self._cztor)
        errors = {}
        if user_input is not None:
            if not user_input.get("pair", True):
                self._cz_pending[CONF_CZ_ENABLED] = False
                return await self._cztor_finish()
            try:
                if self._cz_pin and await self.hass.async_add_executor_job(api.poll_pin, self._cz_pin["poll_token"]):
                    return await self._cztor_finish()
                errors["base"] = "cz_pending"
            except CztorError:
                self._cz_pin = None
                errors["base"] = "cz_failed"
        if not self._cz_pin:
            try:
                self._cz_pin = await self.hass.async_add_executor_job(api.start_pin)
            except CztorError:
                errors["base"] = "cz_network"
                self._cz_pin = {"pin": "—", "url": "https://cztor.com/activate", "poll_token": ""}
        schema = vol.Schema({vol.Optional("pair", default=True): bool})
        return self.async_show_form(step_id="cztor", data_schema=schema, errors=errors,
                                    description_placeholders={"url": self._cz_pin["url"], "pin": self._cz_pin["pin"]})


class NokturnoConfigFlow(CztorPairing, ConfigFlow, domain=DOMAIN):
    """Jediná instance — jeden formulář se vším, stejný jako pozdější Nastavení
    integrace (`NokturnoOptionsFlow`), ať se uživatel při přidávání nemusí
    proklikávat víc kroků a hned vidí, co všechno jde (i nepovinně) nastavit."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            if user_input.get(CONF_PREF_LANG) == "—":
                user_input[CONF_PREF_LANG] = ""
            accounts = {key: user_input.pop(key) for key in ACCOUNT_KEYS if key in user_input}
            # klíč pro synchronizaci s Kodi doplňkem — vzniká jednou, uživatel si ho opíše do Kodi
            if not accounts.get(CONF_SYNC_KEY):
                accounts[CONF_SYNC_KEY] = secrets.token_hex(16)
            self._cz_pending, self._cz_accounts = user_input, accounts
            if await self._cztor_needs_pairing(user_input):
                return await self.async_step_cztor()
            return await self._cztor_finish()
        # sync_key ukázat rovnou vyplněný — ať ho jde zkopírovat do Kodi hned napoprvé,
        # ne až po dodatečném otevření Nastavení integrace. 128 bitů: klíč chrání
        # neautentizované endpointy /sync a /files (dřív 48 bitů).
        schema = vol.Schema(accounts_schema({CONF_SYNC_KEY: secrets.token_hex(16)})).extend(preferences_schema({}).schema)
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_reauth(self, entry_data):
        """WebShare odmítl přihlášení — HA ukáže „vyžaduje opravu" a tenhle krok."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            from .lib.webshare_api import WebshareApi, WebshareApiError, WebshareError
            api = WebshareApi(user_input[CONF_WS_USER], user_input[CONF_WS_PASS])
            try:
                await self.hass.async_add_executor_job(api.login)
            except WebshareApiError:
                errors["base"] = "ws_auth"
            except WebshareError:
                errors["base"] = "ws_network"
            if not errors:
                return self.async_update_reload_and_abort(entry, data={**entry.data, **user_input})
        schema = vol.Schema({
            vol.Required(CONF_WS_USER, default=entry.data.get(CONF_WS_USER, "")): str,
            vol.Required(CONF_WS_PASS): _heslo(),
        })
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)

    async def _cztor_finish(self):
        return self.async_create_entry(title="Nokturno", data=self._cz_accounts, options=self._cz_pending)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return NokturnoOptionsFlow()


class NokturnoOptionsFlow(CztorPairing, OptionsFlow):
    """Změna účtů i předvoleb po instalaci (účty patří do `data`, zbytek do `options`)."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            if user_input.get(CONF_PREF_LANG) == "—":
                user_input[CONF_PREF_LANG] = ""
            accounts = {key: user_input.pop(key) for key in ACCOUNT_KEYS if key in user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data={**self.config_entry.data, **accounts}
            )
            self._cz_pending = user_input
            if await self._cztor_needs_pairing(user_input):
                return await self.async_step_cztor()
            return await self._cztor_finish()
        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(accounts_schema(current)).extend(preferences_schema(current).schema)
        return self.async_show_form(step_id="init", data_schema=schema)

    async def _cztor_finish(self):
        return self.async_create_entry(title="", data=self._cz_pending)
