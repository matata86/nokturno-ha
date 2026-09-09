"""Jádro integrace — hledání a streamy ve stejných zdrojích jako Kodi doplněk.

Logika odpovídá `default.py` doplňku (sloučení Luna ↔ Sosáč, cross-search, řazení),
ale bez Kodi: volání jsou synchronní a HA je pouští v executoru.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import urllib.parse

from .const import LANGS, SORT_ORDERS
from .lib.enrich import DEAD_IMAGES, _cinemeta, enrich, enrich_one
from .lib.luna_api import LunaApi, LunaError, clean_label, parse_base_url, parse_token
from .lib.sosac_api import SosacError, names_match
from .lib.sosac_api import is_sosac_id as _is_legacy_sosac_id
from .lib.sosac_direct import SosacDirect, is_direct_id
from .lib.store import Store
from .lib.streams import arrange, estimate_rank, parse_stream
from .lib.webshare_api import WebshareApi, WebshareError, human_size

WS_LIMIT = 25    # kolik souborů brát z fulltextu WebShare
SOLO_LIMIT = 8   # kolik z nich nechat v seznamu, když k nim Luna nemá protějšek
SIZE_TOLERANCE = 0.25  # GB – Luna a WebShare zaokrouhlují velikost jinak
HISTORY_MAX = 12
SUBS_MAX = 3

_LOGGER = logging.getLogger(__name__)

SOURCE_NAMES = {"main": "Luna", "search": "WebShare", "ws": "WebShare", "sosac": "Sosáč"}

QUALITY_NAMES = {4: "4K", 3: "Full HD", 2: "HD", 1: "SD", 0: ""}


def _fold(text):
    """Bez diakritiky, malá písmena — pro porovnávání názvů souborů."""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


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

    # --- konfigurace --------------------------------------------------------

    def update_options(self, options):
        self.options = dict(options)
        self._luna = self._sosac = self._ws = None
        self._ws_ready = False

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

    def sources(self):
        """Které zdroje jsou nakonfigurované (pro diagnostiku)."""
        return {"luna": self.luna is not None, "sosac": self.sosac is not None, "webshare": self.ws is not None}

    def api_for(self, item_id):
        api = self.sosac if is_sosac_id(item_id) else self.luna
        if api is None:
            raise NokturnoError("Zdroj tohoto titulu není nastavený (Luna / Sosáč).")
        return api

    # --- hledání ------------------------------------------------------------

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
            "description": (meta.get("description") or "")[:600],
            "rating": meta.get("imdbRating") or "",
            "source": "sosac" if is_sosac_id(meta.get("id")) else "luna",
            "alt": alt,
        }

    def search(self, ctype="movie", query="", limit=20):
        """Sloučené výsledky z Luny a Sosáče (stejný titul jen jednou)."""
        query = (query or "").strip()
        if not query:
            raise NokturnoError("Prázdný dotaz.")
        luna_metas, sosac_metas, errors = [], [], []
        if self.luna:
            try:
                cid = "search.movie" if ctype == "movie" else "search.series"
                luna_metas = self.luna.catalog(ctype, cid, search=query)
            except LunaError as err:
                errors.append(f"Luna: {err}")
        if self.sosac:
            try:
                sosac_metas = self.sosac.search(ctype, query)
            except SosacError as err:
                errors.append(f"Sosáč: {err}")
        if not luna_metas and not sosac_metas and errors:
            raise NokturnoError("; ".join(errors))
        merged = self._merge(luna_metas, sosac_metas)[: int(limit or 20)]
        enrich([m for m, _alt in merged if is_sosac_id(m.get("id"))], self.luna, self.store, ctype)
        return [self._item(meta, ctype, alt) for meta, alt in merged]

    # --- historie hledání -----------------------------------------------------

    def history(self):
        return list(self.store.load("history", []))

    def add_history(self, query):
        query = (query or "").strip()
        if not query:
            return
        items = [q for q in self.history() if q.lower() != query.lower()]
        self.store.save("history", ([query] + items)[:HISTORY_MAX])

    def clear_history(self):
        self.store.save("history", [])

    def search_webshare(self, query, limit=20):
        """Soubory přímo z WebShare (fulltext), bez metadat titulu."""
        if not self.ws:
            raise NokturnoError("WebShare účet není nastavený.")
        files, _total = self.ws.search(query, limit=int(limit or 20))
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
                "description": (video.get("overview") or video.get("description") or "")[:600],
            })
        out.sort(key=lambda v: (v["season"] == 0, v["season"], v["episode"]))
        return out

    # --- streamy ------------------------------------------------------------

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
        langs = [f"{code} {channels[code]:g}" if code in channels else code for code in stream.get("langs") or []]
        quality = QUALITY_NAMES.get(stream.get("quality_rank") or 0, "")
        if quality and stream.get("_estimated"):
            quality = "~" + quality  # odhad z velikosti, ne údaj ze zdroje
        source = SOURCE_NAMES.get(stream.get("source"), "")
        size = stream.get("size_gb") or 0
        # pevné pořadí: zdroj · kvalita · název souboru · zvuk · titulky · velikost
        name = clean_label(stream.get("label") if stream.get("_direct") else stream.get("_ws_name", ""))
        if len(name) > 52:
            name = name[:51] + "…"
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
            "source": source,
            "quality": quality,
            "quality_rank": stream.get("quality_rank") or 0,
            "size_gb": round(size, 2) if size else None,
            "bitrate": stream.get("bitrate") or None,
            "langs": stream.get("langs") or [],
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

    def _webshare_streams(self, meta, video=None, ctype="movie", alt=None):
        """Tytéž soubory přímo z WebShare — jejich odkazy fungují i mimo domácí síť.

        Streamy přes Lunu míří na její lokální adresu (`http://192.168.1.10:7126/…`),
        takže na mobilu mimo LAN nehrají. WebShare vrací odkaz na svoje CDN.
        Hledá se ve víc variantách (s rokem, bez roku, originální název), protože
        jeden dotaz vrátí jen část souborů a nespárované streamy pak zůstanou bez odkazu.
        """
        if not self.ws:
            return []
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

        def relevant(name):
            folded = _fold(name)
            if wanted and not any(all(w in folded for w in group) for group in wanted):
                return False
            return not episode_re or bool(episode_re.search(folded))

        out, seen = [], set()
        for query in dict.fromkeys(q.strip() for q in queries if q.strip()):
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

    def streams(self, ctype, item_id, alt=None, series_id=None):
        """Seřazené streamy titulu ze všech dostupných zdrojů."""
        meta, video = self.meta(ctype, item_id, series_id)
        base_id = split_episode_id(item_id)[0]
        api = self.api_for(base_id)
        try:
            found = api.streams(ctype, item_id, include_search=True) if isinstance(api, LunaApi) \
                else api.streams(ctype, item_id)
        except Exception as err:  # noqa: BLE001 – výpadek zdroje = prázdno, ne chyba služby
            _LOGGER.warning("streamy %s: %s", item_id, err)
            found = []
        found += self._cross_streams(ctype, item_id, meta, alt)
        found += self._webshare_streams(meta, video, ctype, alt)
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

    def webshare_link(self, ident):
        if not self.ws:
            raise NokturnoError("WebShare účet není nastavený.")
        return self.ws.file_link(ident)

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
