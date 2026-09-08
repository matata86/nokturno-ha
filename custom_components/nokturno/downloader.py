"""Stahování streamů do složky HA (výchozí `/media/nokturno`, vidí ji i Media Browser)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIGNAL_DOWNLOADS

_LOGGER = logging.getLogger(__name__)

CHUNK = 1024 * 512
MAX_PARALLEL = 1


def safe_name(name, url=""):
    """Název souboru bez znaků, které rozbijí cestu; přípona podle URL."""
    base = re.sub(r"[\\/:*?\"<>|]+", "_", (name or "").strip()) or "nokturno"
    base = re.sub(r"\s+", " ", base)[:120]
    if not os.path.splitext(base)[1]:
        ext = os.path.splitext(url.split("?")[0])[1]
        base += ext if 1 < len(ext) <= 5 else ".mp4"
    return base


class Downloader:
    """Fronta stahování — jedno běží, ostatní čekají."""

    def __init__(self, hass: HomeAssistant, directory: str):
        self.hass = hass
        self.directory = directory
        self.jobs: dict[str, dict] = {}
        self.files: list[dict] = []
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._current: asyncio.Task | None = None

    def set_directory(self, directory):
        self.directory = directory

    # --- hotové soubory -----------------------------------------------------

    def _scan(self):
        """Co ve složce opravdu leží — přežije to restart HA, na rozdíl od fronty."""
        try:
            entries = [e for e in os.scandir(self.directory) if e.is_file() and not e.name.endswith(".part")]
        except OSError:
            return []
        out = [{"name": e.name, "path": e.path, "size": e.stat().st_size, "modified": e.stat().st_mtime}
               for e in entries]
        out.sort(key=lambda f: f["modified"], reverse=True)
        return out

    async def async_refresh_files(self):
        self.files = await self.hass.async_add_executor_job(self._scan)
        self._notify()
        return self.files

    async def async_delete(self, path):
        """Smaže stažený soubor — jen uvnitř složky pro stahování."""
        target = os.path.abspath(path)
        root = os.path.abspath(self.directory)
        if os.path.commonpath([target, root]) != root:
            raise ValueError(f"Soubor {path} není ve složce {self.directory}.")
        await self.hass.async_add_executor_job(os.remove, target)
        for job_id, job in list(self.jobs.items()):
            if os.path.abspath(job.get("path", "")) == target and job["status"] == "done":
                self.jobs.pop(job_id)
        await self.async_refresh_files()

    # --- fronta -------------------------------------------------------------

    def add(self, url, name, meta=None):
        job_id = uuid.uuid4().hex[:8]
        self.jobs[job_id] = {
            "id": job_id,
            "name": name,
            "url": url,
            "status": "queued",
            "done": 0,
            "size": 0,
            "percent": 0,
            "path": os.path.join(self.directory, safe_name(name, url)),
            "started": time.time(),
            "error": "",
            **(meta or {}),
        }
        self._queue.put_nowait(job_id)
        if self._worker is None or self._worker.done():
            self._worker = self.hass.async_create_background_task(self._run(), "nokturno_downloader")
        self._notify()
        return self.jobs[job_id]

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if not job:
            return False
        if job["status"] == "running" and self._current and not self._current.done():
            self._current.cancel()
        job["status"] = "canceled"
        self._notify()
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

    def _notify(self):
        async_dispatcher_send(self.hass, SIGNAL_DOWNLOADS)

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
                job["status"] = "canceled"
                self._cleanup(job)
                self._notify()
            except Exception as err:  # noqa: BLE001 – chyba jedné položky nesmí zabít frontu
                job.update(status="error", error=str(err)[:200])
                self._cleanup(job)
                _LOGGER.error("stahování %s selhalo: %s", job["name"], err)
                self._notify()

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
        self._notify()
        session = async_get_clientsession(self.hass)
        tmp = job["path"] + ".part"
        last = 0.0
        async with session.get(job["url"], timeout=None) as resp:
            resp.raise_for_status()
            job["size"] = int(resp.headers.get("Content-Length") or 0)
            with open(tmp, "wb") as handle:
                async for chunk in resp.content.iter_chunked(CHUNK):
                    handle.write(chunk)
                    job["done"] += len(chunk)
                    if job["size"]:
                        job["percent"] = round(job["done"] / job["size"] * 100, 1)
                    if time.time() - last > 2:  # stav ven jen občas, ne u každého chunku
                        last = time.time()
                        self._notify()
        await self.hass.async_add_executor_job(os.replace, tmp, job["path"])
        job.update(status="done", percent=100)
        await self.async_refresh_files()
        _LOGGER.info("staženo: %s", job["path"])
