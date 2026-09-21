"""Nastavení integrace — účty zdrojů a předvolby přehrávání."""

from __future__ import annotations

import secrets

import voluptuous as vol
from homeassistant.data_entry_flow import section

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
    CONF_SYNC_CODE,
    CONF_SYNC_FAVOURITES,
    CONF_SYNC_HISTORY,
    CONF_SYNC_KEY,
    CONF_SYNC_WATCHED,
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
                CONF_FS_USER, CONF_FS_PASS, CONF_LUNA_URL, CONF_LUNA_TOKEN, CONF_SYNC_KEY, CONF_SYNC_CODE, CONF_TMDB_KEY,
                CONF_TRAKT_ID, CONF_TRAKT_SECRET, CONF_PROWLARR_URL, CONF_PROWLARR_KEY,
                CONF_QBIT_URL, CONF_QBIT_USER, CONF_QBIT_PASS, *STORAGE_KEYS]
# ve formuláři skrytě — každé otevření Nastavení dřív ukázalo všech dvanáct hesel čitelně
SECRET_KEYS = frozenset({CONF_WS_PASS, CONF_STREAMUJ_PASS, CONF_ST_PASS, CONF_FS_PASS, CONF_LUNA_TOKEN, CONF_TMDB_KEY, CONF_SYNC_KEY,
                         CONF_TRAKT_SECRET, CONF_PROWLARR_KEY, CONF_QBIT_PASS,
                         *(key for slot in STORAGE_OPTIONS for key in slot if key.endswith("_password"))})
ACCOUNT_DEFAULTS = {CONF_LUNA_URL: DEFAULT_LUNA_URL, CONF_PROWLARR_URL: DEFAULT_PROWLARR_URL,
                    CONF_QBIT_URL: DEFAULT_QBIT_URL}


def _kod_skupiny(accounts: dict) -> str | None:
    """Srovná kód skupiny do tvaru `NKT-…` a vrátí chybu pro formulář, když nesedí.

    Prázdné pole znamená „HA do skupiny na dashboardu nechodí" — to je výchozí stav
    a žádná chyba. Kód se opisuje z obrazovky televize, takže se nehlídá jen tvar,
    ale rovnou se i normalizuje (malá písmena, chybějící pomlčky).
    """
    from .lib.syncbox import normalize_code, valid_code

    raw = (accounts.get(CONF_SYNC_CODE) or "").strip()
    if not raw:
        accounts[CONF_SYNC_CODE] = ""
        return None
    if not valid_code(raw):
        return "sync_code"
    accounts[CONF_SYNC_CODE] = normalize_code(raw)
    return None


# Formulář má přes čtyřicet polí. Naráz pod sebou to byl nepřehledný sloupec, ve
# kterém se hledalo očima, proto je rozdělený do sbalitelných sekcí
# (`data_entry_flow.section`, HA 2024.6+). Pořadí je podle toho, jak často se do
# nich sahá: přehrávání je otevřené, zbytek sbalený.
#
# Sekce mění tvar dat — uživatelův vstup přijde jako {"sekce": {"klíč": …}}, takže
# se před uložením zase zploští (`_zploskuj`). Uloženo zůstává naplocho, jak to
# bylo: `entry.data` i `entry.options` si nesmí kvůli vzhledu formuláře měnit tvar.
SEKCE = [
    ("prehravani", [CONF_KODI_ENTITY, CONF_PREF_LANG, CONF_PREF_SURROUND, CONF_HIDE_SD,
                    CONF_MAX_BITRATE, CONF_SORT], False),
    ("zdroje", [CONF_WS_USER, CONF_WS_PASS, CONF_STREAMUJ_USER, CONF_STREAMUJ_PASS,
                CONF_ST_EMAIL, CONF_ST_PASS, CONF_FS_USER, CONF_FS_PASS,
                CONF_HS_ENABLED, CONF_CZ_ENABLED, CONF_LUNA_URL, CONF_LUNA_TOKEN,
                CONF_SUB_WARN_DAYS], True),
    ("uloziste", STORAGE_KEYS, True),
    ("torrenty", [CONF_PROWLARR_URL, CONF_PROWLARR_KEY, CONF_QBIT_URL,
                  CONF_QBIT_USER, CONF_QBIT_PASS], True),
    ("stahovani", [CONF_DOWNLOAD_DIR, CONF_EXTERNAL_HOST, CONF_NOTIFY_TARGET], True),
    ("synchronizace", [CONF_SYNC_KEY, CONF_SYNC_CODE, CONF_SYNC_WATCHED,
                       CONF_SYNC_FAVOURITES, CONF_SYNC_HISTORY], True),
    ("ostatni", [CONF_TMDB_KEY, CONF_TRAKT_ID, CONF_TRAKT_SECRET, CONF_STATS_ENABLED], True),
]


def _pole(current: dict) -> dict:
    """Všechna pole obou formulářů jako {klíč: (marker, validátor)} k rozdělení do sekcí."""
    out = dict(accounts_schema(current))
    out.update(preferences_schema(current).schema)
    return {marker.schema: (marker, validator) for marker, validator in out.items()}


