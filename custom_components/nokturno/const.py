"""Konstanty integrace Nokturno."""

DOMAIN = "nokturno"

CONF_LUNA_URL = "luna_url"
CONF_LUNA_TOKEN = "luna_token"
CONF_WS_USER = "ws_username"
CONF_WS_PASS = "ws_password"
CONF_STREAMUJ_USER = "streamuj_username"
CONF_STREAMUJ_PASS = "streamuj_password"

CONF_KODI_ENTITY = "kodi_entity"
CONF_PREF_LANG = "pref_lang"
CONF_PREF_SURROUND = "pref_surround"
CONF_HIDE_SD = "hide_sd"
CONF_MAX_SIZE_GB = "max_size_gb"
CONF_SORT = "sort_streams"
CONF_DOWNLOAD_DIR = "download_dir"
CONF_EXTERNAL_HOST = "external_host"
CONF_NOTIFY_TARGET = "notify_target"

DEFAULT_LUNA_URL = "http://192.168.1.10:7126"
DEFAULT_DOWNLOAD_DIR = "/media/nokturno"
DEFAULT_SORT = "quality"

SORT_ORDERS = ["source", "quality", "size_desc", "size_asc"]
LANGS = ["", "CZ", "SK", "EN"]

# Kodi doplněk, přes který se přehrává (evidence zhlédnuto/rozkoukáno zůstane v Kodi)
KODI_PLUGIN = "plugin://plugin.video.nokturno/"

SERVICE_SEARCH = "search"
SERVICE_STREAMS = "streams"
SERVICE_EPISODES = "episodes"
SERVICE_PLAY = "play"
SERVICE_RESOLVE = "resolve"
SERVICE_DOWNLOAD = "download"
SERVICE_SEND_LINK = "send_link"
SERVICE_CANCEL_DOWNLOAD = "cancel_download"
SERVICE_DELETE_FILE = "delete_file"
SERVICE_CONTINUE = "continue_watching"
SERVICE_WATCH = "watch_series"
SERVICE_CHECK_SERIES = "check_series"
SERVICE_CLEAR_HISTORY = "clear_history"

SIGNAL_DOWNLOADS = f"{DOMAIN}_downloads_updated"
SIGNAL_WATCHLIST = f"{DOMAIN}_watchlist_updated"
EVENT_DOWNLOAD_DONE = f"{DOMAIN}_download_done"
EVENT_NEW_EPISODE = f"{DOMAIN}_new_episode"
WATCH_INTERVAL_HOURS = 6
