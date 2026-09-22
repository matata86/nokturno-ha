"""Konstanty integrace Nokturno.

Klíče nastavení, které čte jádro (účty zdrojů, torrenty, předvolby streamů),
jsou ve sdíleném `lib/const.py` a vtahují se sem hvězdičkou — **needituj je
tady**, mění se v repu `nokturno-core` a rozesílá skriptem `tools/sync_core.py`.
Zdejší zůstávají jen ty, které jsou vlastní Home Assistantu.
"""
from .lib.const import *  # noqa: F401,F403

DOMAIN = "nokturno"

# --- vlastní Home Assistantu ---------------------------------------------
CONF_KODI_ENTITY = "kodi_entity"
CONF_NOTIFY_TARGET = "notify_target"
CONF_TRAKT_ID = "trakt_client_id"
CONF_TRAKT_SECRET = "trakt_client_secret"
CONF_SUB_WARN_DAYS = "sub_warn_days"   # kolik dní předem upozornit na konec předplatného WebShare
CONF_STATS_ENABLED = "stats_enabled"
CONF_SYNC_KEY = "sync_key"   # klíč, kterým se Kodi doplňky hlásí na /api/nokturno/sync
# Kód skupiny na slepém relayi dashboardu (`lib/syncbox.py`). Vyplněný znamená, že
# do skupiny chodí i samo HA — Kodi mimo domácí síť (mobil) na `/api/nokturno/sync`
# nedosáhne, ale na dashboard ano, a HA jejich změny přebere a rozešle dál.
CONF_SYNC_CODE = "sync_code"
SYNC_RELAY_INTERVAL_MINUTES = 5

# Právní upozornění — první krok config flow, bez potvrzení se instalace nedokončí.
CONF_TERMS_ACCEPTED = "terms_accepted"
CONF_TERMS_VERSION = "terms_version"
TERMS_VERSION = 1

# Co se synchronizuje. Stejné tři okruhy jako v doplňku pro Kodi (`lib/sync.py`),
# a platí pro obě cesty naráz: pro Kodi v místní síti (`/api/nokturno/sync`)
# i pro skupinu na relayi. Vypnutý okruh se nepošle ani nepřijme — kdyby se jen
# neposílal, dorazil by zpátky od protějšku a zapsal by se.
CONF_SYNC_WATCHED = "sync_watched"
CONF_SYNC_FAVOURITES = "sync_favourites"
CONF_SYNC_HISTORY = "sync_history"
SYNC_CIRCLE_OPTIONS = (
    ("watched", CONF_SYNC_WATCHED),
    ("favourites", CONF_SYNC_FAVOURITES),
    ("history", CONF_SYNC_HISTORY),
)

SUB_CHECK_INTERVAL_HOURS = 12
STATS_INTERVAL_HOURS = 6

# Kodi doplněk, přes který se přehrává (evidence zhlédnuto/rozkoukáno zůstane v Kodi)
KODI_PLUGIN = "plugin://plugin.video.nokturno/"

SERVICE_SEARCH = "search"
SERVICE_STREAMS = "streams"
SERVICE_EPISODES = "episodes"
SERVICE_DETAIL = "detail"
SERVICE_PLAY = "play"
SERVICE_RESOLVE = "resolve"
SERVICE_DOWNLOAD = "download"
SERVICE_SEND_LINK = "send_link"
SERVICE_CANCEL_DOWNLOAD = "cancel_download"
SERVICE_START_DOWNLOAD = "start_download"
SERVICE_DELETE_FILE = "delete_file"
SERVICE_SHARE_FILE = "share_file"
SERVICE_CONTINUE = "continue_watching"
SERVICE_REMOVE_PROGRESS = "remove_progress"
SERVICE_WATCH = "watch_series"
SERVICE_CHECK_SERIES = "check_series"
SERVICE_CLEAR_HISTORY = "clear_history"
SERVICE_CLEAR_CACHE = "clear_cache"
SERVICE_SEEN = "mark_seen"
SERVICE_TRAKT_AUTH = "trakt_auth"
SERVICE_TRAKT_WATCHED = "trakt_watched"
SERVICE_TRAKT_LIST = "trakt_watchlist"
SERVICE_TRAKT_FLAG = "trakt_flag"
SERVICE_WANT = "want_to_watch"
SERVICE_FAVOURITE_ADD = "favourite_add"
SERVICE_FAVOURITE_TOGGLE = "favourite_toggle"
SERVICE_TORRENTS = "torrents"
SERVICE_TORRENT = "download_torrent"
SERVICE_FULLTEXT = "fulltext_search"

# poslední živý stav „Pokračovat ve sledování" — karta ho ukáže hned po načtení,
# než dorazí čerstvá odpověď z živého dotazu na Kodi (viz kodi_continue v __init__.py)
CONTINUE_CACHE_KEY = "continue_cache"

SIGNAL_DOWNLOADS = f"{DOMAIN}_downloads_updated"
SIGNAL_WATCHLIST = f"{DOMAIN}_watchlist_updated"
SIGNAL_TRAKT = f"{DOMAIN}_trakt_updated"
SIGNAL_ACCOUNTS = f"{DOMAIN}_accounts_updated"
EVENT_DOWNLOAD_DONE = f"{DOMAIN}_download_done"
EVENT_NEW_EPISODE = f"{DOMAIN}_new_episode"
EVENT_TRAKT_AVAILABLE = f"{DOMAIN}_trakt_available"
WATCH_INTERVAL_HOURS = 6
# pod `accounts.TTL` (12 h), ať v senzoru nestojí stav označený jako zastaralý
ACCOUNTS_INTERVAL_HOURS = 6
TRAKT_INTERVAL_HOURS = 24
