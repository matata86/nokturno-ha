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
SERVICE_WATCH = "watch_series"
SERVICE_CHECK_SERIES = "check_series"
SERVICE_CLEAR_HISTORY = "clear_history"
SERVICE_CLEAR_CACHE = "clear_cache"
SERVICE_SEEN = "mark_seen"
SERVICE_TRAKT_AUTH = "trakt_auth"
SERVICE_TRAKT_WATCHED = "trakt_watched"
SERVICE_TRAKT_LIST = "trakt_watchlist"
SERVICE_WANT = "want_to_watch"
SERVICE_TORRENTS = "torrents"
SERVICE_TORRENT = "download_torrent"
SERVICE_FULLTEXT = "fulltext_search"

SIGNAL_DOWNLOADS = f"{DOMAIN}_downloads_updated"
SIGNAL_WATCHLIST = f"{DOMAIN}_watchlist_updated"
SIGNAL_TRAKT = f"{DOMAIN}_trakt_updated"
EVENT_DOWNLOAD_DONE = f"{DOMAIN}_download_done"
EVENT_NEW_EPISODE = f"{DOMAIN}_new_episode"
EVENT_TRAKT_AVAILABLE = f"{DOMAIN}_trakt_available"
WATCH_INTERVAL_HOURS = 6
TRAKT_INTERVAL_HOURS = 24
