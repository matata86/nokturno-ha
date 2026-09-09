/**
 * Nokturno — karta pro hledání ve WebShare, Sosáči a Luně.
 *
 * Hledání → výsledky → streamy → přehrát v Kodi / poslat do mobilu / stáhnout.
 * Data tahá ze služeb integrace `nokturno` (volání s návratovou hodnotou).
 *
 * Ovládací prvky jsou nativní z HA (`ha-input`, `ha-control-select`, `ha-control-button`,
 * `ha-control-select-menu`), aby karta vypadala stejně jako zbytek dashboardu. Pozor:
 * HA 2026.9 nahradil `ha-textfield` za `ha-input` a část prvků se do stránky dotahuje líně.
 *
 * Konfigurace karty (vše volitelné):
 *   type: custom:nokturno-card
 *   player: media_player.coreelec      # výchozí přehrávač
 *   players: [media_player.coreelec, media_player.samsung_tv_q6]
 *   phone: notify.mobile_app_sm_s921b  # výchozí mobil (jinak první nabídnutý)
 *   phones: [...]                      # ruční seznam mobilů
 *   downloads: sensor.nokturno_stahovani
 */

const CARD_VERSION = "1.47.0";
console.info(`%c NOKTURNO-CARD %c ${CARD_VERSION} `, "background:#5b4b8a;color:#fff;border-radius:3px 0 0 3px", "background:#f0b429;color:#222;border-radius:0 3px 3px 0");

const SOURCE_COLORS = { "Luna": "#8e7cc3", "WebShare": "#4a90d9", "Sosáč": "#e08b3c", "Torrent": "#3f9e6f" };
const KINDS = [
  { value: "movie", label: "Filmy" },
  { value: "series", label: "Seriály" },
];

class NokturnoCard extends HTMLElement {
  setConfig(config) {
    this._config = {
      players: config.players || (config.player ? [config.player] : []),
      phones: config.phones || [],
      downloads: config.downloads || "sensor.nokturno_stahovani",
      title: config.title || "Nokturno",
      show_header: config.show_header !== false,
      ...config,
    };
    this._state = {
      view: "search", type: "movie", query: "", results: [], streams: [], episodes: [],
      seasons: [], season: null, item: null, title: "", busy: false, searching: false, loading: null, error: "",
      byType: { movie: [], series: [] }, bothTypes: false,
      player: config.player || (config.players || [])[0] || "", phone: config.phone || "",
      continueItems: null, stack: [],
    };
    this._started = false;
  }

  set hass(hass) {
    this._hass = hass;
    // nativní rozbalovací seznam se řídí color-scheme, ne proměnnými motivu
    const dark = !!(hass.themes && hass.themes.darkMode);
    if (this._dark !== dark) {
      this._dark = dark;
      this.style.colorScheme = dark ? "dark" : "light";
    }
    if (!this._started) {
      this._started = true;
      // ha-input a spol. se do stránky dotahují líně — bez čekání by zůstala prázdná místa
      this._ready().then(() => this._render());
    } else if (this._root) {
      this._renderDownloads();
      // změna sledovaných seriálů nebo historie → překreslit úvod / detail (a zahodit dočasné stavy)
      const key = JSON.stringify([this._sensorAttr("series"), this._sensorAttr("search_history")]);
      if (key !== this._sensorKey) {
        this._sensorKey = key;
        this._watchOverride = {};
        this._wantOverride = {};
        if (this._state.view === "search" || this._state.view === "episodes") this._paint();
      }
    }
  }

  /** Atribut z toho senzoru integrace, který ho má (historie je u stahování, seriály u „Nové díly“). */
  _sensorAttr(name) {
    const states = (this._hass && this._hass.states) || {};
    const own = states[this._config.downloads];
    if (own && own.attributes[name] !== undefined) return own.attributes[name];
    const other = Object.values(states).find((s) =>
      s.entity_id.startsWith("sensor.") && s.entity_id.includes("nokturno") && s.attributes[name] !== undefined);
    return other ? other.attributes[name] : null;
  }

  getCardSize() { return 12; }

  static getStubConfig() { return { type: "custom:nokturno-card" }; }

  static getConfigElement() { return document.createElement("nokturno-card-editor"); }

  async _ready() {
    const needed = ["ha-input", "ha-control-select", "ha-control-button", "ha-select", "mwc-list-item", "ha-icon-button"];
    if (needed.every((tag) => customElements.get(tag))) return;
    try { await window.loadCardHelpers(); } catch (err) { /* starší HA — vykreslí se i tak */ }
    await Promise.race([
      Promise.all(needed.map((tag) => customElements.whenDefined(tag))),
      new Promise((done) => setTimeout(done, 3000)),
    ]);
  }

  /** Volání služby s odpovědí (HA 2023.7+ vrací {response}). */
  async _call(service, data, wantResponse = true) {
    const res = await this._hass.callService("nokturno", service, data, undefined, false, wantResponse);
    return wantResponse ? (res && res.response) || {} : res;
  }

  async _guard(fn) {
    this._state.busy = true; this._state.error = ""; this._paint();
    try { await fn(); }
    catch (err) { this._state.error = (err && (err.message || err.error)) || String(err); }
    finally { this._state.busy = false; this._state.searching = false; this._state.loading = null; this._paint(); }
  }

  // --- akce -----------------------------------------------------------------

  /** ha-input drží text ve vnořeném `wa-input`; property nemusí být aktuální. */
  _readInput() {
    const el = this._input;
    if (!el) return "";
    if (el.value) return el.value;
    const inner = el.shadowRoot && el.shadowRoot.querySelector("wa-input, input");
    const deeper = inner && inner.shadowRoot && inner.shadowRoot.querySelector("input");
    return (deeper && deeper.value) || (inner && inner.value) || "";
  }

  async _search() {
    // uživatel je v databázi filmů → další hledání tam taky, dokud se sám nepřepne zpět
    if (this._state.pendingCatalog || (this._state.catalog && this._state.view === "results")) {
      this._state.pendingCatalog = false;
      return this._searchCatalog();
    }
    const query = (this._state.query || this._readInput() || "").trim();
    if (!query) return;
    this._state.stack = [];
    this._state.query = query;
    this._state.searching = true;
    await this._guard(async () => {
      const st = this._state;
      // jedno hledání pro obojí — přepínač Filmy/Seriály má smysl, jen když jsou obojí
      const [movies, series] = await Promise.all([
        this._call("search", { query, type: "movie", limit: 24 }),
        this._call("search", { query, type: "series", limit: 24 }),
      ]);
      st.byType = { movie: movies.results || [], series: series.results || [] };
      this._pickType();
      st.item = null;
      st.view = "results";
    });
  }

  /** Co ukázat po hledání: typ, který něco našel; obojí = necháme na uživateli. */
  _pickType() {
    const st = this._state;
    const both = st.byType.movie.length > 0 && st.byType.series.length > 0;
    if (!both) st.type = st.byType.series.length ? "series" : "movie";
    st.results = st.byType[st.type] || [];
    st.bothTypes = both;
  }

  async _openItem(item) {
    this._state.item = item;
    this._state.title = item.title;
    this._state.episode = null;
    this._state.descOpen = false;
    if (item.type === "file") {
      // soubor z fulltextu WebShare — žádný detail titulu, rovnou jeden „stream“
      this._state.streams = [{ index: 0, label: item.size || item.title, source: "WebShare", url: item.id }];
      this._state.streamTarget = { url: item.id, name: item.title };
      this._state.view = "streams";
      this._paint();
      return;
    }
    if (item.source === "katalog") return this._openCatalog(item);
    if (item.type === "series") {
      this._state.stack.push(this._state.view);
      await this._guard(async () => {
        const res = await this._call("episodes", { id: item.id });
        this._state.episodes = res.episodes || [];
        this._state.seasons = res.seasons || [];
        this._state.season = this._state.seasons.find((s) => s > 0) ?? this._state.seasons[0] ?? null;
        this._state.view = "episodes";
      });
      this._fillDetail();
      return;
    }
    await this._loadStreams({ id: item.id, type: "movie", alt: item.alt });
    this._fillDetail();
  }

  /** Plakát a popis z databáze filmů — u titulů, které mají IMDb id a zdroje o nich mlčí. */
  async _fillDetail() {
    const item = this._state.item;
    if (!item || !/^tt\d+/.test(String(item.id)) || (item.description && item.poster)) return;
    try {
      const meta = await this._call("detail", {
        id: String(item.id).split(":")[0], type: item.type === "series" ? "series" : "movie" });
      const extra = Object.fromEntries(Object.entries(meta).filter(([k, v]) => v && k !== "title" && k !== "type"));
      this._state.item = { ...item, ...extra };
      this._paint();
    } catch (err) { /* databáze filmů titul nezná — detail se ukáže bez popisu */ }
  }

