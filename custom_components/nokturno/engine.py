"""Jádro integrace — hledání a streamy ve stejných zdrojích jako Kodi doplněk.

Logika odpovídá `default.py` doplňku (sloučení Luna ↔ Sosáč, cross-search, řazení),
ale bez Kodi: volání jsou synchronní a HA je pouští v executoru.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime

from .const import CONF_HS_ENABLED, LANGS, SORT_ORDERS
from .lib.enrich import DEAD_IMAGES, _cinemeta, _fetch, _fetch_title, enrich, enrich_one
from .lib.luna_api import LunaApi, LunaError, clean_label, parse_base_url, parse_token
from .lib.prowlarr import ProwlarrApi, ProwlarrError
from .lib.qbittorrent import QbitApi, QbitError
from .lib.sosac_api import SosacError, names_match
from .lib.sosac_api import is_sosac_id as _is_legacy_sosac_id
from .lib.sosac_direct import SosacDirect, is_direct_id
from .lib.store import Store
from .lib.streams import arrange, estimate_rank, langs_from_name, parse_stream
from .lib.hellspy_api import HellspyApi, HellspyError
from .lib.webshare_api import WebshareApi, WebshareError, human_size

WS_LIMIT = 25    # kolik souborů brát z fulltextu WebShare
HS_LIMIT = 25    # totéž pro HellSpy
SOLO_LIMIT = 8   # kolik z nich nechat v seznamu, když k nim Luna nemá protějšek
SIZE_TOLERANCE = 0.25  # GB – Luna a WebShare zaokrouhlují velikost jinak
HISTORY_MAX = 12
SUBS_MAX = 3
SEARCH_CACHE_TTL = 43200      # 12 h – seznam nalezených titulů podle dotazu (Luna, WebShare fulltext)
STREAMS_CACHE_TTL = 259200    # 72 h – seznam streamů k titulu, ale JEN když nějaké našel (viz `cached_if`)

_LOGGER = logging.getLogger(__name__)

SOURCE_NAMES = {"main": "Luna", "search": "WebShare", "ws": "WebShare", "sosac": "Sosáč",
                "hs": "HellSpy", "torrent": "Torrent"}

QUALITY_NAMES = {4: "4K", 3: "Full HD", 2: "HD", 1: "SD", 0: ""}


def _fold(text):
    """Bez diakritiky, malá písmena — pro porovnávání názvů souborů."""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

# databáze filmů vrací žánry a země anglicky — do shrnutí patří česky
GENRES_CS = {
    "Action": "Akční", "Adventure": "Dobrodružný", "Animation": "Animovaný", "Biography": "Životopisný",
    "Comedy": "Komedie", "Crime": "Krimi", "Documentary": "Dokument", "Drama": "Drama", "Family": "Rodinný",
    "Fantasy": "Fantasy", "History": "Historický", "Horror": "Horor", "Music": "Hudební", "Musical": "Muzikál",
    "Mystery": "Mysteriózní", "Romance": "Romantický", "Sci-Fi": "Sci-fi", "Short": "Krátkometrážní",
    "Sport": "Sportovní", "Thriller": "Thriller", "War": "Válečný", "Western": "Western",
}
COUNTRIES_CS = {
    "Czech Republic": "Česko", "Czechia": "Česko", "Czechoslovakia": "Československo", "Slovakia": "Slovensko",
    "United States": "USA", "United States of America": "USA", "United Kingdom": "Velká Británie",
    "Germany": "Německo", "France": "Francie", "Italy": "Itálie", "Spain": "Španělsko", "Poland": "Polsko",
    "Austria": "Rakousko", "Hungary": "Maďarsko", "Canada": "Kanada", "Japan": "Japonsko", "Denmark": "Dánsko",
    "Sweden": "Švédsko", "Norway": "Norsko", "Netherlands": "Nizozemsko", "Belgium": "Belgie",
    "Switzerland": "Švýcarsko", "Australia": "Austrálie", "Russia": "Rusko", "Ireland": "Irsko",
}


class NokturnoError(Exception):
    """Chyba, kterou má smysl ukázat uživateli."""


def is_sosac_id(item_id):
    """Sosáč napřímo (`sosacd_`) i starší Stremio režim (`sosac2_`).

    Knihovní `sosac_api.is_sosac_id` zná jen ten starší tvar — tituly ze Sosáče by pak
    šly do Luny (žádné streamy) a nedostaly by poster z TMDB.
    """
    return is_direct_id(item_id) or _is_legacy_sosac_id(item_id)


def split_episode_id(item_id):
    """`id:S:E` → (id seriálu, sezóna, epizoda); u filmu (id, None, None)."""
    parts = str(item_id).split(":")
    if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
        return ":".join(parts[:-2]), int(parts[-2]), int(parts[-1])
    return str(item_id), None, None


class Engine:
    """Přístup ke třem zdrojům obsahu pod jedním rozhraním."""

    def __init__(self, options, storage_dir):
        self.options = dict(options)
        self.store = Store(storage_dir)
        self._luna = None
        self._sosac = None
        self._ws = None
        self._ws_ready = False
        self._hs = None
        self._prowlarr = self._qbit = None

    # --- konfigurace --------------------------------------------------------

    def update_options(self, options):
        self.options = dict(options)
        self._luna = self._sosac = self._ws = None
        self._ws_ready = False
        self._hs = None
        self._prowlarr = self._qbit = None

    def _opt(self, key, default=""):
        value = self.options.get(key, default)
        return value if value is not None else default

    @property
    def luna(self):
        if self._luna is None:
            token = parse_token(self._opt("luna_token"))
            if token:
                base = parse_base_url(self._opt("luna_url"), self._opt("luna_url"))
                self._luna = LunaApi(base, token, cache=self.store)
        return self._luna

    @property
    def sosac(self):
        if self._sosac is None:
            user = self._opt("streamuj_username").strip()
            if user:
                self._sosac = SosacDirect(user, self._opt("streamuj_password"),
                                          cache=self.store, index_store=self.store)
        return self._sosac

    @property
    def ws(self):
        if not self._ws_ready:
            self._ws_ready = True
            user = self._opt("ws_username").strip()
            if user:
                api = WebshareApi(user, self._opt("ws_password"))
                try:
                    api.login()
                    self._ws = api
                except WebshareError as err:
                    _LOGGER.warning("WebShare login selhal: %s", err)
        return self._ws

    @property
    def hs(self):
        """HellSpy nemá účet ani token — stačí přepínač v nastavení."""
        if self._hs is None and self._opt(CONF_HS_ENABLED, False):
            self._hs = HellspyApi(cache=self.store)
        return self._hs

    @property
    def prowlarr(self):
        """Hledání na trackerech. Bez adresy i klíče se torrenty vůbec nenabídnou."""
        if self._prowlarr is None:
            url = self._opt("prowlarr_url").strip()
            key = self._opt("prowlarr_key").strip()
            if url and key:
                self._prowlarr = ProwlarrApi(url, key)
        return self._prowlarr

    @property
    def qbit(self):
        if self._qbit is None:
            url = self._opt("qbit_url").strip()
            if url:
                self._qbit = QbitApi(url, self._opt("qbit_username"), self._opt("qbit_password"))
        return self._qbit

    def sources(self):
        """Které zdroje jsou nastavené — pro diagnostiku a pro kartu.

        WebShare se hlásí podle vyplněných údajů, ne podle `ws`: ta se
        přihlašuje po síti a tohle se čte při počítání atributů senzoru, tedy
        ve smyčce událostí, kam blokující volání nepatří."""
        return {"luna": self.luna is not None, "sosac": self.sosac is not None,
                "webshare": bool(self._opt("ws_username").strip()),
                "torrent": self.prowlarr is not None}

    def api_for(self, item_id):
        api = self.sosac if is_sosac_id(item_id) else self.luna
        if api is None:
            raise NokturnoError("Zdroj tohoto titulu není nastavený (Luna / Sosáč).")
        return api

    # --- hledání ------------------------------------------------------------

    @staticmethod
    def split_year(query):
        """„Pět švestek 2026" → („Pět švestek", 2026). Zdroje hledají jen v názvu, rok
        v dotazu by je zmátl — odřízneme ho a použijeme na filtrování výsledků."""
        query = (query or "").strip()
        match = YEAR_RE.search(query)
        if not match:
            return query, None
        base = (query[: match.start()] + " " + query[match.end():]).strip()
        year = int(match.group(1))
        # „2012" nebo „Blade Runner 2049" — číslo je součást názvu, ne rok vydání
        if not base or year > datetime.now().year + 2:
            return query, None
        return base, year

    def _by_year(self, pairs, year):
        """Rok v dotazu je filtr: projdou jen tituly z toho roku (a ty, kde ho zdroj neuvádí).
        Když nezbude nic, karta nabídne hledání v databázi filmů — je to poctivější
        než ukázat stejnojmenný film o čtyřicet let starší."""
        if not year:
            return pairs
        return [p for p in pairs if self._year(p[0]) in (year, None)]

    @staticmethod
    def _year(meta):
        raw = str(meta.get("year") or meta.get("releaseInfo") or "")[:4]
        return int(raw) if raw.isdigit() else None

    def _same_title(self, luna_meta, sosac_meta):
        name = luna_meta.get("name") or ""
        if not (names_match(name, sosac_meta.get("_title")) or names_match(name, sosac_meta.get("_orig"))):
            return False
        y1, y2 = self._year(luna_meta), self._year(sosac_meta)
        return not (y1 and y2 and abs(y1 - y2) > 1)

    def _merge(self, luna_metas, sosac_metas):
        """[(meta, alt)] — titul z Luny s přibaleným id Sosáče, zbytek Sosáče zvlášť."""
        merged, used = [], set()
        for lm in luna_metas:
            alt = None
            for sm in sosac_metas:
                if sm["id"] not in used and self._same_title(lm, sm):
                    alt = sm["id"]
                    used.add(sm["id"])
                    break
            merged.append((lm, alt))
        for sm in sosac_metas:
            if sm["id"] in used:
                continue
            # Sosáč má některé filmy vloženy víckrát; k Luně se spáruje jen první,
            # ostatní kopie by se ve výsledcích objevily jako druhá dlaždice téhož titulu
            if any(self._same_title(lm, sm) for lm in luna_metas):
                continue
            merged.append((sm, None))
        return merged

    @staticmethod
    def _art(url):
        """Mrtvé náhledy Sosáče neposílat — v kartě je lepší podklad než rozbitý obrázek."""
        return "" if DEAD_IMAGES in (url or "") else (url or "")

    def _item(self, meta, ctype, alt=None):
        return {
            "id": meta.get("id"),
            "type": ctype,
            "title": meta.get("_title") or meta.get("name") or "",
            "original_title": meta.get("_orig") or "",
            "year": self._year(meta),
            "poster": self._art(meta.get("poster")),
            "background": self._art(meta.get("background")),
            "description": (meta.get("description") or "")[:4000],
            "rating": meta.get("imdbRating") or "",
            "source": "sosac" if is_sosac_id(meta.get("id")) else "luna",
            "alt": alt,
        }

    def search(self, ctype="movie", query="", limit=20):
        """Sloučené výsledky z Luny a Sosáče (stejný titul jen jednou).

        Sosáč vrací u položek vždy mrtvý náhled (`movies.sosac.tv`), takže `_needs()`
        v `enrich()` je pro ně TRUE napořád — cachovat jen dílčí Luna/Sosáč volání by
        `enrich()` nechalo běžet (a diskové I/O na jeho vlastní cache × N položek dělat)
        při každém hledání znovu. Cachuje se proto rovnou celý výsledek PO enrichi.

        Dotaz zakončený `*` obejde cache a vynutí čerstvá data (hvězdička se před
        hledáním odřízne) — výsledek se přesto zapíše do cache pro příští normální dotaz.
        """
        query = (query or "").strip()
        force = query.endswith("*")
        if force:
            query = query[:-1].strip()
        query, want_year = self.split_year(query)
        if not query:
            raise NokturnoError("Prázdný dotaz.")

        def _fetch():
            luna_metas, sosac_metas, errors = [], [], []
            if self.luna:
                try:
                    cid = "search.movie" if ctype == "movie" else "search.series"
                    cache_key = f"luna:search:{ctype}:{cid}:{query}"
                    luna_metas = self.store.cached(cache_key, SEARCH_CACHE_TTL,
                                                    lambda: self.luna.catalog(ctype, cid, search=query))
                except LunaError as err:
                    errors.append(f"Luna: {err}")
            if self.sosac:
                try:
                    sosac_metas = self.sosac.search(ctype, query)
                except SosacError as err:
                    errors.append(f"Sosáč: {err}")
            if not luna_metas and not sosac_metas and errors:
                raise NokturnoError("; ".join(errors))
            merged = self._by_year(self._merge(luna_metas, sosac_metas), want_year)[: int(limit or 20)]
            enrich([m for m, _alt in merged if is_sosac_id(m.get("id"))], self.luna, self.store, ctype)
            return [self._item(meta, ctype, alt) for meta, alt in merged]

        cache_key = f"search:{ctype}:{query}:{int(limit or 20)}:{want_year or ''}"
        return self.store.cached_if(cache_key, 0 if force else SEARCH_CACHE_TTL, _fetch)

    # --- historie hledání -----------------------------------------------------

    # historie se sdílí s doplňkem pro Kodi pod typem "any" (hlavní hledání) —
    # zápis vede i deník `histlog`, takže se synchronizuje mezi kartou a všemi Kodi
    def history(self):
        return self.store.history("any")

    def add_history(self, query):
        self.store.add_history("any", query)

    def clear_history(self):
        self.store.clear_history("any")

    def search_catalog(self, ctype="movie", query="", limit=10):
        """Hledání v databázi filmů (Cinemeta = IMDb/TMDB) — najde i tituly, které zatím
        žádný ze zdrojů nemá, třeba chystané filmy. Slouží pro seznam „k zhlédnutí"."""
        query, want_year = self.split_year(query)
        if not query:
            raise NokturnoError("Prázdný dotaz.")
        url = (f"https://v3-cinemeta.strem.io/catalog/{'series' if ctype == 'series' else 'movie'}"
               f"/top/search={urllib.parse.quote(query)}.json")

        def load():
            req = urllib.request.Request(url, headers={"User-Agent": "Home Assistant Nokturno"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))

        try:
            data = self.store.cached(url, 3600, load)
        except Exception as err:  # noqa: BLE001
            raise NokturnoError(f"Databáze filmů neodpověděla: {err}") from err
        metas = data.get("metas") or []
        if want_year:
            metas = [m for m in metas
                     if str(m.get("releaseInfo") or m.get("year") or "")[:4] in (str(want_year), "")]
        out = []
        for meta in metas[: int(limit or 10)]:
            year = str(meta.get("releaseInfo") or meta.get("year") or "")[:4]
            out.append({
                "id": meta.get("id"),
                "type": ctype,
                "title": meta.get("name") or "",
                "year": int(year) if year.isdigit() else None,
                "poster": meta.get("poster") or "",
                "background": meta.get("background") or "",
                "description": (meta.get("description") or "")[:4000],
                "source": "katalog",
                "alt": None,
            })
        return out

    def catalog_detail(self, ctype="movie", item_id=""):
        """Popis, plakát a hodnocení titulu z databáze filmů — katalog Cinemety je nemá."""
        if not item_id:
            raise NokturnoError("Chybí `id`.")
        kind = "series" if ctype == "series" else "movie"
        key = f"cinemeta:{kind}:{item_id}"
        try:
            meta = self.store.cached(key, 86400, lambda: _cinemeta(kind, item_id))
        except Exception as err:  # noqa: BLE001
            raise NokturnoError(f"Databáze filmů neodpověděla: {err}") from err
        # Cinemeta u čerstvých titulů popis nemá — TMDB (přes Lunu) ho většinou zná, a česky
        try:
            meta = {**meta, **{k: v for k, v in _fetch(self.luna, self.store, kind, item_id).items() if v}}
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("detail %s: %s", item_id, err)
        year = str(meta.get("year") or meta.get("releaseInfo") or "")[:4]
        year_num = int(year) if year.isdigit() else None
        if self.luna:  # TMDB podle IMDb id zná český název („Sunday League…“ → „Okresní přebor…“)
            try:
                by_id = self.store.cached(f"lunameta:{kind}:{item_id}", 30 * 86400,
                                          lambda: self.luna.meta(kind, item_id) or {})
                if by_id.get("name"):
                    meta = {**meta, **{k: v for k, v in by_id.items() if v}}
            except Exception as err:  # noqa: BLE001 – Luna nemusí běžet
                _LOGGER.debug("meta z Luny %s: %s", item_id, err)
        if not meta.get("description"):  # čerstvý film — zkusit TMDB ještě podle názvu a roku
            try:
                by_name = _fetch_title(self.luna, self.store, kind, meta.get("name") or "", year_num)
                meta = {**meta, **{k: v for k, v in by_name.items() if v}}
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("detail podle názvu %s: %s", item_id, err)
        return {
            "id": item_id,
            "type": kind,
            "title": self._local_title(kind, meta.get("name") or "", year_num) or meta.get("name") or "",
            "year": year_num,
            "poster": meta.get("poster") or "",
            "background": meta.get("background") or "",
            "description": (meta.get("description") or self._summary(meta))[:4000],
            "rating": meta.get("imdbRating") or "",
            "genres": meta.get("genres") or [],
            "runtime": meta.get("runtime") or "",
            "cast": meta.get("cast") or [],
            "director": meta.get("director") or [],
            "source": "katalog",
        }

    def _local_title(self, kind, name, year):
        """Databáze filmů vede mezinárodní přepis („Pet svestek“) — český název zná TMDB."""
        if not self.luna or not name:
            return ""

        def load():
            cid = "search.movie" if kind == "movie" else "search.series"
            try:
                metas = self.luna.catalog(kind, cid, search=name)
            except Exception:  # noqa: BLE001 – Luna nemusí běžet
                return ""
            for meta in metas[:10]:
                found = meta.get("name") or ""
                if _fold(found) != _fold(name):
                    continue
                my = str(meta.get("year") or meta.get("releaseInfo") or "")[:4]
                if year and my.isdigit() and abs(int(my) - year) > 1:
                    continue
                return found
            return ""

        return self.store.cached(f"lname:{kind}:{_fold(name)}:{year or ''}", 30 * 86400, load)

    @staticmethod
    def _summary(meta):
        """Chystané filmy popis nemají nikde — složíme aspoň větu z toho, co je známo."""
        parts = []
        head = ", ".join(GENRES_CS.get(g, g) for g in (meta.get("genres") or []))
        if meta.get("country"):
            country = ", ".join(COUNTRIES_CS.get(c.strip(), c.strip())
                                for c in str(meta["country"]).split(","))
            head = f"{head} · {country}" if head else country
        if head:
            parts.append(head + ".")
        if meta.get("director"):
            parts.append("Režie " + ", ".join(meta["director"][:3]) + ".")
        if meta.get("cast"):
            parts.append("Hrají " + ", ".join(meta["cast"][:5]) + ".")
        return " ".join(parts)

    def search_webshare(self, query, limit=20):
        """Soubory přímo z WebShare (fulltext), bez metadat titulu.

        Dotaz zakončený `*` obejde cache a vynutí čerstvá data, stejně jako u `search()`.
        """
        if not self.ws:
            raise NokturnoError("WebShare účet není nastavený.")
        query = (query or "").strip()
        force = query.endswith("*")
        if force:
            query = query[:-1].strip()
        cache_key = f"webshare:search:{query}:{int(limit or 20)}"
        files, _total = self.store.cached_if(cache_key, 0 if force else SEARCH_CACHE_TTL,
                                              lambda: self.ws.search(query, limit=int(limit or 20)))
        return [{
            "id": "ws:" + f["ident"],
            "type": "file",
            "title": f.get("name") or "",
            "year": None,
            "poster": f.get("img") or "",
            "size": f.get("size_h") or human_size(int(f.get("size") or 0)),
            "source": "webshare",
            "alt": None,
        } for f in files]

    # --- detail -------------------------------------------------------------

    def meta(self, ctype, item_id, series_id=None):
        base_id, season, episode = split_episode_id(item_id)
        if season is not None and series_id:
            base_id = series_id
        meta_type = "series" if season is not None else ctype
        meta = self.api_for(base_id).meta(meta_type, base_id)
        if is_sosac_id(base_id):
            enrich_one(meta, self.luna, self.store, meta_type)
        video = None
        if season is not None:
            video = next((v for v in meta.get("videos") or []
                          if int(v.get("season") or 0) == season and int(v.get("episode") or 0) == episode), None)
        return meta, video

    def episodes(self, series_id, season=None):
        """Epizody seriálu; bez `season` všechny."""
        meta = self.api_for(series_id).meta("series", series_id)
        out = []
        for video in meta.get("videos") or []:
            s = int(video.get("season") or 0)
            if season is not None and s != int(season):
                continue
            out.append({
                "id": video.get("id") or f"{series_id}:{s}:{int(video.get('episode') or 0)}",
                "season": s,
                "episode": int(video.get("episode") or 0),
                "title": video.get("title") or "",
                "thumbnail": video.get("thumbnail") or "",
                "released": video.get("released") or "",
                "description": (video.get("overview") or video.get("description") or "")[:4000],
            })
        out.sort(key=lambda v: (v["season"] == 0, v["season"], v["episode"]))
        return out

    # --- streamy ------------------------------------------------------------

    def _with_local_title(self, ctype, base_id, meta):
        """Doplní do metadat český název podle IMDb id (TMDB přes Lunu, jinak databáze filmů)."""
        kind = ctype if ctype in ("movie", "series") else "movie"
        try:
            title = self.catalog_detail(kind, base_id).get("title") or ""
        except NokturnoError as err:
            _LOGGER.debug("název podle %s: %s", base_id, err)
            return meta
        if not title or names_match(title, meta.get("name") or ""):
            return meta
        return {**meta, "name": title, "_title": title,
                "_orig": meta.get("_orig") or meta.get("name") or ""}

    def _cross_streams(self, ctype, item_id, meta, alt=None):
        """Streamy z druhého zdroje pro stejný titul (Luna ↔ Sosáč)."""
        base_id, season, episode = split_episode_id(item_id)
        if alt and self.sosac and not is_sosac_id(base_id):
            try:
                target = alt if season is None else self.sosac.episode_id(alt, season, episode)
                return self.sosac.streams(ctype, target) if target else []
            except Exception as err:  # noqa: BLE001 – nedostupný Sosáč nesmí shodit výpis
                _LOGGER.debug("cross-search (alt): %s", err)
                return []
        title = meta.get("_title") or meta.get("name") or ""
        year = self._year(meta)
        orig = meta.get("_orig") or None
        meta_type = "series" if season is not None else ctype
        try:
            if is_sosac_id(base_id):
                if not self.luna:
                    return []
                cid = "search.movie" if meta_type == "movie" else "search.series"
                for cand in self.luna.catalog(meta_type, cid, search=title)[:10]:
                    if not (names_match(cand.get("name"), title) or (orig and names_match(cand.get("name"), orig))):
                        continue
                    cand_year = self._year(cand)
                    if year and cand_year and abs(year - cand_year) > 1:
                        continue
                    target = cand["id"] if season is None else f"{cand['id']}:{season}:{episode}"
                    return self.luna.streams(meta_type, target)
                return []
            if not self.sosac:
                return []
            match = self.sosac.find_match(meta_type, title, year, orig)
            if not match:
                return []
            # find_match vrací celé meta, ne id — do streams/episode_id patří match["id"]
            target = match["id"] if season is None else self.sosac.episode_id(match["id"], season, episode)
            return self.sosac.streams(ctype, target) if target else []
        except Exception as err:  # noqa: BLE001 – výpadek druhého zdroje jen zaloguj
            _LOGGER.debug("cross-search: %s", err)
            return []

    def _describe(self, stream, index):
        """Stream do podoby vhodné pro HA (dashboard, hlasovka, automatizace)."""
        parse_stream(stream)
        channels = stream.get("channels") or {}
        # pevné pořadí: zdroj · kvalita · název souboru · zvuk · titulky · velikost
        full = clean_label(stream.get("label") if stream.get("_direct") else stream.get("_ws_name", ""))
        # metadata zdroje nemusí sedět na soubor (Luna hlásila „EN 5.1“ u souboru „…_cz_…“),
        # takže jazyk z názvu souboru se přidá k tomu, co uvádí zdroj
        codes = list(stream.get("langs") or [])
        for code in sorted(langs_from_name(full)):
            if code not in codes:
                codes.append(code)
        langs = [f"{code} {channels[code]:g}" if code in channels else code for code in codes]
        quality = QUALITY_NAMES.get(stream.get("quality_rank") or 0, "")
        if quality and stream.get("_estimated"):
            quality = "~" + quality  # odhad z velikosti, ne údaj ze zdroje
        source = SOURCE_NAMES.get(stream.get("source"), "")
        size = stream.get("size_gb") or 0
        name = full[:51] + "…" if len(full) > 52 else full
        parts = [p for p in (
            source,
            quality,
            name,
            ("zvuk " + " ".join(langs)) if langs else "",
            ("tit. " + " ".join(stream.get("subs") or [])) if stream.get("subs") else "",
            f"{size:.1f} GB" if size else "",
        ) if p]
        return {
            "index": index,
            # Sosáč streamuje z veřejného streamuj.tv, takže jeho odkazy hrají i mimo domácí síť
            "direct": bool(stream.get("_direct")) or bool(stream.get("_ws_url")) or stream.get("source") == "sosac",
            # odkaz, který funguje i mimo domácí síť (přímo z WebShare)
            "ws_url": stream.get("_ws_url", ""),
            "label": "  ·  ".join(parts) or clean_label(stream.get("label") or ""),
            "raw_label": clean_label(stream.get("label") or ""),
            "file": full,  # nezkrácený název souboru — karta ho dává do tooltipu
            "source": source,
            "quality": quality,
            "quality_rank": stream.get("quality_rank") or 0,
            "size_gb": round(size, 2) if size else None,
            "bitrate": stream.get("bitrate") or None,
            "langs": codes,
            "channels": channels,
            "subs": stream.get("subs") or [],
            "url": stream.get("url") or "",
            "subtitles": stream.get("subtitles") or [],
        }

    def original_titles(self, meta, ctype, alt=None):
        """Další názvy titulu pro fulltext: originál ze Sosáče (`_orig`), anglický název z Cinemety.

        Luna originál neposílá, přitom soubory na WebShare se často jmenují originálem
        („Outlander: Blood of My Blood“, „The Matrix“).
        """
        title = meta.get("_title") or meta.get("name") or ""
        names = [meta.get("_orig") or ""]
        if alt and self.sosac:
            try:
                alt_meta = self.sosac.meta(ctype, alt)
                names += [alt_meta.get("_orig") or "", alt_meta.get("_title") or ""]
            except (SosacError, Exception) as err:  # noqa: BLE001 – jen doplňkový zdroj
                _LOGGER.debug("originál z alt %s: %s", alt, err)
        imdb = meta.get("imdb_id") or (meta.get("id") if str(meta.get("id", "")).startswith("tt") else "")
        if imdb:
            def load():
                try:
                    return {"name": _cinemeta(ctype, imdb).get("name") or ""}
                except Exception:  # noqa: BLE001
                    return {"name": ""}
            names.append((self.store.cached(f"cmname:{ctype}:{imdb}", 30 * 86400, load) or {}).get("name", ""))
        out, seen = [], {_fold(title)}
        for name in names:
            key = _fold(name)
            if name and key and key not in seen and not key.isdigit():
                seen.add(key)
                out.append(name)
        return out

    def _title_queries(self, meta, video=None, ctype="movie", alt=None):
        """Dotazy pro fulltextové zdroje a filtr, který z výsledku nechá jen ten titul.

        Sdílí to WebShare i HellSpy — oba hledají v názvech souborů, takže potřebují
        totéž: víc variant názvu a pak zahodit všechno, co se jen podobá.
        """
        title = meta.get("_title") or meta.get("name") or ""
        origs = self.original_titles(meta, ctype, alt)
        if video:
            episode = f"S{int(video.get('season') or 0):02d}E{int(video.get('episode') or 0):02d}"
            queries = [f"{title} {episode}"] + [f"{o} {episode}" for o in origs]
        else:
            year = self._year(meta)
            queries = [f"{title} {year}" if year else title, title]
            queries += [f"{o} {year}" if year else o for o in origs]
        # fulltext WebShare vrací i soubory, které mají společné jen část slov („Krev mé krve" u
        # Hry o trůny i Cizinky) — bereme jen ty, co mají všechna slova názvu (nebo originálu)
        # a u epizody i její číslo (S02E01 / 2x01 / 02x01)
        def words(text):
            return [w for w in re.split(r"[^a-z0-9]+", _fold(text)) if len(w) > 2]
        wanted = [w for w in [words(title)] + [words(o) for o in origs] if w]
        episode_re = None
        if video:
            se, ep = int(video.get("season") or 0), int(video.get("episode") or 0)
            episode_re = re.compile(rf"s{se:02d}e{ep:02d}|(?<!\d){se:02d}?x{ep:02d}(?!\d)|(?<!\d){se}x{ep:02d}(?!\d)")

        # rok v názvu souboru rozliší stejnojmenné filmy („pět švestek“ 1983 vs. 2026);
        # roky, které patří k názvu titulu („Blade Runner 2049“), se ignorují
        want_year = None if video else self._year(meta)
        title_years = {int(y) for y in YEAR_RE.findall(_fold(title) + " " + " ".join(_fold(o) for o in origs))}

        def year_ok(folded):
            if not want_year:
                return True
            years = {int(y) for y in YEAR_RE.findall(folded)}
            years -= title_years - {want_year}
            # soubor bez roku v názvu propustíme, soubor s jiným rokem ne
            return not years or any(abs(y - want_year) <= 1 for y in years)

        def relevant(name):
            folded = _fold(name)
            if wanted and not any(all(w in folded for w in group) for group in wanted):
                return False
            if not year_ok(folded):
                return False
            return not episode_re or bool(episode_re.search(folded))

        return [q.strip() for q in dict.fromkeys(queries) if q.strip()], relevant

    def _webshare_streams(self, meta, video=None, ctype="movie", alt=None):
        """Tytéž soubory přímo z WebShare — jejich odkazy fungují i mimo domácí síť.

        Streamy přes Lunu míří na její lokální adresu (`http://192.168.1.10:7126/…`),
        takže na mobilu mimo LAN nehrají. WebShare vrací odkaz na svoje CDN.
        Hledá se ve víc variantách (s rokem, bez roku, originální název), protože
        jeden dotaz vrátí jen část souborů a nespárované streamy pak zůstanou bez odkazu.
        """
        if not self.ws:
            return []
        queries, relevant = self._title_queries(meta, video, ctype, alt)
        out, seen = [], set()
        for query in queries:
            try:
                files, _total = self.ws.search(query, limit=WS_LIMIT)
            except WebshareError as err:
                _LOGGER.debug("WebShare hledání „%s“: %s", query, err)
                continue
            for f in files:
                if f["ident"] in seen or not relevant(f.get("name") or ""):
                    continue
                seen.add(f["ident"])
                # velikost patří do `detail` — odtud ji `parse_stream` čte (v labelu ji nehledá).
                # `size_h` z WebShare je ve stejných jednotkách jako údaj Luny, takže se dvojice najdou.
                out.append({
                    "url": "ws:" + f["ident"],
                    "label": f.get("name") or "",
                    "detail": f.get("size_h") or (human_size(int(f["size"])) if f.get("size") else ""),
                    "source": "ws",
                    "_direct": True,
                })
        return out

    def _hellspy_streams(self, meta, video=None, ctype="movie", alt=None):
        """Tentýž titul na HellSpy. Nabízí se původní soubor, ne překódování, takže
        název i velikost popisují to, co se opravdu přehraje — viz `lib/hellspy_api`."""
        if not self.hs:
            return []
        queries, relevant = self._title_queries(meta, video, ctype, alt)
        out, seen = [], set()
        for query in queries:
            try:
                files, _next = self.hs.search(query, limit=HS_LIMIT)
            except HellspyError as err:
                _LOGGER.debug("HellSpy hledání „%s“: %s", query, err)
                continue
            for f in files:
                name = f.get("name") or ""
                # Táž nahrávka bývá na HellSpy vícekrát pod prakticky stejným názvem.
                # _fold zahodí cizí písmo úplně, takže se dvě jinak shodná jména liší
                # jen zbylou mezerou — proto se mezery ještě srovnají.
                key = (" ".join(_fold(name).split()), f["size"])
                if f["hash"] in seen or key in seen or not relevant(name):
                    continue
                seen.add(f["hash"])
                seen.add(key)
                out.append({
                    "url": f"hs:{f['id']}:{f['hash']}",
                    "label": name,
                    "detail": f.get("size_h") or "",
                    "source": "hs",
                    "_direct": True,
                })
        return out

    def _webshare_subtitles(self, meta, video=None, ctype="movie", alt=None):
        """Titulky k titulu z WebShare (`.srt`), české napřed — `ws:<ident>` jako u streamů."""
        if not self.ws:
            return []
        title = meta.get("_title") or meta.get("name") or ""
        year = self._year(meta)
        names = [title] + self.original_titles(meta, ctype, alt)
        if video:
            suffix = f" S{int(video.get('season') or 0):02d}E{int(video.get('episode') or 0):02d} srt"
        else:
            suffix = f" {year} srt" if year else " srt"
        groups = [[w for w in re.split(r"\W+", _fold(n)) if len(w) > 2] for n in names]
        found, seen = [], set()
        for query in [n + suffix for n in names]:
            try:
                root = self.ws._with_token("search", what=query, category="", sort="", limit=40, offset=0)
            except WebshareError as err:
                _LOGGER.debug("WebShare titulky: %s", err)
                continue
            for f in root.findall("file"):
                name, kind, ident = f.findtext("name") or "", (f.findtext("type") or "").lower(), f.findtext("ident")
                if kind != "srt" or ident in seen:
                    continue
                folded = _fold(name)
                if groups and not any(g and all(w in folded for w in g) for g in groups):
                    continue
                seen.add(ident)
                if year and not video and str(year) not in folded:
                    continue
                czech = bool(re.search(r"(^|[^a-z])(cz|cze|czech|cs)([^a-z]|$)", folded))
                found.append((0 if czech else 1, name, ident))
        found.sort()
        return ["ws:" + ident for _rank, _name, ident in found[:SUBS_MAX]]

    @staticmethod
    def _merge_direct(streams):
        """Tentýž soubor přes Lunu i přímo z WebShare → jedna položka.

        Popis z Luny je bohatší (bitrate, jazyky, kanály), přímý odkaz WebShare zase
        funguje mimo domácí síť a jede z jejich CDN. Necháme tedy popis z Luny
        a přibalíme k němu `_ws_url`; osamocené soubory z WebShare zůstanou zvlášť.
        Velikosti se párují s tolerancí — Luna zaokrouhluje jinak než WebShare.
        """
        direct = [s for s in streams if s.get("_direct") and (s.get("size_gb") or 0) > 0]
        used, out = set(), []
        for stream in streams:
            if stream.get("_direct"):
                continue
            size = stream.get("size_gb") or 0
            if size:
                best, closest = None, SIZE_TOLERANCE
                for cand in direct:
                    if id(cand) in used or (cand.get("quality_rank") or 0) != (stream.get("quality_rank") or 0):
                        continue
                    delta = abs((cand.get("size_gb") or 0) - size)
                    if delta < closest:
                        best, closest = cand, delta
                if best is not None:
                    stream["_ws_url"] = best["url"]
                    # název souboru zná jen WebShare (Luna posílá jen popis) — přebalit do páru
                    stream["_ws_name"] = best.get("label") or ""
                    used.add(id(best))
            out.append(stream)
        solo = [s for s in streams if s.get("_direct") and id(s) not in used]
        solo.sort(key=lambda s: -(s.get("size_gb") or 0))
        return out + solo[:SOLO_LIMIT]

    def _torrent_streams(self, meta, video=None, ctype="movie"):
        """Torrenty z trackerů přes Prowlarr. Poslední možnost, když jinde nic není.

        Zkouší se český i původní název: české trackery pojmenovávají soubory
        obojím a fulltext na jednom z nich často nevrátí nic. U seriálu se
        sezóna a díl vybírají až z výsledků, aby na díl 2x01 nevyskočila
        první sezóna."""
        api = self.prowlarr
        if api is None:
            return []
        titles = []
        for name in (meta.get("_title"), meta.get("name")):
            name = (name or "").strip()
            if name and name not in titles:
                titles.append(name)
        if not titles:
            return []
        season = episode = None
        if video and video.get("season") is not None:
            season = int(video["season"])
            episode = int(video.get("episode") or 0) or None
        year = str(meta.get("year") or meta.get("releaseInfo") or "")[:4]
        # U seriálu jde do dotazu jen název: trackery hledají fulltextem přes
        # název souboru a značka „S02E01“ v něm dotaz spolehlivě vynuluje
        # (ověřeno na Sk-CzTorrentu). Sezóna a díl se proto vybírají až
        # z výsledků. Rok u seriálu taky ne — v názvu bývá rok sezóny.
        queries = [t if season is not None or not year.isdigit() else f"{t} {year}" for t in titles]
        for query in queries:
            try:
                rows = api.search(query, "series" if season is not None else ctype,
                                  season=season, episode=episode)
            except ProwlarrError as err:  # noqa: BLE001 – výpadek trackerů není chyba titulu
                _LOGGER.warning("torrenty %s: %s", query, err)
                return []
            if rows:
                return rows
        return []

    @staticmethod
    def _describe_torrent(row, index):
        """Torrent do stejného tvaru jako stream, ale s vlastním druhem a bez přehrání."""
        size = row.get("size_gb") or 0
        name = row["title"][:51] + "…" if len(row["title"]) > 52 else row["title"]
        parts = [p for p in (
            "Torrent",
            row.get("quality") or "",
            name,
            f"{row['seeders']} seedů",
            f"{size:.1f} GB" if size else "",
        ) if p]
        return {
            "index": index,
            # torrent není odkaz na video — nedá se přehrát ani poslat do mobilu,
            # jde s ním jen jedno: zařadit do stahování
            "kind": "torrent",
            "direct": False,
            "ws_url": "",
            "label": "  ·  ".join(parts),
            "raw_label": row["title"],
            "file": row["title"],
            "source": "Torrent",
            "tracker": row.get("indexer") or "",
            "seeders": row.get("seeders") or 0,
            "leechers": row.get("leechers") or 0,
            "quality": row.get("quality") or "",
            "quality_rank": 0,
            "size_gb": size or None,
            "bitrate": None,
            "langs": [],
            "channels": {},
            "subs": [],
            "url": row.get("url") or "",
            "subtitles": [],
        }

    def torrents(self, ctype, item_id, series_id=None, offset=0):
        """Torrenty titulu. Hledají se až na vyžádání — trackery odpovídají
        v řádu sekund a u titulu, na který stream je, by to jen zdržovalo."""
        meta, video = self.meta(ctype, item_id, series_id)
        rows = self._torrent_streams(meta, video, ctype)
        return [self._describe_torrent(row, offset + i) for i, row in enumerate(rows)]

    # stavy qBittorrentu → co z toho má karta ukázat
    QBIT_STATES = {
        "downloading": "running", "forcedDL": "running", "metaDL": "running",
        "forcedMetaDL": "running", "allocating": "running", "checkingDL": "running",
        "stalledDL": "queued", "queuedDL": "queued", "stoppedDL": "queued", "pausedDL": "queued",
        "error": "error", "missingFiles": "error",
    }

    def torrent_jobs(self):
        """Rozdělané torrenty jako položky fronty stahování.

        Tvar je stejný jako u vlastního stahování, aby je karta uměla vykreslit
        beze změny. Hotové torrenty se nevracejí — ty už leží ve složce a karta
        je ukáže mezi staženými soubory."""
        api = self.qbit
        if api is None:
            return []
        try:
            rows = api.torrents()
        except QbitError as err:  # noqa: BLE001 – klient nemusí běžet, to není chyba integrace
            _LOGGER.debug("qBittorrent: %s", err)
            return []
        out = []
        for t in rows:
            state = self.QBIT_STATES.get(t.get("state") or "")
            if state is None:      # uploading, stalledUP, checkingUP… = staženo
                continue
            size = t.get("size_gb") or 0
            out.append({
                "id": "qb:" + str(t.get("hash") or ""),
                "name": t.get("name") or "",
                "status": state,
                "percent": t.get("progress") or 0,
                "size": int(size * 1073741824),
                "done": int(size * 1073741824 * (t.get("progress") or 0) / 100),
                "speed": t.get("speed") or 0,
                "eta": t.get("eta") if (t.get("eta") or 0) < 8640000 else None,
                "path": t.get("path") or "",
                "error": "",
                "torrent": True,
            })
        return out

    def cancel_torrent(self, torrent_hash):
        api = self.qbit
        if api is None:
            raise NokturnoError("qBittorrent není nastavený.")
        try:
            api.delete(torrent_hash, with_files=True)
        except QbitError as err:
            raise NokturnoError(str(err)) from err
        return True

    def streams_or_torrents(self, ctype, item_id, alt=None, series_id=None):
        """Streamy titulu, a když žádné nejsou, aspoň torrenty.

        Pro hlídání dostupnosti (nové díly, seznam k zhlédnutí): torrent je až
        poslední možnost, ale titul, který leží jen na trackeru, k dispozici je.
        Trackery se ptají jen když streamy nic nevrátily — jinak by každá
        kontrola stála dotazy navíc."""
        found = self.streams(ctype, item_id, alt, series_id)
        if found or self.prowlarr is None:
            return found
        try:
            return self.torrents(ctype, item_id, series_id)
        except Exception as err:  # noqa: BLE001 – tracker nesmí shodit kontrolu
            _LOGGER.debug("torrenty %s: %s", item_id, err)
            return []

    def forget_torrent(self, path):
        """Odebere z qBittorrentu torrent, ze kterého vznikl daný soubor.

        Volá se při mazání staženého filmu. Data si maže integrace sama (i s
        titulky), klientovi torrent jen zmizí ze seznamu — jinak by soubor dál
        seedoval a po smazání hlásil chybějící data. Cesty se porovnávají podle
        názvu souboru srovnaného na jednu podobu: qBittorrent může běžet jinde
        a diakritiku vracet v jiné normalizaci Unicode."""
        api = self.qbit
        if api is None or not path:
            return False
        want = unicodedata.normalize("NFC", os.path.basename(path)).casefold()
        try:
            rows = api.torrents()
        except QbitError as err:
            _LOGGER.debug("qBittorrent: %s", err)
            return False
        for row in rows:
            name = unicodedata.normalize("NFC", os.path.basename(row.get("path") or "")).casefold()
            if name and name == want:
                try:
                    api.delete(row.get("hash"), with_files=False)
                except QbitError as err:
                    _LOGGER.warning("torrent %s nejde odebrat: %s", row.get("name"), err)
                    return False
                return True
        return False

    def download_torrent(self, url, name=""):
        """Předá torrent qBittorrentu. Stažený soubor skončí ve složce stahování."""
        api = self.qbit
        if api is None:
            raise NokturnoError("qBittorrent není nastavený.")
        try:
            if not api.add(url, save_path=self._opt("download_dir", "") or "", rename=name):
                raise NokturnoError("qBittorrent torrent nepřijal.")
        except QbitError as err:
            raise NokturnoError(str(err)) from err
        return True

    def streams(self, ctype, item_id, alt=None, series_id=None):
        """Seřazené streamy titulu ze všech dostupných zdrojů.

        Síťové dohledání streamů se cachuje 72 h, ale JEN když něco našlo (`cached_if`) —
        prázdný výsledek by mohl být jen dočasný výpadek zdroje, takže se zkusí znovu
        hned příště. Řazení/filtrování podle uživatelských preferencí (jazyk, velikost,
        pořadí) běží vždy nad čerstvě načtenými daty, aby se projevila okamžitě.
        """
        meta, video = self.meta(ctype, item_id, series_id)
        base_id = split_episode_id(item_id)[0]

        def _fetch_streams():
            nonlocal meta
            api = self.api_for(base_id)
            try:
                found = api.streams(ctype, item_id, include_search=True) if isinstance(api, LunaApi) \
                    else api.streams(ctype, item_id)
            except Exception as err:  # noqa: BLE001 – výpadek zdroje = prázdno, ne chyba služby
                _LOGGER.warning("streamy %s: %s", item_id, err)
                found = []
            # titul otevřený jen podle IMDb id (z databáze filmů) má v metadatech mezinárodní přepis
            # („Sunday League…“), pod kterým Sosáč nic nenajde — podstrčíme mu český název z TMDB
            if not found and not alt and not is_sosac_id(base_id) and str(base_id).startswith("tt"):
                meta = self._with_local_title(ctype, base_id, meta)
            found += self._cross_streams(ctype, item_id, meta, alt)
            found += self._webshare_streams(meta, video, ctype, alt)
            found += self._hellspy_streams(meta, video, ctype, alt)
            for stream in found:
                parse_stream(stream)
                # bez kvality v názvu („Matrix (1999).mkv") by soubor spadl na konec seznamu,
                # i když je podle velikosti zjevně 4K — odhadneme ji, ale přiznaně (~)
                if not stream.get("quality_rank"):
                    guess = estimate_rank(stream.get("size_gb"))
                    if guess:
                        stream["quality_rank"] = guess
                        stream["_estimated"] = True
            found = self._merge_direct(found)
            # titulky z WebShare ke streamům, které žádné nemají (Sosáč si posílá svoje)
            subs = self._webshare_subtitles(meta, video, ctype, alt)
            if subs:
                for stream in found:
                    if not stream.get("subtitles"):
                        stream["subtitles"] = list(subs)
            # `parse_stream()` dává do langs/subs `set` — nejde ho serializovat do JSON
            # cache, tak se tu normalizuje na list (řazení navíc dělá cache stabilní)
            for stream in found:
                if isinstance(stream.get("langs"), set):
                    stream["langs"] = sorted(stream["langs"])
                if isinstance(stream.get("subs"), set):
                    stream["subs"] = sorted(stream["subs"])
            return found

        cache_key = f"streams:{ctype}:{item_id}:{alt or ''}"
        found = self.store.cached_if(cache_key, STREAMS_CACHE_TTL, _fetch_streams)
        try:
            max_gb = float(str(self._opt("max_size_gb", 0)).replace(",", ".") or 0)
        except ValueError:
            max_gb = 0.0
        lang = self._opt("pref_lang", "")
        order = self._opt("sort_streams", "quality")
        ordered = arrange(
            found,
            pref_lang=lang if lang in LANGS else "",
            hide_sd=bool(self.options.get("hide_sd")),
            max_size_gb=max_gb,
            order=order if order in SORT_ORDERS else "quality",
            pref_surround=bool(self.options.get("pref_surround")),
        )
        return [self._describe(s, i) for i, s in enumerate(ordered)]

    # co WebShare vrací u nedostupných souborů — hlášky jsou anglické a nic neříkající
    WS_ERRORS = {
        "temporarily unavailable": "WebShare tenhle soubor teď nevydá (bývá to dočasné). "
                                   "Zkus jiný stream ze seznamu.",
        "file not found": "Soubor už na WebShare není. Zkus jiný stream ze seznamu.",
        "file password": "Soubor na WebShare je chráněný heslem.",
    }

    def webshare_link(self, ident):
        if not self.ws:
            raise NokturnoError("WebShare účet není nastavený.")
        try:
            link = self.ws.file_link(ident)
        except WebshareError as err:
            text = str(err).lower()
            for needle, message in self.WS_ERRORS.items():
                if needle in text:
                    raise NokturnoError(message) from err
            raise NokturnoError(f"WebShare: {err}") from err
        if not link:
            raise NokturnoError("WebShare nevrátil odkaz na soubor. Zkus jiný stream ze seznamu.")
        return link

    def external_url(self, url):
        """Odkaz na Lunu přepsaný na adresu dostupnou mimo domácí síť (Tailscale).

        Luna posílá svoji LAN adresu (`http://192.168.1.10:7126/…`), takže na mobilu
        mimo síť nehraje. Odkazy WebShare a Sosáče jsou veřejné a nechávají se být.
        """
        host = str(self._opt("external_host", "")).strip()
        if not host or not url.startswith("http"):
            return url
        luna = urllib.parse.urlsplit(self._opt("luna_url", ""))
        parts = urllib.parse.urlsplit(url)
        if not luna.hostname or parts.hostname != luna.hostname:
            return url
        netloc = host if ":" in host else (f"{host}:{parts.port}" if parts.port else host)
        return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

    def resolve(self, url, prefer_external=False):
        """Přímé HTTP URL pro externí přehrávač (Sosáč vrací `streamuj:` odkazy)."""
        if not url:
            raise NokturnoError("Chybí odkaz na stream.")
        if url.startswith("ws:"):
            return self.webshare_link(url[3:])
        if url.startswith("hs:"):
            api = self.hs or HellspyApi(cache=self.store)
            file_id, _sep, file_hash = url[3:].partition(":")
            try:
                return api.file_link(file_id, file_hash)
            except HellspyError as err:
                raise NokturnoError(f"HellSpy: {err}") from err
        if url.startswith("streamuj:"):
            sosac = self.sosac
            if sosac is None:
                raise NokturnoError("Účet Streamuj není nastavený.")
            return sosac.resolve(url)
        return self.external_url(url) if prefer_external else url

    def find_first(self, ctype, query):
        """První výsledek hledání — pro „pusť X" jedním krokem (hlasovka, skripty)."""
        results = self.search(ctype, query, limit=3)
        if not results:
            raise NokturnoError(f"„{query}“ jsem nenašel.")
        return results[0]

    def best_stream(self, ctype, item_id, alt=None, series_id=None):
        streams = self.streams(ctype, item_id, alt, series_id)
        if not streams:
            raise NokturnoError("Pro tento titul se nenašel žádný stream.")
        return streams[0]