def formular(current: dict) -> vol.Schema:
    """Schéma se sbalitelnými sekcemi. Pole, které by v žádné nebylo, spadne do „ostatní“ —
    ať nový klíč nezmizí z formuláře jen proto, že se zapomnělo doplnit sem."""
    pole = _pole(current)
    rozdelene, schema = set(), {}
    for jmeno, klice, sbalena in SEKCE:
        vybrane = {pole[k][0]: pole[k][1] for k in klice if k in pole}
        rozdelene.update(k for k in klice if k in pole)
        if jmeno == "ostatni":
            zbytek = [k for k in pole if k not in rozdelene]
            vybrane.update({pole[k][0]: pole[k][1] for k in zbytek})
        if vybrane:
            schema[vol.Required(jmeno)] = section(vol.Schema(vybrane), {"collapsed": sbalena})
    return vol.Schema(schema)


def _zploskuj(user_input: dict) -> dict:
    """Ze sekcí zase plochý dict — tak se to ukládá i čte po zbytek integrace."""
    plocho = {}
    for klic, hodnota in (user_input or {}).items():
        if isinstance(hodnota, dict) and any(j == klic for j, _, _ in SEKCE):
            plocho.update(hodnota)
        else:
            plocho[klic] = hodnota
    return plocho


def _seznam(hodnota) -> list[str]:
    """Entity přehrávače vždy jako seznam. Do 6.6.0 se ukládal jeden řetězec a
    `EntitySelector(multiple=True)` by na něm spadl."""
    if not hodnota:
        return []
    return list(hodnota) if isinstance(hodnota, (list, tuple)) else [hodnota]


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
        # Víc přehrávačů naráz: služba `play` bez `entity_id` pustí titul na všech
        # vybraných. Uložená hodnota z dřívějška je jeden řetězec, proto `_seznam`.
        vol.Optional(CONF_KODI_ENTITY, default=_seznam(data.get(CONF_KODI_ENTITY))):
            selector.EntitySelector(
                selector.EntitySelectorConfig(domain="media_player", multiple=True)),
        # `translation_key` je jediná cesta, jak se u hodnot selectu dostat k překladu —
        # bez něj HA vypíše holou uloženou hodnotu („quality", „size_desc").
        vol.Optional(CONF_PREF_LANG, default=data.get(CONF_PREF_LANG, "CZ")):
            selector.SelectSelector(selector.SelectSelectorConfig(
                options=[l or "—" for l in LANGS], translation_key="pref_lang")),
        vol.Optional(CONF_PREF_SURROUND, default=data.get(CONF_PREF_SURROUND, False)): bool,
        vol.Optional(CONF_HIDE_SD, default=data.get(CONF_HIDE_SD, False)): bool,
        vol.Optional(CONF_MAX_BITRATE, default=data.get(CONF_MAX_BITRATE, 0)):
            vol.All(vol.Coerce(float), vol.Range(min=0, max=2000)),
        vol.Optional(CONF_SORT, default=data.get(CONF_SORT, DEFAULT_SORT)):
            selector.SelectSelector(selector.SelectSelectorConfig(
                options=SORT_ORDERS, translation_key="sort_streams")),
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
        # co se synchronizuje — platí pro Kodi v místní síti i pro skupinu na relayi
        vol.Optional(CONF_SYNC_WATCHED, default=data.get(CONF_SYNC_WATCHED, True)): bool,
        vol.Optional(CONF_SYNC_FAVOURITES, default=data.get(CONF_SYNC_FAVOURITES, True)): bool,
        vol.Optional(CONF_SYNC_HISTORY, default=data.get(CONF_SYNC_HISTORY, True)): bool,
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
            user_input = _zploskuj(user_input)
            if user_input.get(CONF_PREF_LANG) == "—":
                user_input[CONF_PREF_LANG] = ""
            accounts = {key: user_input.pop(key) for key in ACCOUNT_KEYS if key in user_input}
            # klíč pro synchronizaci s Kodi doplňkem — vzniká jednou, uživatel si ho opíše do Kodi
            if not accounts.get(CONF_SYNC_KEY):
                accounts[CONF_SYNC_KEY] = secrets.token_hex(16)
            chyba = _kod_skupiny(accounts)
            if chyba:
                return self.async_show_form(step_id="user", errors={CONF_SYNC_CODE: chyba},
                                            data_schema=formular({**accounts, **user_input}))
            self._cz_pending, self._cz_accounts = user_input, accounts
            if await self._cztor_needs_pairing(user_input):
                return await self.async_step_cztor()
            return await self._cztor_finish()
        # sync_key ukázat rovnou vyplněný — ať ho jde zkopírovat do Kodi hned napoprvé,
        # ne až po dodatečném otevření Nastavení integrace. 128 bitů: klíč chrání
        # neautentizované endpointy /sync a /files (dřív 48 bitů).
        return self.async_show_form(step_id="user",
                                    data_schema=formular({CONF_SYNC_KEY: secrets.token_hex(16)}))

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
            user_input = _zploskuj(user_input)
            if user_input.get(CONF_PREF_LANG) == "—":
                user_input[CONF_PREF_LANG] = ""
            accounts = {key: user_input.pop(key) for key in ACCOUNT_KEYS if key in user_input}
            chyba = _kod_skupiny(accounts)
            if chyba:
                return self.async_show_form(step_id="init", errors={CONF_SYNC_CODE: chyba},
                                            data_schema=formular({**accounts, **user_input}))
            self.hass.config_entries.async_update_entry(
                self.config_entry, data={**self.config_entry.data, **accounts}
            )
            self._cz_pending = user_input
            if await self._cztor_needs_pairing(user_input):
                return await self.async_step_cztor()
            return await self._cztor_finish()
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=formular(current))

    async def _cztor_finish(self):
        return self.async_create_entry(title="", data=self._cz_pending)
