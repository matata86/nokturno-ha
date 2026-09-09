"""Stahování streamů do složky HA (výchozí `/media/nokturno`, vidí ji i Media Browser)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import unicodedata
import time
import uuid

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIGNAL_DOWNLOADS

_LOGGER = logging.getLogger(__name__)

CHUNK = 1024 * 512
FLUSH = 8 * 1024 * 1024   # kolik se nasbírá, než se sáhne na disk
SUBTITLE_EXT = (".srt", ".sub", ".ass", ".vtt")
MAX_PARALLEL = 1


def _append(path, data, mode="ab"):
    """Zápis kusu souboru — běží ve vlákně, ne ve smyčce událostí."""
    with open(path, mode) as handle:
        handle.write(data)


def _file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _write_bytes(path, data):
    with open(path, "wb") as handle:
        handle.write(data)


def safe_name(name, url=""):
    """Název souboru bez znaků, které rozbijí cestu; přípona podle URL."""
    base = re.sub(r"[\\/:*?\"<>|]+", "_", (name or "").strip()) or "nokturno"
    base = re.sub(r"\s+", " ", base)[:120]
    if not os.path.splitext(base)[1]:
        ext = os.path.splitext(url.split("?")[0])[1]
        base += ext if 1 < len(ext) <= 5 else ".mp4"
    return base


def _key(path):
    """Název souboru srovnaný na jednu podobu — pro porovnání napříč zdroji."""
    return unicodedata.normalize("NFC", os.path.basename(path or "")).casefold()


class Downloader:
    """Fronta stahování — jedno běží, ostatní čekají."""

    def __init__(self, hass: HomeAssistant, directory: str, store=None):
        self.hass = hass
        self.directory = directory
        self.store = store          # kvůli přežití restartu
        self.resolver = None        # callback(source_url) → čerstvá adresa (odkazy WebShare expirují)
        self.jobs: dict[str, dict] = {}
        self.files: list[dict] = []
        # rozdělané torrenty z qBittorrentu — vlastní fronta to není, ale karta
        # obojí ukazuje na jednom místě
        self.torrents: list[dict] = []
        self.free_gb: float = 0.0
        self.on_done = None  # callback(job) po dokončení – notifikace
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._current: asyncio.Task | None = None
        self._saved = 0.0

    def set_directory(self, directory):
        self.directory = directory

    # --- hotové soubory -----------------------------------------------------

    def _scan(self):
        """Co ve složce opravdu leží — přežije to restart HA, na rozdíl od fronty.

        Titulky se do seznamu nedávají zvlášť, patří k videu (počítají se u něj).
        Rozdělané torrenty se vynechají: qBittorrent zapisuje rovnou pod finálním
        názvem, takže by se soubor tvářil jako hotový, dokud se stahuje.
        """
        try:
            entries = [e for e in os.scandir(self.directory) if e.is_file() and not e.name.endswith(".part")]
        except OSError:
            return []
        subs = {}
        videos = []
        for entry in entries:
            if os.path.splitext(entry.name)[1].lower() in SUBTITLE_EXT:
                stem = os.path.splitext(entry.name)[0].rsplit(".", 1)[0]
                subs[stem] = subs.get(stem, 0) + 1
            else:
                videos.append(entry)
        # qBittorrent hlásí názvy tak, jak jsou v torrentu; souborový systém je
        # může vrátit v jiné normalizaci Unicode, takže se porovnávají srovnané
        pending = {_key(t["path"]) for t in self.torrents if t.get("path")}
        out = [{"name": e.name, "path": e.path, "size": e.stat().st_size, "modified": e.stat().st_mtime,
                "subtitles": subs.get(os.path.splitext(e.name)[0], 0)}
               for e in videos if _key(e.path) not in pending]
        out.sort(key=lambda f: f["modified"], reverse=True)
        return out

    def _free(self):
        try:
            return shutil.disk_usage(self.directory).free / 1024 ** 3
        except OSError:
            return 0.0

    @staticmethod
    def _remove_with_subs(path):
        os.remove(path)
        stem = os.path.splitext(path)[0]
        for suffix in SUBTITLE_EXT:
            for candidate in (stem + suffix, stem + ".2" + suffix, stem + ".3" + suffix):
                try:
                    os.remove(candidate)
                except OSError:
                    pass

    async def async_refresh_files(self):
        self.files = await self.hass.async_add_executor_job(self._scan)
        self.free_gb = await self.hass.async_add_executor_job(self._free)
        self._notify()
        return self.files

    async def async_delete(self, path):
        """Smaže stažený soubor — jen uvnitř složky pro stahování."""
        target = os.path.abspath(path)
        root = os.path.abspath(self.directory)
        if os.path.commonpath([target, root]) != root:
            raise ValueError(f"Soubor {path} není ve složce {self.directory}.")
        await self.hass.async_add_executor_job(self._remove_with_subs, target)
        for job_id, job in list(self.jobs.items()):
            if os.path.abspath(job.get("path", "")) == target and job["status"] == "done":
                self.jobs.pop(job_id)
        await self.async_refresh_files()

    # --- fronta -------------------------------------------------------------

    def add(self, url, name, meta=None, subtitles=None, source_url=""):
        job_id = uuid.uuid4().hex[:8]
        self.jobs[job_id] = {
            "id": job_id,
            "name": name,
            "url": url,
            "source_url": source_url or url,  # `ws:<ident>` — po restartu se z něj vyrobí nový odkaz
            "status": "queued",
            "done": 0,
            "size": 0,
            "percent": 0,
            "path": os.path.join(self.directory, safe_name(name, url)),
            "started": time.time(),
            "speed": 0.0,          # B/s z posledního úseku
            "eta": None,           # sekundy do konce, když je známá velikost
            "error": "",
            "subtitles": list(subtitles or []),
            **(meta or {}),
        }
        self._queue.put_nowait(job_id)
        if self._worker is None or self._worker.done():
            self._worker = self.hass.async_create_background_task(self._run(), "nokturno_downloader")
        self._notify(save=True)
        return self.jobs[job_id]

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if not job:
            return False
        job["_by_user"] = True
        if job["status"] == "running" and self._current and not self._current.done():
            self._current.cancel()
        job["status"] = "canceled"
        self._cleanup(job)
        self._notify(save=True)
        return True

    def remove(self, job_id):
        self.cancel(job_id)
        self.jobs.pop(job_id, None)
        self._notify()

    def shutdown(self):
        if self._current and not self._current.done():
            self._current.cancel()
        if self._worker and not self._worker.done():
            self._worker.cancel()

    def _notify(self, save=False):
        async_dispatcher_send(self.hass, SIGNAL_DOWNLOADS)
        # zapisovat každý tik by bylo zbytečné psaní na disk; při změně stavu ale hned
        if self.store and (save or time.time() - self._saved > 20):
            self._saved = time.time()
            self.hass.async_add_executor_job(self._save)

    def _save(self):
        keep = ("id", "name", "url", "source_url", "status", "done", "size", "percent",
                "path", "error", "subtitles", "stream", "started")
        self.store.save("downloads", [{k: job.get(k) for k in keep}
                                      for job in list(self.jobs.values())[-30:]])

    async def async_restore(self):
        """Po restartu HA navázat na přerušené stahování (soubor `.part` zůstal na disku)."""
        if not self.store:
            return
        saved = await self.hass.async_add_executor_job(self.store.load, "downloads", [])
        resumed = 0
        for job in saved:
            if not job.get("id"):
                continue
            # doplnit klíče, které starší zápis nemusí mít — senzor je čte napřímo
            job.setdefault("started", time.time())
            job.setdefault("speed", 0.0)
            job.setdefault("eta", None)
            job.setdefault("subtitles", [])
            self.jobs[job["id"]] = job
            if job.get("status") in ("queued", "running"):
                job["status"] = "queued"
                self._queue.put_nowait(job["id"])
                resumed += 1
        if resumed:
            _LOGGER.info("navazuji na %d přerušené stahování", resumed)
            if self._worker is None or self._worker.done():
                self._worker = self.hass.async_create_background_task(self._run(), "nokturno_downloader")
        self._notify()

    # --- vlastní stahování --------------------------------------------------

    async def _run(self):
        while not self._queue.empty():
            job_id = await self._queue.get()
            job = self.jobs.get(job_id)
            if not job or job["status"] != "queued":
                continue
            self._current = self.hass.async_create_task(self._download(job))
            try:
                await self._current
            except asyncio.CancelledError:
                if job.get("_by_user"):
                    job["status"] = "canceled"
                    self._cleanup(job)
                else:
                    # vypnutí HA — `.part` necháme ležet, po startu se na něj naváže
                    job["status"] = "queued"
                    _LOGGER.info("stahování %s přerušeno, naváže se po startu", job["name"])
                self._notify(save=True)
                raise
            except Exception as err:  # noqa: BLE001 – chyba jedné položky nesmí zabít frontu
                job.update(status="error", error=str(err)[:200])
                self._cleanup(job)
                _LOGGER.error("stahování %s selhalo: %s", job["name"], err)
                self._notify(save=True)

    def _cleanup(self, job):
        """Nedokončený `.part` po zrušení nebo chybě smazat, ať se nehromadí."""
        try:
            os.remove(job["path"] + ".part")
        except OSError:
            pass

    def _ensure_dir(self):
        # pozor: os.makedirs(cesta, True) by True předalo jako práva (0o001), ne jako exist_ok
        os.makedirs(self.directory, exist_ok=True)

    async def _download(self, job):
        await self.hass.async_add_executor_job(self._ensure_dir)
        job.update(status="running", error="")
        self._notify(save=True)
        session = async_get_clientsession(self.hass)
        tmp = job["path"] + ".part"
        # co už je na disku z minula (restart HA) — na to se dá navázat
        have = await self.hass.async_add_executor_job(_file_size, tmp)
        if have and self.resolver and job.get("source_url"):
            try:  # odkaz z WebShare mezitím vypršel, tak si vyžádáme nový
                job["url"] = await self.hass.async_add_executor_job(self.resolver, job["source_url"])
            except Exception as err:  # noqa: BLE001 – když to nevyjde, zkusíme starý odkaz
                _LOGGER.debug("obnova odkazu %s: %s", job["name"], err)
        headers = {"Range": f"bytes={have}-"} if have else {}
        last = time.time()
        last_done = job["done"]
        async with session.get(job["url"], headers=headers, timeout=None) as resp:
            resp.raise_for_status()
            length = int(resp.headers.get("Content-Length") or 0)
            if resp.status == 206 and have:  # server umí navázat
                job["done"] = have
                job["size"] = have + length
                mode = "ab"
                _LOGGER.info("navazuji na %s od %.1f MB", job["name"], have / 1024 ** 2)
            else:  # server rozsah neumí (nebo nebylo na co navázat) — od začátku
                job["done"] = 0
                job["size"] = length
                mode = "wb"
            last_done = job["done"]
            # zápis patří do vlákna, ne do smyčky událostí — HA jinak hlásí blokující volání.
            # Chunky se sbírají do bufferu, ať se do executoru nechodí kvůli každým 512 kB.
            buffer: list[bytes] = []
            buffered = 0
            async for chunk in resp.content.iter_chunked(CHUNK):
                buffer.append(chunk)
                buffered += len(chunk)
                job["done"] += len(chunk)
                if buffered >= FLUSH:
                    await self.hass.async_add_executor_job(_append, tmp, b"".join(buffer), mode)
                    mode = "ab"  # další zápisy už jen připojují
                    buffer, buffered = [], 0
                if job["size"]:
                    job["percent"] = round(job["done"] / job["size"] * 100, 1)
                now = time.time()
                if now - last > 2:  # stav ven jen občas, ne u každého chunku
                    # rychlost z posledního úseku, ne průměr od začátku — ať reaguje na zpomalení
                    job["speed"] = (job["done"] - last_done) / (now - last)
                    job["eta"] = round((job["size"] - job["done"]) / job["speed"]) \
                        if job["size"] and job["speed"] > 0 else None
                    last, last_done = now, job["done"]
                    self._notify()
            await self.hass.async_add_executor_job(_append, tmp, b"".join(buffer), mode)
        await self.hass.async_add_executor_job(os.replace, tmp, job["path"])
        for index, sub_url in enumerate(job.get("subtitles") or []):
            await self._download_subtitle(job, sub_url, index)
        job.update(status="done", percent=100, speed=0.0, eta=0)
        self._notify(save=True)
        await self.async_refresh_files()
        _LOGGER.info("staženo: %s", job["path"])
        if self.on_done:
            try:
                await self.on_done(job)
            except Exception as err:  # noqa: BLE001 – notifikace nesmí shodit frontu
                _LOGGER.warning("oznámení o stažení: %s", err)

    async def _download_subtitle(self, job, url, index):
        """Titulky vedle videa — stejný název, přípona .srt (další jako .2.srt), ať je Kodi/VLC najde."""
        stem = os.path.splitext(job["path"])[0]
        dest = f"{stem}.srt" if index == 0 else f"{stem}.{index + 1}.srt"
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url, timeout=60) as resp:
                resp.raise_for_status()
                data = await resp.read()
            await self.hass.async_add_executor_job(_write_bytes, dest, data)
        except Exception as err:  # noqa: BLE001 – titulky jsou bonus
            _LOGGER.warning("titulky k %s: %s", job["name"], err)