  /** Titul z databáze filmů: zdroje ho znát nemusí, takže detail nesmí spadnout na chybě. */
  async _openCatalog(item) {
    const st = this._state;
    st.stack.push(st.view);
    await this._guard(async () => {
      const type = item.type === "series" ? "series" : "movie";
      try {  // katalog Cinemety nevrací popis — ten je až v detailu titulu
        const meta = await this._call("detail", { id: item.id, type });
        st.item = { ...item, ...Object.fromEntries(Object.entries(meta).filter(([, v]) => v)) };
      } catch (err) { /* bez popisu se detail zobrazí taky */ }
      if (type === "series") {
        try {
          const res = await this._call("episodes", { id: item.id });
          if ((res.episodes || []).length) {
            st.episodes = res.episodes;
            st.seasons = res.seasons || [];
            st.season = st.seasons.find((s) => s > 0) ?? st.seasons[0] ?? null;
            st.view = "episodes";
            return;
          }
        } catch (err) { /* seriál zatím žádný zdroj nemá */ }
      }
      let streams = [];
      try {
        const res = await this._call("streams", { id: item.id, type });
        streams = res.streams || [];
      } catch (err) { /* stejně tak film */ }
      st.streams = streams;
      st.streamTarget = { id: item.id, type };
      st.view = "streams";
    });
  }

  async _loadStreams(data) {
    this._state.stack.push(this._state.view);
    await this._guard(async () => {
      const res = await this._call("streams", data);
      this._state.streams = res.streams || [];
      this._state.streamTarget = data;
      this._state.torrents = false;   // torrenty se u nového titulu hledají znovu
      this._state.view = "streams";
    });
  }

  _target(stream) {
    const target = { ...this._state.streamTarget };
    if (!target.url) target.stream = stream.index;
    return target;
  }

  async _play(stream) {
    const entityId = await this._choose("player");
    if (!entityId) { if (!this._players().length) this._toast("Není nastavený žádný přehrávač."); return; }
    this._state.player = entityId;
    await this._guard(async () => {
      await this._call("play", { ...this._target(stream), entity_id: entityId }, false);
      this._toast(`Spouštím na ${this._friendly(entityId)}`);
    });
  }

  /** Vybere přehrávač nebo mobil. S jedinou možností se neptá, jinak ukáže
      malý výběr — dva rozbalovací seznamy natrvalo v kartě zabíraly víc místa,
      než kolik se jich reálně používá. */
  /** Společný modal karty. `body` je obsah panelu, `wire` navěsí obsluhu
      a dostane funkci, kterou modal zavře i s výsledkem. */
  _modal(body, wire) {
    return new Promise((resolve) => {
      // Modal patří do stránky, ne do karty: uvnitř dashboardu ho transformace
      // rodičovských prvků vytrhly z prostředka obrazovky do rohu (`fixed` se
      // pak počítá k nim). Proto i vlastní styly místo těch v kartě.
      const wrap = document.createElement("div");
      wrap.className = "nokturno-chooser";
      wrap.innerHTML = `<style>
        .nokturno-chooser { position:fixed !important; top:0 !important; left:0 !important;
          width:100vw; height:100vh; z-index:99; background:rgba(0,0,0,.5); }
        /* polohu panelu počítá karta měřením, CSS ji jen drží */
        .nokturno-chooser .panel { position:fixed !important; top:0 !important; left:0 !important;
          margin:0 !important; background: var(--card-background-color, #1c1c1c);
          color: var(--primary-text-color, #fff); border-radius:14px; padding:8px;
          width:max-content; min-width:250px; max-width:min(90vw,340px);
          box-shadow:0 8px 32px rgba(0,0,0,.5); }
        .nokturno-chooser .phead { display:flex; align-items:center; justify-content:space-between;
          gap:8px; padding:4px 4px 8px 10px; }
        .nokturno-chooser .ptitle { font-size:.8rem; font-weight:600; color: var(--secondary-text-color, #9e9e9e); }
        .nokturno-chooser .pclose { border:none; background:none; color: var(--secondary-text-color, #9e9e9e);
          font-size:1.3rem; line-height:1; cursor:pointer; padding:2px 9px 5px; border-radius:8px; }
        .nokturno-chooser .pclose:hover { background: var(--secondary-background-color, #2a2a2a); }
        .nokturno-chooser .pick { display:flex; align-items:center; gap:8px; width:100%; border:none;
          background:none; color:inherit; font:inherit; text-align:left; padding:10px;
          border-radius:8px; cursor:pointer; }
        .nokturno-chooser .pick:hover { background: var(--secondary-background-color, #2a2a2a); }
        .nokturno-chooser .pick ha-icon { --mdc-icon-size:18px; color: var(--secondary-text-color, #9e9e9e); }
        .nokturno-chooser .ptext { padding:2px 10px 10px; font-size:.9rem; line-height:1.35; }
        .nokturno-chooser .pfoot { display:flex; justify-content:flex-end; gap:8px; padding:4px; }
        .nokturno-chooser .pbtn { border:none; border-radius:8px; padding:8px 14px; font:inherit;
          cursor:pointer; background: var(--secondary-background-color, #2a2a2a); color:inherit; }
        .nokturno-chooser .pbtn.danger { background: var(--error-color, #c0392b); color:#fff; }
      </style>${body}`;
      const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(null); } };
      const close = (value) => {
        window.removeEventListener("keydown", onKey, true);
        wrap.dispatchEvent(new Event("remove-listener"));
        wrap.remove();
        resolve(value);
      };
      window.addEventListener("keydown", onKey, true);
      wrap.addEventListener("click", (e) => { if (e.target === wrap) close(null); });   // klepnutí vedle zavře
      const closer = wrap.querySelector(".pclose");
      if (closer) closer.addEventListener("click", () => close(null));
      wire(wrap, close);
      document.body.appendChild(wrap);
      // Panel patří doprostřed karty, ne obrazovky — modal se týká toho, na co
      // se právě kleplo. Polohu počítá měření, ne CSS: modal visí v `body`,
      // kde o kartě nic neví, a transformace předků umí podstrčit jiný
      // vztažný bod. Do okna se zarovná, aby nevyčníval ven.
      const panel = wrap.querySelector(".panel");
      const centre = () => {
        panel.style.transform = "none";
        const box = panel.getBoundingClientRect();     // pozice bez posunu = vztažný bod
        const card = this.getBoundingClientRect();
        const pad = 8;
        const fit = (start, size, room) => Math.max(pad, Math.min(room - size - pad, start));
        const x = fit(card.left + (card.width - box.width) / 2, box.width, window.innerWidth);
        const y = fit(card.top + (card.height - box.height) / 2, box.height, window.innerHeight);
        panel.style.transform = `translate(${Math.round(x - box.left)}px, ${Math.round(y - box.top)}px)`;
      };
      requestAnimationFrame(centre);
      const follow = () => requestAnimationFrame(centre);
      window.addEventListener("resize", follow);
      window.addEventListener("scroll", follow, true);
      wrap.addEventListener("remove-listener", () => {
        window.removeEventListener("resize", follow);
        window.removeEventListener("scroll", follow, true);
      });
    });
  }

  /** Vybere přehrávač nebo mobil. S jedinou možností se neptá, jinak ukáže
      malý výběr — dva rozbalovací seznamy natrvalo v kartě zabíraly víc místa,
      než kolik se jich reálně používá. */
  _choose(kind) {
    const list = kind === "phone" ? this._phones() : this._players();
    const name = (v) => (kind === "phone" ? this._phoneName(v) : this._friendly(v));
    if (!list.length) return Promise.resolve(null);
    if (list.length === 1) return Promise.resolve(list[0]);
    return this._modal(`<div class="panel">
      <div class="phead">
        <span class="ptitle">${kind === "phone" ? "Do kterého mobilu?" : "Kde přehrát?"}</span>
        <button class="pclose" title="Zavřít">×</button>
      </div>
      ${list.map((v, i) => `<button class="pick" data-pickone="${i}">
        <ha-icon icon="${kind === "phone" ? "mdi:cellphone" : "mdi:cast"}"></ha-icon>
        <span>${this._esc(name(v))}</span></button>`).join("")}
    </div>`, (wrap, close) => {
      wrap.querySelectorAll("[data-pickone]").forEach((el) =>
        el.addEventListener("click", () => close(list[+el.dataset.pickone])));
    });
  }

  /** Potvrzení vlastním modalem — `window.confirm` prohlížeč po pár dialozích
      potlačí a mazání pak tiše nedělá nic. */
  _confirm(title, text, label = "Smazat") {
    return this._modal(`<div class="panel">
      <div class="phead"><span class="ptitle">${this._esc(title)}</span>
        <button class="pclose" title="Zavřít">×</button></div>
      <div class="ptext">${this._esc(text)}</div>
      <div class="pfoot">
        <button class="pbtn" data-no="1">Zpět</button>
        <button class="pbtn danger" data-yes="1">${this._esc(label)}</button>
      </div>
    </div>`, (wrap, close) => {
      wrap.querySelector("[data-no]").addEventListener("click", () => close(null));
      wrap.querySelector("[data-yes]").addEventListener("click", () => close(true));
    }).then((value) => value === true);
  }

  async _download(stream) {
    await this._guard(async () => {
      const res = await this._call("download", this._target(stream));
      this._toast(`Stahuji do ${res.path || "úložiště"}`);
    });
  }

  /** Prowlarr nastavený? Senzor stahování to hlásí v atributu `sources`. */
  _hasTorrents() {
    const sensor = this._hass && this._hass.states[this._config.downloads];
    return !!(sensor && sensor.attributes.sources && sensor.attributes.sources.torrent);
  }

  /** Torrenty se hledají až na vyžádání — trackery odpovídají v řádu sekund
      a u titulu, na který stream je, by to jen zdržovalo otevření detailu. */
  async _findTorrents() {
    this._state.finding = true;   // vlastní příznak: jinak by tlačítko hlásilo hledání při každé akci
    await this._guard(async () => {
      const res = await this._call("torrents", { ...this._state.streamTarget });
      // torrenty patří nad streamy — kvůli nim se hledalo, tak ať jsou hned vidět
      this._state.streams = (res.streams || []).concat(this._state.streams);
      this._state.torrents = true;
      if (!(res.streams || []).length) this._toast("Na trackerech nic nenašel");
    });
    this._state.finding = false;
    this._paint();
  }

  async _downloadTorrent(stream) {
    await this._guard(async () => {
      await this._call("download_torrent", { url: stream.url, name: stream.file || "" }, false);
      this._toast("Torrent zařazen do stahování");
    });
  }

  async _toPhone(stream) {
    const target = await this._choose("phone");
    if (!target) { if (!this._phones().length) this._toast("Nenašel jsem žádný mobil s aplikací Home Assistant."); return; }
    this._state.phone = target;
    await this._guard(async () => {
      await this._call("send_link", {
        ...this._target(stream),
        notify_service: target,
        name: `${this._state.title || ""} — ${stream.label}`.trim(),
      }, false);
      this._toast(`Odkaz odeslán: ${this._phoneName(target)}`);
    });
  }

  /** Schránka: clipboard API běží jen na https, přes http zbývá execCommand. */
  _copy(text) {
    try {
      if (window.isSecureContext && navigator.clipboard) {
        navigator.clipboard.writeText(text);
        return true;
      }
    } catch (err) { /* v iframe bez oprávnění spadne — zkusíme starou cestu */ }
    try {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.cssText = "position:fixed;top:0;left:0;opacity:0";
      document.body.appendChild(area);
      area.select();
      area.setSelectionRange(0, text.length);
      const ok = document.execCommand("copy");
      area.remove();
      return ok;
    } catch (err) {
      return false;
    }
  }

  async _openLink(stream) {
    await this._guard(async () => {
      const res = await this._call("resolve", this._target(stream));
      if (!res.url) return;
      if (this._copy(res.url)) {
        this._toast("Odkaz zkopírován — vlož ho do VLC nebo prohlížeče");
      } else {
        window.prompt("Zkopíruj odkaz (Ctrl+C):", res.url);
      }
    });
  }

  /** Rozkoukané: otevře streamy titulu v kartě (id a typ nese plugin odkaz z Kodi). */
  async _openContinue(item) {
    const query = (item.file || "").split("?")[1] || "";
    const params = new URLSearchParams(query);
    const id = params.get("id");
    const type = params.get("type") || (item.series ? "series" : "movie");
    this._state.stack.push("search");
    this._state.descOpen = false;
    this._state.episode = null;
    this._state.title = item.label || item.title;
    if (id) {
      this._state.item = {
        id, type, title: item.title || item.label, year: item.year,
        poster: item.thumbnail, background: item.fanart, description: item.plot,
        alt: params.get("alt") || null,
      };
      return this._loadStreams({
        id, type,
        series: params.get("series") || undefined,
        alt: params.get("alt") || undefined,
      });
    }
    // starší doplněk odkaz bez id nemá — dohledáme titul podle názvu
    return this._guard(async () => {
      const res = await this._call("search", { query: item.title || item.label, type, limit: 1 });
      const found = (res.results || [])[0];
      if (!found) { this._toast("Titul se nepodařilo najít."); this._state.stack.pop(); return; }
      this._state.item = found;
      const streams = await this._call("streams", { id: found.id, type, alt: found.alt });
      this._state.streams = streams.streams || [];
      this._state.streamTarget = { id: found.id, type, alt: found.alt };
      this._state.view = "streams";
    });
  }

  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  // --- cíle -----------------------------------------------------------------

  _players() {
    if (this._config.players.length) return this._config.players;
    return Object.keys((this._hass && this._hass.states) || {})
      .filter((id) => id.startsWith("media_player."));
  }

  /** Telefony i s vlastníkem — seznam hlásí integrace v atributu senzoru. */
  _targets() {
    const sensor = this._hass && this._hass.states[this._config.downloads];
    return (sensor && sensor.attributes.notify_targets) || [];
  }

  _phones() {
    const source = this._config.phones.length ? this._config.phones : this._targets().map((t) => t.service);
    const seen = new Set();
    return source.filter((service) => {
      const key = this._short(service);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  _short(service) {
    return String(service).replace(/^notify\./, "").replace(/^mobile_app_/, "");
  }

  /** Popisek mobilu: „Martin · SM-S921B“. */
  _phoneName(service) {
    const short = this._short(service);
    const target = this._targets().find((t) => this._short(t.service) === short);
    const device = (target && target.device) || short.toUpperCase().replace(/_/g, "-");
    return target && target.user ? `${target.user} · ${device}` : device;
  }

  _friendly(entityId) {
    const state = this._hass && this._hass.states[entityId];
    return (state && state.attributes.friendly_name) || entityId;
  }

  // --- vykreslení -----------------------------------------------------------

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 12px 14px 16px; container-type: inline-size; }
        .head { display:flex; align-items:center; gap:8px; margin-bottom:10px; }
        .head[hidden] { display:none; }
        .head h2 { margin:0; font-size:1.15rem; font-weight:500; flex:1; }
        ha-card { position:relative; }
        /* hledání pod sebou přes celou šířku karty */
        .bar { display:grid; grid-template-columns: 1fr; gap:8px; align-items:center; }
        .bar[hidden] { display:none; }  /* jinak by display:grid přebil atribut hidden */
        ha-control-button#go { width:100%; }
        ha-control-button#go ha-icon { --mdc-icon-size:20px; margin-right:4px; vertical-align:-4px; }
        ha-control-select { --control-select-thickness:40px; }
        /* prvek má vlastní display, atribut hidden by se bez tohohle neprojevil */
        ha-control-select[hidden] { display:none; }
        ha-control-select::part(label), ha-control-select { white-space:nowrap; }
        /* detail: [zpět][název] a pod tím dva výběry vedle sebe přes celou šířku */
        .bar.detail { display:block; margin-top:10px; }
        .titlerow { display:flex; align-items:center; gap:4px; }
        .titlerow .name { flex:1; min-width:0; font-size:1.05rem; }
        .picks { display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:8px; margin-top:8px; }
        .picks ha-select { width:100%; }
        ha-control-select-menu { width:100%; }
        .name { font-weight:500; }
        .grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap:10px; margin-top:12px; align-items:start; }
        .grid.files { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
        .poster { cursor:pointer; text-align:left; background:none; border:none; padding:0; color:inherit; font:inherit; display:flex; flex-direction:column; }
        /* pozor: lazy loading obrázků tu nefunguje - dlaždice pod okrajem okna se v shadow DOM nenačtou */
        .thumb { position:relative; display:flex; align-items:center; justify-content:center; width:100%;
                 aspect-ratio:2/3; border-radius:12px; background: var(--secondary-background-color);
                 color: var(--secondary-text-color); overflow:hidden; }
        .grid.files .thumb { aspect-ratio:16/9; }
        .thumb img { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
        /* než se načtou streamy, je přes obrázek vidět, na co se kliklo */
        .mask { position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
                background: rgba(0,0,0,.55); color:#fff; border-radius:12px; }
        .mask ha-icon { --mdc-icon-size:34px; }
        /* dva řádky pro každý název — jinak si delší názvy posunou sousední dlaždice */
        .poster .t { font-size:.8rem; margin-top:5px; line-height:1.25; height:2.5em; overflow:hidden;
                     display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
        .poster .y { font-size:.72rem; color: var(--secondary-text-color); }
        .poster .year { color: var(--secondary-text-color); }
        .hero { margin-top:10px; }
        .heroart { position:relative; display:block; }
        .hero img { width:100%; aspect-ratio:16/9; object-fit:cover; border-radius:12px; display:block;
                    background: var(--secondary-background-color); }
        .desc { margin-top:8px; font-size:.85rem; line-height:1.35; color: var(--secondary-text-color); cursor:pointer;
                display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
        .desc.open { -webkit-line-clamp:unset; display:block; }
        /* výběr ve vzhledu HA: podklad s popiskem, uvnitř nativní select */
        .pick { display:flex; flex-direction:column; justify-content:center; gap:1px; padding:5px 10px;
                background: var(--secondary-background-color); border-radius:12px; min-height:48px; cursor:pointer; }
        .pick > span { font-size:.7rem; color: var(--secondary-text-color); }
        .pick select { border:none; background:none; color: var(--primary-text-color); font:inherit; font-size:.9rem;
                       padding:0; margin:0; width:100%; cursor:pointer; outline:none; appearance:none; }
        /* rozbalený seznam kreslí prohlížeč — bez těchhle barev je v tmavém motivu bílý na bílém */
        .pick option { background: var(--card-background-color, #1c1c1c); color: var(--primary-text-color); }
        /* stream má tři řádky pod sebou: štítek, celý název souboru, tlačítka */
        .stream, .stream.stacked { display:grid; grid-template-columns:minmax(0, 1fr);
                                   grid-template-areas:"tag" "label" "icons";
                                   column-gap:8px; row-gap:2px; padding:8px 0;
                                   border-bottom:1px solid var(--divider-color); }
        .stream .tag { grid-area:tag; justify-self:start; }
        /* celý název souboru na plnou šířku — tlačítka mu už nekrátí řádek */
        .stream .label { grid-area:label; font-size:.9rem; overflow-wrap:anywhere;
                         display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
        .stream .icons { grid-area:icons; display:flex; justify-content:flex-end; gap:2px; margin-top:2px; }
        /* tlačítka streamu ve vzhledu HA: čtyři široká vedle sebe přes celou šířku */
        .icons.wide .span4 { grid-column: 1 / -1; }
        .icons.wide { display:grid; grid-template-columns:repeat(4, 1fr); gap:6px; margin-top:6px; }
        .icons.wide ha-control-button { width:100%; height:40px; --control-button-border-radius:12px; }
        .icons.wide ha-icon { --mdc-icon-size:20px; }
        .tag { font-size:.7rem; font-weight:600; padding:2px 6px; border-radius:6px; color:#fff; white-space:nowrap;
               display:inline-flex; align-items:center; gap:3px; }
        /* zeměkoule = odkaz vede přímo z WebShare, takže hraje i mimo domácí síť */
        .tag .ext { --mdc-icon-size:13px; opacity:.9; }
        .tag ha-icon.ext { --mdc-icon-size:12px; }
        /* v úvodních sekcích je název krátký, štítek se vejde vedle něj */
        .stream.stacked { grid-template-columns:auto minmax(0, 1fr) auto;
                          grid-template-areas:"tag label icons"; align-items:center; row-gap:0; }
        .stream.stacked .icons { align-self:center; margin-top:0; }
        .stream.stacked .label { -webkit-line-clamp:2; }
        /* u sledovaných seriálů patří stav ("ke sledování 1x10, odvysíláno 2x10")
           na vlastní řádek pod název — proto o řádek vyšší clamp než u ostatních */
        .stream.stacked .label--meta { -webkit-line-clamp:3; }
        .stream .label--meta .muted { display:block; }
        @container (max-width: 430px) {
          .stream.stacked { grid-template-columns:minmax(0, 1fr) auto;
                            grid-template-areas:"tag icons" "label icons"; row-gap:2px; }
        }
        .icons { display:flex; }
        .watch { margin-left:auto; }
        /* štítky s posledními dotazy a přepínači nad výsledky */
        .chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
        .chip { background: var(--secondary-background-color); color: var(--primary-text-color); border:none;
                border-radius:14px; padding:5px 11px; font:inherit; font-size:.8rem; cursor:pointer;
                display:inline-flex; align-items:center; gap:4px; }
        .chip.x { color: var(--secondary-text-color); }
        .section { margin-top:14px; font-weight:500; display:flex; align-items:center; gap:6px; }
        .section ha-icon { --mdc-icon-size:18px; }
        /* rozkoukané: dlaždice na šířku, ať je poznat záběr z filmu */
        .cont { display:grid; grid-template-columns:repeat(auto-fill, minmax(150px, 1fr)); gap:10px; margin-top:8px; }
        .cont .poster .thumb { aspect-ratio:16/9; }
        .where { position:absolute; left:6px; bottom:6px; font-size:.68rem; font-weight:600; padding:2px 6px;
                 border-radius:6px; background:rgba(0,0,0,.65); color:#fff; }
        .icons ha-icon-button { --mdc-icon-button-size:40px; --mdc-icon-size:20px; }
        .legend { margin-top:8px; font-size:.75rem; color: var(--secondary-text-color); display:flex;
                  align-items:center; gap:4px; }
        .legend ha-icon { --mdc-icon-size:14px; }
        .muted { color: var(--secondary-text-color); font-size:.85rem; }
        .muted.empty { margin:12px 2px 4px; }
        .err { color: var(--error-color); font-size:.85rem; margin-top:8px; }
        .ep { display:flex; gap:8px; align-items:center; padding:9px 0; border-bottom:1px solid var(--divider-color); cursor:pointer; }
        .ep .n { color: var(--secondary-text-color); min-width:46px; font-variant-numeric: tabular-nums; }
        .dl { margin-top:4px; }
        .dlrow { display:flex; justify-content:space-between; gap:8px; align-items:center; }
        .dljob { margin:6px 0 10px; }
        /* druhý řádek s rychlostí a časem — menší písmo, tlačítko křížku vpravo */
        .dlinfo { margin-top:2px; font-size:.78rem; }
        .dlinfo ha-icon-button { --mdc-icon-button-size:28px; --mdc-icon-size:16px; }
        /* oddělovače patří mezi položky, ne nad nadpis sekce */
        .file { display:flex; align-items:center; gap:8px; padding:4px 0; border-bottom:1px solid var(--divider-color); }
        .file:last-child { border-bottom:none; }
        .file .label { flex:1; min-width:0; font-size:.9rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .file .label { flex:1; font-size:.85rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .prog { height:4px; border-radius:2px; background: var(--divider-color); overflow:hidden; margin-top:3px; }
        .prog > div { height:100%; background: var(--primary-color); }
        .spin { animation: sp 1s linear infinite; display:inline-block; }
        @keyframes sp { to { transform: rotate(360deg); } }
      </style>
      <ha-card>
        <div class="head"${this._config.show_header ? "" : " hidden"}>
          <ha-icon icon="mdi:movie-search"></ha-icon>
          <h2>${this._esc(this._config.title)}</h2>
        </div>
        <div class="bar" id="search">
          <ha-input id="q" placeholder="Název filmu nebo seriálu" with-clear></ha-input>
          <ha-control-button id="go" title="Hledat ve WebShare, Sosáči a Luně"><ha-icon icon="mdi:magnify"></ha-icon> Hledat</ha-control-button>
          <ha-control-select id="type"></ha-control-select>
        </div>
        <div id="body"></div>
        <div id="downloads" class="dl" hidden></div>
      </ha-card>`;
    this._root = this.shadowRoot;
    this._input = this._root.querySelector("#q");
    this._input.addEventListener("keydown", (e) => { if (e.key === "Enter") this._search(); });
    ["input", "change"].forEach((ev) => this._input.addEventListener(ev, (e) => {
      this._state.query = (e.target && e.target.value) || this._readInput();
    }));
    this._root.querySelector("#go").addEventListener("click", () => this._search());
    this._root.querySelector("#body").addEventListener("click", (e) => this._onClick(e));
    const kind = this._root.querySelector("#type");
    kind.options = KINDS;
    kind.value = this._state.type;
    kind.addEventListener("value-changed", (e) => {
      const st = this._state;
      st.type = (e.detail && e.detail.value) || kind.value;
      if (st.byType && st.view === "results") { st.results = st.byType[st.type] || []; this._paint(); }
    });
    this._paint();
  }

  _paint() {
    if (!this._root) return;
    const go = this._root.querySelector("#go");
    // kolečko se točí přímo v tlačítku Hledat, ať je vidět, že dotaz běží
    // kolečko běží při každém načítání, ne jen při hledání — je to jediné místo, kde je vidět
    go.toggleAttribute("disabled", !!this._state.busy);
    go.querySelector("ha-icon").className = this._state.busy ? "spin" : "";
    go.querySelector("ha-icon").setAttribute("icon", this._state.busy ? "mdi:loading" : "mdi:magnify");
    const body = this._root.querySelector("#body");
    const st = this._state;
    const kind = this._root.querySelector("#type");
    if (kind && kind.value !== st.type) kind.value = st.type;
    // přepínač dává smysl jen tehdy, když dotaz našel filmy i seriály
    if (kind) kind.hidden = !(st.view === "results" && st.bothTypes);
    // v detailu (epizody, streamy) je hledání jen na překážku
    this._root.querySelector("#search").hidden = st.view === "streams" || st.view === "episodes";
    let html = "";
    if (st.view === "results") html = this._results();
    else if (st.view === "episodes") html = this._episodes();
    else if (st.view === "streams") html = this._streams();
    else html = this._home();
    if (st.error) html += `<div class="err">${this._esc(st.error)}</div>`;
    body.innerHTML = html;
    this._wirePicks(body);
    this._applyTooltips(body);
    this._retryImages(body);
    this._renderDownloads();
  }

  /** ha-select se plní z JS, ne z HTML — a je potřeba to udělat všude, kde vznikne. */
  _wirePicks(root) {
    const st = this._state;
    root.querySelectorAll("[data-pick]").forEach((el) => {
      // ha-select hodnotu sám nemění — pošle jen `selected` s novou hodnotou a čeká, až ji nastavíme
      const apply = (event) => {
        const id = el.dataset.pick;
        const value = (event && event.detail && event.detail.value) ?? el.value;
        if (value == null || value === "") return;
        if (el.value !== value) el.value = value;
        if (id === "season") { st.season = +value; this._paint(); }
        else if (id === "player" || id === "fplayer") { st.player = value; }
        else if (id === "phone" || id === "fphone") { st.phone = value; }
      };
      // nativní select hlásí „change“, ha-select „selected“ (mwc) i „closed“
      el.addEventListener("change", apply);
      el.addEventListener("selected", apply);
      if (el.tagName.toLowerCase() === "ha-select") {
        const conf = (this._pickData || {})[el.dataset.pick];
        if (conf) {
          el.label = conf.label;
          el.options = conf.options;
          el.value = conf.value;
        }
        el.addEventListener("value-changed", apply);
        el.addEventListener("selected", apply);
      }
    });
  }

  /** Úvodní obrazovka: poslední dotazy, rozkoukané z Kodi, sledované seriály. */
  _home() {
    const st = this._state;
    const sensor = this._hass && this._hass.states[this._config.downloads];
    const history = (sensor && sensor.attributes.search_history) || [];
    let html = history.length
      ? `<div class="chips">${history.map((q, i) => `<button class="chip" data-hist="${i}" title="Zopakovat hledání „${this._esc(q)}“">${this._esc(q)}</button>`).join("")}
         <button class="chip x" data-histclear="1" title="Smazat historii">×</button></div>`
      : `<div class="muted" style="margin-top:10px">Zadej název — hledá se ve WebShare, Sosáči i Luně naráz.</div>`;
    if (st.continueItems === null) this._loadContinue();
    const cont = st.continueItems || [];
    const manyKodi = new Set(cont.map((c) => c.entity_id)).size > 1;
    if (cont.length) {
      html += `<div class="section"><ha-icon icon="mdi:play-circle-outline"></ha-icon> Pokračovat ve sledování</div>
        <div class="cont">${cont.map((c, i) => `
          <button class="poster" data-cont="${i}" title="${this._esc(c.plot)}">
            <span class="thumb"><ha-icon icon="mdi:filmstrip"></ha-icon>
              ${c.fanart || c.thumbnail ? `<img src="${this._esc(c.fanart || c.thumbnail)}" referrerpolicy="no-referrer" />` : ""}
              ${manyKodi ? `<span class="where">${this._esc(c.player)}</span>` : ""}
              ${st.busy && st.loading === `cont:${i}` ? `<span class="mask"><ha-icon class="spin" icon="mdi:loading"></ha-icon></span>` : ""}
            </span>
            <div class="t">${this._esc(c.label)}</div>
          </button>`).join("")}</div>`;
    }
    const trakt = this._traktList();
    if (trakt.length) {
      html += `<div class="section"><ha-icon icon="mdi:bookmark-check-outline"></ha-icon> K zhlédnutí</div>
        <div>${trakt.slice(0, 12).map((t, i) => `
          <div class="stream stacked" data-trakt="${i}" style="cursor:pointer" title="${t.streams ? `Otevřít streamy — ${t.streams} k dispozici` : "Zatím žádný stream; hlídám a dám vědět"}">
            <span class="tag" style="background:${t.streams ? "#2e8b57" : "#777"}">
              <ha-icon icon="${t.streams ? "mdi:play-circle-outline" : (t.pending ? "mdi:radar" : "mdi:clock-outline")}" class="ext"></ha-icon>
              ${t.streams ? (t.torrent ? "jen torrent" : "lze pustit") : (t.pending ? "hlídám" : "zatím ne")}</span>
            <span class="label">${this._esc(t.title)}${t.year ? ` <span class="muted">(${t.year})</span>` : ""}${
              t.streams ? ` <span class="muted">· ${t.streams} streamů</span>` : ""}</span>
          </div>`).join("")}</div>`;
    }
    const series = this._watchlist();
    if (series.length) {
      html += `<div class="section"><ha-icon icon="mdi:television-play"></ha-icon> Sledované seriály</div>
        <div>${series.map((w, i) => `
          <div class="stream stacked">
            <span class="tag" style="background:${w.new ? "#2e8b57" : "#777"}">${w.new ? "nový díl" : "sleduji"}</span>
            <span class="label${w.new ? "" : " label--meta"}">${this._esc(w.title)}${w.new
              ? ` — ${w.new.season}x${String(w.new.episode).padStart(2, "0")} ${this._esc(w.new.title)}`
              : `<span class="muted">${w.available
                  ? `ke sledování ${w.available.season}x${String(w.available.episode).padStart(2, "0")}${w.available.torrent ? " (jen torrent)" : ""}`
                  : "zatím bez streamu"}${w.latest && (!w.available || w.latest.episode !== w.available.episode || w.latest.season !== w.available.season)
                  ? `, odvysíláno ${w.latest.season}x${String(w.latest.episode).padStart(2, "0")}` : ""}</span>`}</span>
            <span class="icons">
              ${w.new ? `<ha-icon-button data-wseen="${i}" title="Označit nový díl jako viděný"><ha-icon icon="mdi:check"></ha-icon></ha-icon-button>` : ""}
              <ha-icon-button data-wopen="${i}" title="Otevřít"><ha-icon icon="mdi:folder-play-outline"></ha-icon></ha-icon-button>
              <ha-icon-button data-wremove="${i}" title="Přestat sledovat"><ha-icon icon="mdi:eye-off-outline"></ha-icon></ha-icon-button>
            </span>
          </div>`).join("")}</div>`;
    }
    return html;
  }

  _isWatched(id) { return this._watchlist().some((w) => w.id === id); }

  async _toggleWatch() {
    const item = this._state.item;
    const watching = this._isWatched(item.id);
    // ikona se přepne hned, senzor to potvrdí o chvíli později
    this._watchOverride = this._watchOverride || {};
    this._watchOverride[item.id] = watching ? false : { id: item.id, title: item.title, alt: item.alt, poster: item.poster };
    await this._guard(async () => {
      await this._call("watch_series", watching
        ? { id: item.id, remove: true }
        : { id: item.id, title: item.title, alt: item.alt || undefined, poster: item.poster || undefined }, false);
      this._toast(watching ? "Seriál už nesleduji" : "Nové díly budu hlásit");
    });
  }

  /** Seznam k zhlédnutí z Traktu (ze senzoru „K zhlédnutí"). */
  _traktList() {
    return (this._sensorAttr("items") || []).filter((i) => i && i.id);
  }

  _isWanted(id) {
    const over = this._wantOverride || {};
    if (id in over) return over[id] !== false;
    return this._traktList().some((t) => t.id === id);
  }

  /** Co si záložka uloží. Otevřený díl se hlídá jako díl — uživatel si ho
      vybral, hlídat kvůli němu celý seriál by mu řeklo něco jiného. */
  _wantTarget() {
    const st = this._state;
    const item = st.item;
    if (!item) return null;
    const ep = st.episode;
    if (ep && item.type === "series") {
      const num = `${ep.season}x${String(ep.episode).padStart(2, "0")}`;
      return { id: ep.id, type: "series", series: item.id,
               title: `${item.title} — ${num}${ep.title ? ` ${ep.title}` : ""}`,
               year: item.year, alt: item.alt, poster: item.poster };
    }
    return { id: item.id, type: item.type === "series" ? "series" : "movie",
             title: item.title, year: item.year, alt: item.alt, poster: item.poster };
  }

  /** Seznam „k zhlédnutí" — vlastní i z Traktu; kontroluje se denně, jestli už má stream. */
  async _toggleWant() {
    const target = this._wantTarget();
    if (!target) return;
    const wanted = this._isWanted(target.id);
    this._wantOverride = this._wantOverride || {};
    this._wantOverride[target.id] = wanted ? false : true;
    this._paint();
    await this._guard(async () => {
      await this._call("want_to_watch", wanted
        ? { id: target.id, remove: true }
        : { id: target.id, type: target.type, title: target.title, series: target.series || undefined,
            year: target.year || undefined, alt: target.alt || undefined, poster: target.poster || undefined }, false);
      this._toast(wanted ? "Odebráno ze seznamu" : "Přidáno — dám vědět, až bude ke sledování");
    });
  }

  /** Hlídat titul, který zatím žádný zdroj nemá — stačí název z vyhledávacího pole. */
  /** Databáze filmů (IMDb/TMDB) — najde i tituly, které zatím žádný zdroj nemá. */
  async _searchCatalog() {
    const query = (this._readInput() || this._state.query || "").trim();
    if (!query) {
      // „+“ u seznamu k zhlédnutí s prázdným polem: rovnou nachystat hledání v databázi
      this._state.pendingCatalog = true;
      this._toast("Napiš název — hledat budu rovnou v databázi filmů.");
      if (this._input && this._input.focus) this._input.focus();
      return;
    }
    this._state.searching = true;
    await this._guard(async () => {
      const st = this._state;
      const [movies, series] = await Promise.all([
        this._call("search", { query, type: "catalog", limit: 12 }),
        this._call("search", { query, type: "catalog_series", limit: 12 }),
      ]);
      st.byType = { movie: movies.results || [], series: series.results || [] };
      this._pickType();
      st.catalog = true;
      st.view = "results";
      if (!st.results.length) this._toast("V databázi filmů nic takového není.");
    });
  }

  async _wantQuery() {
    const query = (this._state.query || this._readInput() || "").trim();
    if (!query) { this._toast("Napiš nejdřív název do pole pro hledání."); return; }
    this._state.searching = true;
    await this._guard(async () => {
      await this._call("want_to_watch", { query, type: this._state.type === "series" ? "series" : "movie" }, false);
      this._toast(`Hlídám „${query}" — dám vědět, až bude ke sledování`);
      this._state.view = "search";
    });
  }

  _watchlist() {
    const list = [...(this._sensorAttr("series") || [])];
    const over = this._watchOverride || {};
    const kept = list.filter((w) => over[w.id] !== false).map((w) => (over[w.id] ? { ...w, ...over[w.id] } : w));
    Object.values(over).forEach((w) => { if (w && !kept.some((k) => k.id === w.id)) kept.push(w); });
    return kept;
  }

  async _loadContinue() {
    this._state.continueItems = [];
    try {
      const res = await this._call("continue_watching", {});
      this._state.continueItems = res.items || [];
      if (this._state.view === "search") this._paint();
    } catch (err) { /* Kodi vypnuté — sekce se prostě neukáže */ }
  }

  _results() {
    const st = this._state;
    // databáze filmů je po ruce vždycky — zdroje můžou najít něco jiného, než uživatel hledal
    const home = `<div class="chips">
      <button class="chip" data-back="search" title="Zpět na úvodní obrazovku"><ha-icon icon="mdi:home-outline" style="--mdc-icon-size:14px"></ha-icon> Úvod</button>
      ${st.catalog
        ? `<button class="chip" data-research="1" title="Zpět na výsledky z WebShare, Sosáče a Luny"><ha-icon icon="mdi:magnify" style="--mdc-icon-size:14px"></ha-icon> Zpět k výsledkům ze zdrojů</button>`
        : `<button class="chip" data-catalog="1" title="Hledat v databázi filmů (IMDb/TMDB) — najde i tituly, které zdroje nemají"><ha-icon icon="mdi:database-search-outline" style="--mdc-icon-size:14px"></ha-icon> Hledat v databázi filmů</button>`}
    </div>`;
    if (!st.results.length) return home + `<div class="muted" style="margin-top:10px">${st.catalog
      ? "V databázi filmů nic takového není."
      : "Ve zdrojích nic nenalezeno — zkus databázi filmů."}</div>`;
    const files = st.results.every((r) => r.type === "file");
    const hint = st.catalog
      ? `<div class="muted" style="margin-top:8px">Z databáze filmů — klepnutím otevřeš detail; záložkou v něm si titul uložíš do seznamu k zhlédnutí.</div>` : "";
    return home + hint + `<div class="grid${files ? " files" : ""}">` + st.results.map((r, i) => `
      <button class="poster" data-open="${i}" title="${this._esc(
        [r.title + (r.year ? ` (${r.year})` : ""), r.description].filter(Boolean).join("\n"))}">
        <span class="thumb">
          <ha-icon icon="mdi:filmstrip"></ha-icon>
          ${r.poster ? `<img src="${this._esc(r.poster)}" referrerpolicy="no-referrer" />` : ""}
          ${st.busy && st.loading === `res:${i}` ? `<span class="mask"><ha-icon class="spin" icon="mdi:loading"></ha-icon></span>` : ""}
        </span>
        <div class="t">${this._esc(r.title)}${r.year ? ` <span class="year">(${r.year})</span>` : ""}</div>
        ${r.size ? `<div class="y">${this._esc(r.size)}</div>` : ""}
      </button>`).join("") + `</div>`;
  }

  _episodes() {
    const st = this._state;
    const list = st.episodes.filter((e) => st.season === null || e.season === st.season);
    return this._hero() + `
      <div class="bar detail">
        <div class="titlerow">
          <ha-icon-button data-back="back" title="Zpět"><ha-icon icon="mdi:arrow-left"></ha-icon></ha-icon-button>
          <span class="name">${this._esc(st.item.title)}${st.item.year ? ` <span class="muted">(${st.item.year})</span>` : ""}</span>
          <ha-icon-button data-watch="1" title="${this._isWatched(st.item.id) ? "Přestat sledovat" : "Sledovat nové díly"}">
            <ha-icon icon="${this._isWatched(st.item.id) ? "mdi:eye-check" : "mdi:eye-plus-outline"}"></ha-icon>
          </ha-icon-button>
        </div>
        <span class="picks">
          ${this._pick("season", "Sezóna", st.seasons.map((n) => ({ value: String(n), label: n === 0 ? "Speciály" : "Sezóna " + n })), String(st.season))}
        </span>
      </div>
      <div>${list.map((e, i) => `
        <div class="ep" data-ep="${i}" title="Zobrazit streamy epizody">
          <span class="n">${e.season}x${String(e.episode).padStart(2, "0")}</span>
          <span>${this._esc(e.title)}</span>
        </div>`).join("")}</div>`;
  }

  _streams() {
    const st = this._state;
    const players = this._players();
    const phones = this._phones();
    // v konfiguraci bývá `notify.sm_s921b`, služba se ale jmenuje `notify.mobile_app_sm_s921b`
    if (players.length) st.player = players.includes(st.player) ? st.player : players[0];
    if (phones.length) st.phone = phones.find((p) => this._short(p) === this._short(st.phone)) || phones[0];
    const head = this._hero() + `
      <div class="bar detail">
        <div class="titlerow">
          <ha-icon-button data-back="back" title="Zpět"><ha-icon icon="mdi:arrow-left"></ha-icon></ha-icon-button>
          <span class="name">${this._esc(st.title)}${st.item && st.item.year && !st.episode
            && !String(st.title).includes(String(st.item.year)) ? ` <span class="muted">(${st.item.year})</span>` : ""}</span>
          ${st.item ? (() => {
            const saved = this._isWanted((this._wantTarget() || {}).id);
            return `<ha-icon-button data-want="1" title="${saved ? "Odebrat ze seznamu k zhlédnutí" : "Přidat do seznamu k zhlédnutí"}">
            <ha-icon icon="${saved ? "mdi:bookmark-check" : "mdi:bookmark-plus-outline"}"></ha-icon>
          </ha-icon-button>`; })() : ""}
        </div>
      </div>`;
    // torrenty jsou poslední možnost, ale tlačítko patří nahoru k ostatnímu ovládání.
    // Hledání trvá pár sekund, takže se točí kolečko i v tlačítku, nejen přes fotku.
    const torrentBtn = st.torrents || !this._hasTorrents() ? "" : `<div class="chips" style="margin:8px 0 2px">
      <button class="chip" data-findtorrents="1"${st.busy ? " disabled" : ""} title="Prohledat torrentové trackery přes Prowlarr — trvá pár sekund, proto se hledá až na vyžádání">
        <ha-icon class="${st.finding ? "spin" : ""}" icon="${st.finding ? "mdi:loading" : "mdi:magnify-scan"}" style="--mdc-icon-size:14px"></ha-icon> ${st.finding ? "Hledám torrenty…" : "Hledat torrenty"}
      </button></div>`;
    if (!st.streams.length) return head + torrentBtn + `<div class="muted empty">Pro tento titul se nenašel žádný stream.${
      st.item && st.item.source === "katalog" ? " Ulož si ho záložkou nahoře a dám vědět, jakmile se objeví." : ""}</div>`;
    const legend = st.streams.some((s) => s.direct)
      ? `<div class="legend"><ha-icon icon="mdi:earth"></ha-icon> = hraje i mimo domácí síť</div>` : "";
    return head + torrentBtn + legend + `<div>${st.streams.map((s, i) => `
      <div class="stream" title="${this._esc(this._streamTitle(s))}">
        <span class="tag" style="background:${SOURCE_COLORS[s.source] || "#777"}">${s.source || "?"}${
          s.direct ? `<ha-icon class="ext" icon="mdi:earth" title="Hraje i mimo domácí síť"></ha-icon>` : ""}</span>
        <span class="label">${this._esc(s.label.replace(s.source + "  ·  ", ""))}</span>
        <span class="icons wide">${s.kind === "torrent"
          // torrent není odkaz na video: nedá se přehrát ani poslat do mobilu,
          // nejdřív ho musí stáhnout torrentový klient
          ? `<ha-control-button class="span4" data-torrent="${i}" title="Zařadit ke stažení do qBittorrentu — až se soubor stáhne, objeví se mezi staženými"><ha-icon icon="mdi:download-network-outline"></ha-icon> Stáhnout torrent</ha-control-button>`
          : `<ha-control-button data-play="${i}" title="Přehrát"><ha-icon icon="mdi:play"></ha-icon></ha-control-button>
          <ha-control-button data-phone="${i}" title="Poslat do mobilu"><ha-icon icon="mdi:cellphone-play"></ha-icon></ha-control-button>
          <ha-control-button data-dl="${i}" title="Stáhnout"><ha-icon icon="mdi:download"></ha-icon></ha-control-button>
          <ha-control-button data-link="${i}" title="Zkopírovat odkaz"><ha-icon icon="mdi:link-variant"></ha-icon></ha-control-button>`}
        </span>
      </div>`).join("")}</div>`;
  }

  /** TMDB občas jeden obrázek odmítne — zkusíme ho ještě dvakrát, teprve pak necháme podklad. */
  _retryImages(root) {
    root.querySelectorAll("img").forEach((img) => {
      img.addEventListener("error", () => {
        const tries = +(img.dataset.try || 0);
        if (tries >= 2) { img.remove(); return; }
        img.dataset.try = String(tries + 1);
        const src = img.src;
        setTimeout(() => { img.src = ""; img.src = src; }, 400 * (tries + 1));
      });
    });
  }

  /** Obrázek na šířku a popis — u epizody její vlastní, jinak popis titulu. */
  _hero() {
    const st = this._state;
    const item = st.item || {};
    const art = (st.episode && st.episode.thumbnail) || item.background || item.poster || "";
    const text = (st.episode && st.episode.description) || item.description || "";
    if (!art && !text) return "";
    return `
      <div class="hero">
        ${art ? `<span class="heroart">
          <img src="${this._esc(art)}" referrerpolicy="no-referrer" />
          ${st.busy ? `<span class="mask"><ha-icon class="spin" icon="mdi:loading"></ha-icon></span>` : ""}
        </span>` : ""}
        ${text ? `<div class="desc${st.descOpen ? " open" : ""}" data-toggle="desc" title="Klepnutím rozbalíš">${this._esc(text)}</div>` : ""}
      </div>`;
  }

  _renderDownloads() {
    if (!this._root) return;
    const box = this._root.querySelector("#downloads");
    const sensor = this._hass && this._hass.states[this._config.downloads];
    const jobs = (sensor && sensor.attributes.downloads) || [];
    const files = (sensor && sensor.attributes.files) || [];
    const active = jobs.filter((j) => j.status === "running" || j.status === "queued");
    // Stažené patří na úvod; v detailu titulu by jen odváděly pozornost od streamů.
    const home = !["results", "episodes", "streams"].includes(this._state.view);
    const shown = home ? files : [];
    this._files = shown;
    this._active = active;
    if (!active.length && !shown.length) { box.hidden = true; box.innerHTML = ""; return; }
    box.hidden = false;
    box.innerHTML = (active.length ? `<div class="section"><ha-icon icon="mdi:progress-download"></ha-icon> Stahování</div>` : "")
      + active.map((j, i) => `
      <div class="dljob">
        <div class="dlrow">
          <span class="muted">${this._esc(j.name)}</span>
          <span class="muted">${j.status === "queued" ? "ve frontě" : j.percent + " %"}</span>
        </div>
        <div class="prog"><div style="width:${j.percent || 0}%"></div></div>
        <div class="dlrow dlinfo">
          <span class="muted">${j.status === "queued" ? "čeká na svoje místo ve frontě"
            : [this._speed(j.speed), this._eta(j.eta),
               j.size ? `${this._size(j.done)} z ${this._size(j.size)}` : ""].filter(Boolean).join(" · ")}</span>
          <ha-icon-button data-dlcancel="${i}" title="Zrušit stahování">
            <ha-icon icon="mdi:close"></ha-icon></ha-icon-button>
        </div>
      </div>`).join("") + (shown.length ? `
      <div class="section"><ha-icon icon="mdi:folder-download-outline"></ha-icon> Stažené
        ${sensor && sensor.attributes.free_gb != null ? `<span class="muted" style="font-weight:400">· volných ${sensor.attributes.free_gb} GB</span>` : ""}</div>
      ${shown.map((f, i) => `
        <div class="file" title="${this._esc(f.path)}">
          <span class="label">${this._esc(f.name)}${f.subtitles ? ` <span class="muted">· ${f.subtitles}× titulky</span>` : ""}</span>
          <span class="muted">${this._size(f.size)}</span>
          <span class="icons">
            <ha-icon-button data-fileplay="${i}" title="Přehrát"><ha-icon icon="mdi:play"></ha-icon></ha-icon-button>
            <ha-icon-button data-fileshare="${i}" title="Poslat odkaz do mobilu"><ha-icon icon="mdi:cellphone-play"></ha-icon></ha-icon-button>
            <ha-icon-button data-filedel="${i}" title="Smazat i s titulky"><ha-icon icon="mdi:delete-outline"></ha-icon></ha-icon-button>
          </span>
        </div>`).join("")}` : "");
    // ha-select vzniká i tady, takže se musí naplnit stejně jako v těle karty
    this._wirePicks(box);
    this._applyTooltips(box);
    this._bindFiles(box);
  }

  /** `ha-icon-button` si dovnitř dává prázdný `title`, který ten náš přebije —
   *  bublina se objeví, až když se text předá jako `label`. */
  _applyTooltips(root) {
    root.querySelectorAll("ha-icon-button[title]").forEach((el) => {
      const text = el.getAttribute("title");
      if (text && el.label !== text) el.label = text;
    });
  }

  _bindFiles(box) {
    box.querySelectorAll("[data-dlcancel]").forEach((el) =>
      el.addEventListener("click", () => this._cancelDownload(this._active[+el.dataset.dlcancel])));
    box.querySelectorAll("[data-fileplay]").forEach((el) =>
      el.addEventListener("click", () => this._playFile(this._files[+el.dataset.fileplay])));
    box.querySelectorAll("[data-fileshare]").forEach((el) =>
      el.addEventListener("click", () => this._shareFile(this._files[+el.dataset.fileshare])));
    box.querySelectorAll("[data-filedel]").forEach((el) =>
      el.addEventListener("click", () => this._deleteFile(this._files[+el.dataset.filedel])));
  }

  async _cancelDownload(job) {
    if (!job) return;
    await this._guard(async () => {
      await this._call("cancel_download", { download_id: job.id }, false);
      this._toast(`Stahování „${job.name}" zrušeno`);
    });
  }

  async _playFile(file) {
    const entityId = await this._choose("player");
    if (!entityId) { if (!this._players().length) this._toast("Není nastavený žádný přehrávač."); return; }
    this._state.player = entityId;
    await this._guard(async () => {
      await this._hass.callService("media_player", "play_media", {
        entity_id: entityId,
        media_content_type: "video",
        media_content_id: `media-source://media_source/local/${this._folder()}${file.name}`,
      });
      this._toast(`Spouštím na ${this._friendly(entityId)}`);
    });
  }

  /** Složka pro stahování relativně k /media (media_source ji adresuje takhle). */
  _folder() {
    const sensor = this._hass && this._hass.states[this._config.downloads];
    const dir = (sensor && sensor.attributes.directory) || "";
    const rel = dir.replace(/^\/media\/?/, "").replace(/\/$/, "");
    return rel ? rel + "/" : "";
  }

  /** Odkaz na stažený soubor přes veřejnou adresu HA (venku Nabu Casa) rovnou do mobilu. */
  async _shareFile(file) {
    const target = await this._choose("phone");
    if (!target && this._phones().length) return;   // výběr zavřený bez volby
    this._state.phone = target || this._state.phone;
    await this._guard(async () => {
      const res = await this._call("share_file", { path: file.path, notify_service: target || undefined });
      this._toast(res.url ? `Odkaz odeslán: ${this._phoneName(target)}` : "Odkaz se nepodařilo vytvořit");
    });
  }

  async _deleteFile(file) {
    if (!file) return;
    const ok = await this._confirm("Smazat soubor?",
      `${file.name}${file.subtitles ? " i s titulky" : ""}. Když film přišel z torrentu, odebere se i ten z qBittorrentu.`);
    if (!ok) return;
    await this._guard(async () => {
      await this._call("delete_file", { path: file.path }, false);
      this._toast("Smazáno");
    });
  }

  _speed(bytesPerSecond) {
    const mb = (bytesPerSecond || 0) / 1024 ** 2;
    if (!mb) return "";
    return mb >= 1 ? `${mb.toFixed(1)} MB/s` : `${Math.round(mb * 1024)} kB/s`;
  }

  /** Zbývající čas — u dlouhých stahování stačí minuty, sekundy jen na konci. */
  _eta(seconds) {
    if (seconds == null || seconds < 0) return "";
    if (seconds < 60) return `zbývá ${Math.round(seconds)} s`;
    const min = Math.round(seconds / 60);
    if (min < 60) return `zbývá ${min} min`;
    const h = Math.floor(min / 60);
    return `zbývá ${h} h ${String(min % 60).padStart(2, "0")} min`;
  }

  _size(bytes) {
    const gb = (bytes || 0) / 1024 ** 3;
    return gb >= 1 ? `${gb.toFixed(1)} GB` : `${Math.round((bytes || 0) / 1024 ** 2)} MB`;
  }

  /** Výběr ve vzhledu HA. `ha-control-select-menu` v 2026.9 výběr nijak nehlásí, proto nativní select. */
  /** Výběr ve vzhledu HA. `ha-select` je materiálový prvek s vlastní rozbalovací nabídkou;
   *  na starším HA, kde není, zbývá nativní `<select>` ostylovaný do podobné podoby. */
  _pick(id, label, options, value) {
    if (!customElements.get("ha-select")) {
      return `<label class="pick">
        <span>${this._esc(label)}</span>
        <select id="${id}" data-pick="${id}">
          ${options.map((o) => `<option value="${this._esc(o.value)}" ${o.value === value ? "selected" : ""}>${this._esc(o.label)}</option>`).join("")}
        </select>
      </label>`;
    }
    // ha-select v HA 2026.9 bere volby jako property `options`, ne jako vnořené položky
    this._pickData = this._pickData || {};
    this._pickData[id] = { label, options, value };
    return `<ha-select id="${id}" data-pick="${id}"></ha-select>`;
  }

  /** Jeden posluchač na celý obsah — přežije překreslení a funguje i uvnitř ha-icon-button. */
  _onClick(event) {
    const st = this._state;
    const keys = ["open", "back", "ep", "play", "phone", "dl", "link", "toggle", "hist", "histclear", "cont",
                  "watch", "wopen", "wremove", "wseen", "trakt", "want", "catalog", "research",
                  "torrent", "findtorrents"];
    const hit = event.composedPath().find((el) => el.dataset && keys.some((k) => k in el.dataset));
    if (!hit) return;
    const data = hit.dataset;
    if (data.toggle === "desc") { this._state.descOpen = !this._state.descOpen; this._paint(); return; }
    if (data.hist !== undefined) {
      const sensor = this._hass.states[this._config.downloads];
      const q = ((sensor && sensor.attributes.search_history) || [])[+data.hist];
      if (q) { this._input.value = q; st.query = q; this._search(); }
      return;
    }
    if (data.histclear !== undefined) return this._call("clear_history", {}, false).then(() => this._paint());
    if (data.cont !== undefined) {
      st.loading = `cont:${+data.cont}`;
      return this._openContinue(st.continueItems[+data.cont]);
    }
    if (data.watch !== undefined) return this._toggleWatch();
    if (data.wopen !== undefined) {
      const w = this._watchlist()[+data.wopen];
      return this._openItem({ id: w.id, type: "series", title: w.title, alt: w.alt, poster: w.poster });
    }
    if (data.want !== undefined) return this._toggleWant();
    if (data.wantquery !== undefined) return this._wantQuery();
    if (data.catalog !== undefined) return this._searchCatalog();
    if (data.research !== undefined) { st.catalog = false; return this._search(); }
    if (data.trakt !== undefined) {
      const t = this._traktList()[+data.trakt];
      if (!t) return undefined;
      if (t.pending) { this._toast("Titul zatím žádný zdroj nemá — hlídám ho."); return undefined; }
      const parts = String(t.id).split(":");
      if (parts.length === 3) {
        // uložený díl: seznam epizod by byl objížďka, otevřít rovnou jeho streamy
        const series = t.series || parts[0];
        st.item = { id: series, type: "series", title: t.title, year: t.year,
                    alt: t.alt || null, poster: t.poster || "" };
        st.title = t.title;
        st.episode = { id: t.id, season: +parts[1], episode: +parts[2], title: "" };
        st.descOpen = false;
        return this._loadStreams({ id: t.id, type: "series", series, alt: t.alt || null })
          .then(() => this._fillDetail());   // plakát a popis seriálu k dílu
      }
      return this._openItem({ id: t.id, type: t.type, title: t.title, year: t.year, alt: t.alt || null,
                              poster: t.poster || "", description: t.description || "" });
    }
    if (data.wseen !== undefined) {
      const w = this._watchlist()[+data.wseen];
      this._watchOverride = this._watchOverride || {};
      this._watchOverride[w.id] = { ...w, new: null };  // zhasne hned
      return this._guard(async () => { await this._call("mark_seen", { id: w.id }, false); });
    }
    if (data.wremove !== undefined) {
      const w = this._watchlist()[+data.wremove];
      this._watchOverride = this._watchOverride || {};
      this._watchOverride[w.id] = false;  // zmizí hned
      return this._guard(async () => { await this._call("watch_series", { id: w.id, remove: true }, false); });
    }
    if (data.open !== undefined) {
      st.loading = `res:${+data.open}`;
      return this._openItem(st.results[+data.open]);
    }
    if (data.back !== undefined) {
      const target = data.back === "back" ? (st.stack.pop() || "search") : data.back;
      if (data.back !== "back") { st.stack = []; st.catalog = false; }
      st.view = target;
      if (target === "search") st.continueItems = null;
      this._paint();
      return;
    }
    if (data.ep !== undefined) {
      const list = st.episodes.filter((e) => st.season === null || e.season === st.season);
      const ep = list[+data.ep];
      st.title = `${st.item.title} — ${ep.season}x${String(ep.episode).padStart(2, "0")} ${ep.title}`;
      st.episode = ep;
      st.descOpen = false;
      return this._loadStreams({ id: ep.id, type: "series", series: st.item.id, alt: st.item.alt });
    }
    if (data.play !== undefined) return this._play(st.streams[+data.play]);
    if (data.phone !== undefined) return this._toPhone(st.streams[+data.phone]);
    if (data.dl !== undefined) return this._download(st.streams[+data.dl]);
    if (data.link !== undefined) return this._openLink(st.streams[+data.link]);
    if (data.torrent !== undefined) return this._downloadTorrent(st.streams[+data.torrent]);
    if (data.findtorrents !== undefined) return this._findTorrents();
    return undefined;
  }

  /** Popis pro tooltip — celý název souboru a co karta zkrátila. */
  _streamTitle(s) {
    const rows = [s.label];
    if (s.file && !s.label.includes(s.file)) rows.push(s.file);
    if (s.subs && s.subs.length) rows.push("titulky: " + s.subs.join(", "));
    if (s.bitrate) rows.push(`${s.bitrate} Mb/s`);
    if (s.direct) rows.push("hraje i mimo domácí síť");
    if (s.kind === "torrent") {
      rows.push(`${s.tracker || "tracker"}: ${s.seeders} sdílí, ${s.leechers} stahuje`);
      rows.push("stáhne se přes qBittorrent, přehrát půjde až potom");
    }
    return rows.filter(Boolean).join("\n");
  }

  _esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
}


/** Vizuální editor karty — pole skládá `ha-form`, cíle notifikací bere ze senzoru integrace. */
class NokturnoCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) {
      this._form.hass = hass;
      this._form.schema = this._schema();
    }
  }

  _phoneOptions() {
    const sensor = this._hass && this._hass.states[this._config.downloads || "sensor.nokturno_stahovani"];
    const targets = (sensor && sensor.attributes.notify_targets) || [];
    return targets.map((t) => ({
      value: t.service,
      label: t.user ? `${t.user} · ${t.device}` : t.device,
    }));
  }

  _schema() {
    const phones = this._phoneOptions();
    return [
      { name: "title", selector: { text: {} } },
      { name: "show_header", selector: { boolean: {} } },
      { name: "player", selector: { entity: { domain: "media_player" } } },
      { name: "players", selector: { entity: { domain: "media_player", multiple: true } } },
      phones.length
        ? { name: "phone", selector: { select: { options: phones, mode: "dropdown" } } }
        : { name: "phone", selector: { text: {} } },
      { name: "downloads", selector: { entity: { domain: "sensor", integration: "nokturno" } } },
    ];
  }

  _label(schema) {
    return {
      title: "Nadpis karty",
      show_header: "Zobrazit nadpis a ikonu",
      player: "Výchozí přehrávač",
      players: "Přehrávače na výběr",
      phone: "Výchozí mobil",
      downloads: "Senzor stahování",
    }[schema.name] || schema.name;
  }

  _render() {
    if (this._form) {
      this._form.data = this._config;
      return;
    }
    this.innerHTML = "";
    const form = document.createElement("ha-form");
    form.hass = this._hass;
    form.data = this._config;
    form.schema = this._schema();
    form.computeLabel = (schema) => this._label(schema);
    form.addEventListener("value-changed", (e) => {
      this._config = { type: "custom:nokturno-card", ...e.detail.value };
      this.dispatchEvent(new CustomEvent("config-changed", {
        detail: { config: this._config }, bubbles: true, composed: true,
      }));
    });
    this.appendChild(form);
    this._form = form;
  }
}

// Frontend HA si po startu nasadí vlastní registr prvků (scoped custom elements) a o tom,
// co bylo definováno dřív, neví — karta by hlásila „Custom element doesn't exist“.
// Proto registraci po načtení stránky ještě několikrát zopakujeme (podtřídou, tu registr přijme).
function defineCard(tag, cls) {
  try {
    if (!customElements.get(tag)) customElements.define(tag, class extends cls {});
  } catch (err) { /* jiný registr už jméno zná — nevadí */ }
}

function registerNokturnoCards() {
  defineCard("nokturno-card-editor", NokturnoCardEditor);
  defineCard("nokturno-card", NokturnoCard);
}

registerNokturnoCards();
if (document.readyState !== "complete") window.addEventListener("load", registerNokturnoCards, { once: true });
[500, 1500, 3000, 6000].forEach((ms) => setTimeout(registerNokturnoCards, ms));
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "nokturno-card")) window.customCards.push({
  type: "nokturno-card",
  preview: true,
  documentationURL: "https://github.com/matata86/nokturno-ha",
  name: "Nokturno",
  description: "Hledání ve WebShare, Sosáči a Luně — přehrání v Kodi, stažení nebo odeslání do mobilu.",
});
