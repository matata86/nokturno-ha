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

const CARD_VERSION = "1.25.1";
console.info(`%c NOKTURNO-CARD %c ${CARD_VERSION} `, "background:#5b4b8a;color:#fff;border-radius:3px 0 0 3px", "background:#f0b429;color:#222;border-radius:0 3px 3px 0");

const SOURCE_COLORS = { "Luna": "#8e7cc3", "WebShare": "#4a90d9", "Sosáč": "#e08b3c" };
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
      seasons: [], season: null, item: null, title: "", busy: false, loading: null, error: "",
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
    const needed = ["ha-input", "ha-control-select", "ha-control-button", "ha-control-select-menu", "ha-icon-button"];
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
    finally { this._state.busy = false; this._state.loading = null; this._paint(); }
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
    const query = (this._state.query || this._readInput() || "").trim();
    if (!query) return;
    this._state.stack = [];
    this._state.query = query;
    await this._guard(async () => {
      const res = await this._call("search", { query, type: this._state.type, limit: 24 });
      this._state.results = res.results || [];
      this._state.item = null;
      this._state.view = "results";
    });
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
    if (item.type === "series") {
      this._state.stack.push(this._state.view);
      await this._guard(async () => {
        const res = await this._call("episodes", { id: item.id });
        this._state.episodes = res.episodes || [];
        this._state.seasons = res.seasons || [];
        this._state.season = this._state.seasons.find((s) => s > 0) ?? this._state.seasons[0] ?? null;
        this._state.view = "episodes";
      });
      return;
    }
    await this._loadStreams({ id: item.id, type: "movie", alt: item.alt });
  }

  async _loadStreams(data) {
    this._state.stack.push(this._state.view);
    await this._guard(async () => {
      const res = await this._call("streams", data);
      this._state.streams = res.streams || [];
      this._state.streamTarget = data;
      this._state.view = "streams";
    });
  }

  _target(stream) {
    const target = { ...this._state.streamTarget };
    if (!target.url) target.stream = stream.index;
    return target;
  }

  async _play(stream) {
    const entityId = this._state.player || this._players()[0];
    if (!entityId) { this._toast("Není nastavený žádný přehrávač."); return; }
    await this._guard(async () => {
      await this._call("play", { ...this._target(stream), entity_id: entityId }, false);
      this._toast(`Spouštím na ${this._friendly(entityId)}`);
    });
  }

  async _download(stream) {
    await this._guard(async () => {
      const res = await this._call("download", this._target(stream));
      this._toast(`Stahuji do ${res.path || "úložiště"}`);
    });
  }

  async _toPhone(stream) {
    const target = this._state.phone || this._phones()[0];
    if (!target) { this._toast("Nenašel jsem žádný mobil s aplikací Home Assistant."); return; }
    await this._guard(async () => {
      await this._call("send_link", {
        ...this._target(stream),
        notify_service: target,
        name: `${this._state.title || ""} — ${stream.label}`.trim(),
      }, false);
      this._toast(`Odkaz odeslán: ${this._phoneName(target)}`);
    });
  }

  async _openLink(stream) {
    await this._guard(async () => {
      const res = await this._call("resolve", this._target(stream));
      if (!res.url) return;
      this._toast(this._copy(res.url) ? "Odkaz zkopírován — vlož ho do VLC nebo prohlížeče"
                                      : "Odkaz se nepodařilo zkopírovat");
    });
  }

  /** Rozkoukané: Kodi dostane přímo plugin:// odkaz z doplňku (obnoví pozici). */
  async _playContinue(item) {
    // pokračuje se na tom Kodi, kde je titul rozkoukaný
    const entityId = item.entity_id || this._state.player || this._players()[0];
    if (!entityId) { this._toast("Není nastavený žádný přehrávač."); return; }
    await this._guard(async () => {
      await this._hass.callService("media_player", "play_media", {
        entity_id: entityId, media_content_type: "video", media_content_id: item.file,
      });
      this._toast(`Pokračuji na ${this._friendly(entityId)}: ${item.label}`);
    });
  }

  /** Kopírování do schránky. `navigator.clipboard` funguje jen přes https nebo localhost,
   *  na `http://<ip>:8123` (typicky mobil v LAN) se musí přes skryté pole a execCommand. */
  _copy(text) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).catch(() => this._copyFallback(text));
      return true;
    }
    return this._copyFallback(text);
  }

  _copyFallback(text) {
    const field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.cssText = "position:fixed;top:0;left:0;opacity:0";
    document.body.appendChild(field);
    field.select();
    field.setSelectionRange(0, text.length);
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
    field.remove();
    return ok;
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
        .busy { position:absolute; right:16px; top:12px; }
        ha-card { position:relative; }
        /* hledání pod sebou přes celou šířku karty */
        .bar { display:grid; grid-template-columns: 1fr; gap:8px; align-items:center; }
        .bar[hidden] { display:none; }  /* jinak by display:grid přebil atribut hidden */
        ha-control-button#go { width:100%; }
        ha-control-button#go ha-icon { --mdc-icon-size:20px; margin-right:4px; vertical-align:-4px; }
        ha-control-select { --control-select-thickness:40px; }
        ha-control-select::part(label), ha-control-select { white-space:nowrap; }
        /* detail: [zpět][název] a pod tím dva výběry vedle sebe přes celou šířku */
        .bar.detail { display:block; margin-top:10px; }
        .titlerow { display:flex; align-items:center; gap:4px; }
        .titlerow .name { flex:1; min-width:0; font-size:1.05rem; }
        .picks { display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:8px; margin-top:8px; }
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
        .hero { position:relative; }
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
        .stream { display:flex; align-items:center; gap:8px; padding:4px 0; border-bottom:1px solid var(--divider-color); }
        /* dlouhý název souboru nesmí roztáhnout řádek a vytlačit ikony mimo kartu */
        .stream .label { flex:1 1 0; min-width:0; font-size:.9rem; overflow-wrap:anywhere;
                         display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
        .stream .icons { flex:0 0 auto; }
        /* seznamy na úvodu mají štítek nad názvem, ať je řádek čitelný i na širší kartě */
        .stream.stacked { display:grid; grid-template-columns:minmax(0, 1fr) auto;
                          grid-template-areas:"tag icons" "label icons"; column-gap:8px; row-gap:2px; padding:8px 0; }
        .stream.stacked .tag { grid-area:tag; justify-self:start; }
        .stream.stacked .label { grid-area:label; -webkit-line-clamp:2; }
        .stream.stacked .icons { grid-area:icons; align-self:center; }
        .tag { font-size:.7rem; font-weight:600; padding:2px 6px; border-radius:6px; color:#fff; white-space:nowrap;
               display:inline-flex; align-items:center; gap:3px; }
        /* zeměkoule = odkaz vede přímo z WebShare, takže hraje i mimo domácí síť */
        .tag .ext { --mdc-icon-size:13px; opacity:.9; }
        .chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
        .chip { background: var(--secondary-background-color); color: var(--primary-text-color); border:none;
                border-radius:14px; padding:5px 11px; font:inherit; font-size:.8rem; cursor:pointer; }
        .chip.x { color: var(--secondary-text-color); }
        .section { margin-top:14px; font-weight:500; display:flex; align-items:center; gap:6px; }
        .section ha-icon { --mdc-icon-size:18px; }
        .tag ha-icon.ext { --mdc-icon-size:12px; }
        .cont { display:grid; grid-template-columns:repeat(auto-fill, minmax(150px, 1fr)); gap:10px; margin-top:8px; }
        .cont .poster .thumb { aspect-ratio:16/9; }
        .where { position:absolute; left:6px; bottom:6px; font-size:.68rem; font-weight:600; padding:2px 6px;
                 border-radius:6px; background:rgba(0,0,0,.65); color:#fff; }
        .watch { margin-left:auto; }
        .legend { margin-top:8px; font-size:.75rem; color: var(--secondary-text-color); display:flex;
                  align-items:center; gap:4px; }
        .legend ha-icon { --mdc-icon-size:14px; }
        .icons { display:flex; }
        .icons ha-icon-button { --mdc-icon-button-size:40px; --mdc-icon-size:20px; }
        /* na úzké kartě (mobil) se popis lámal vedle štítku — štítek proto nad text */
        @container (max-width: 430px) {
          .stream { display:grid; grid-template-columns:minmax(0, 1fr) auto; grid-template-areas:"tag icons" "label icons";
                    column-gap:8px; row-gap:2px; padding:8px 0; }
          .stream .tag { grid-area:tag; justify-self:start; }
          .stream .label { grid-area:label; }
          .stream .icons { grid-area:icons; align-self:center; }
        }
        .muted { color: var(--secondary-text-color); font-size:.85rem; }
        .err { color: var(--error-color); font-size:.85rem; margin-top:8px; }
        .ep { display:flex; gap:8px; align-items:center; padding:9px 0; border-bottom:1px solid var(--divider-color); cursor:pointer; }
        .ep .n { color: var(--secondary-text-color); min-width:46px; font-variant-numeric: tabular-nums; }
        .dl { margin-top:4px; }
        .dlrow { display:flex; justify-content:space-between; gap:8px; }
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
        <span id="busy" class="muted busy"></span>
        <div class="bar" id="search">
          <ha-input id="q" placeholder="Název filmu nebo seriálu" with-clear></ha-input>
          <ha-control-button id="go"><ha-icon icon="mdi:magnify"></ha-icon> Hledat</ha-control-button>
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
    kind.addEventListener("value-changed", (e) => { this._state.type = (e.detail && e.detail.value) || kind.value; });
    this._paint();
  }

  _paint() {
    if (!this._root) return;
    this._root.querySelector("#busy").innerHTML = this._state.busy
      ? '<ha-icon class="spin" icon="mdi:loading"></ha-icon>' : "";
    const body = this._root.querySelector("#body");
    const st = this._state;
    // v detailu (epizody, streamy) je hledání jen na překážku
    this._root.querySelector("#search").hidden = st.view === "streams" || st.view === "episodes";
    let html = "";
    if (st.view === "results") html = this._results();
    else if (st.view === "episodes") html = this._episodes();
    else if (st.view === "streams") html = this._streams();
    else html = this._home();
    if (st.error) html += `<div class="err">${this._esc(st.error)}</div>`;
    body.innerHTML = html;
    body.querySelectorAll("select[data-pick]").forEach((el) => el.addEventListener("change", () => {
      const id = el.dataset.pick;
      if (id === "season") { st.season = +el.value; this._paint(); }
      else if (id === "player") { st.player = el.value; }
      else if (id === "phone") { st.phone = el.value; }
    }));
    this._retryImages(body);
    this._renderDownloads();
  }

  /** Úvodní obrazovka: poslední dotazy, rozkoukané z Kodi, sledované seriály. */
  _home() {
    const st = this._state;
    const sensor = this._hass && this._hass.states[this._config.downloads];
    const history = (sensor && sensor.attributes.search_history) || [];
    let html = history.length
      ? `<div class="chips">${history.map((q, i) => `<button class="chip" data-hist="${i}">${this._esc(q)}</button>`).join("")}
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
            </span>
            <div class="t">${this._esc(c.label)}</div>
          </button>`).join("")}</div>`;
    }
    const trakt = this._traktList();
    if (trakt.length) {
      html += `<div class="section"><ha-icon icon="mdi:bookmark-check-outline"></ha-icon> K zhlédnutí (Trakt)</div>
        <div>${trakt.slice(0, 12).map((t, i) => `
          <div class="stream stacked" data-trakt="${i}" style="cursor:pointer">
            <span class="tag" style="background:${t.streams ? "#2e8b57" : "#777"}">
              <ha-icon icon="${t.streams ? "mdi:play-circle-outline" : "mdi:clock-outline"}" class="ext"></ha-icon>
              ${t.streams ? "lze pustit" : "zatím ne"}</span>
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
            <span class="label">${this._esc(w.title)}${w.new
              ? ` — ${w.new.season}x${String(w.new.episode).padStart(2, "0")} ${this._esc(w.new.title)}`
              : ` <span class="muted">· ${w.available
                  ? `ke sledování ${w.available.season}x${String(w.available.episode).padStart(2, "0")}`
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
    const home = `<div class="chips"><button class="chip" data-back="search"><ha-icon icon="mdi:home-outline" style="--mdc-icon-size:14px"></ha-icon> Úvod</button></div>`;
    if (!st.results.length) return home + `<div class="muted" style="margin-top:10px">Nic nenalezeno.</div>`;
    const files = st.results.every((r) => r.type === "file");
    return home + `<div class="grid${files ? " files" : ""}">` + st.results.map((r, i) => `
      <button class="poster" data-open="${i}">
        <span class="thumb">
          <ha-icon icon="mdi:filmstrip"></ha-icon>
          ${r.poster ? `<img src="${this._esc(r.poster)}" referrerpolicy="no-referrer" />` : ""}
          ${st.busy && st.loading === i ? `<span class="mask"><ha-icon class="spin" icon="mdi:loading"></ha-icon></span>` : ""}
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
        <div class="ep" data-ep="${i}">
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
          <span class="name">${this._esc(st.title)}${st.item && st.item.year && !st.episode ? ` <span class="muted">(${st.item.year})</span>` : ""}</span>
        </div>
        <span class="picks">
          ${players.length > 1 ? this._pick("player", "Přehrávač", players.map((p) => ({ value: p, label: this._friendly(p) })), st.player) : ""}
          ${phones.length > 1 ? this._pick("phone", "Mobil", phones.map((p) => ({ value: p, label: this._phoneName(p) })), st.phone) : ""}
        </span>
      </div>`;
    if (!st.streams.length) return head + `<div class="muted">Pro tento titul se nenašel žádný stream.</div>`;
    const legend = st.streams.some((s) => s.direct)
      ? `<div class="legend"><ha-icon icon="mdi:earth"></ha-icon> = hraje i mimo domácí síť</div>` : "";
    return head + legend + `<div>${st.streams.map((s, i) => `
      <div class="stream">
        <span class="tag" style="background:${SOURCE_COLORS[s.source] || "#777"}">${s.source || "?"}${
          s.direct ? `<ha-icon class="ext" icon="mdi:earth" title="Hraje i mimo domácí síť"></ha-icon>` : ""}</span>
        <span class="label">${this._esc(s.label.replace(s.source + "  ·  ", ""))}</span>
        <span class="icons">
          <ha-icon-button data-play="${i}" title="Přehrát"><ha-icon icon="mdi:play"></ha-icon></ha-icon-button>
          <ha-icon-button data-phone="${i}" title="Poslat do mobilu"><ha-icon icon="mdi:cellphone-play"></ha-icon></ha-icon-button>
          <ha-icon-button data-dl="${i}" title="Stáhnout"><ha-icon icon="mdi:download"></ha-icon></ha-icon-button>
          <ha-icon-button data-link="${i}" title="Zkopírovat odkaz"><ha-icon icon="mdi:link-variant"></ha-icon></ha-icon-button>
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
        ${art ? `<img src="${this._esc(art)}" referrerpolicy="no-referrer" />` : ""}
        ${st.busy && art ? `<span class="mask"><ha-icon class="spin" icon="mdi:loading"></ha-icon></span>` : ""}
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
    this._files = files;
    if (!active.length && !files.length) { box.hidden = true; box.innerHTML = ""; return; }
    box.hidden = false;
    box.innerHTML = (active.length ? `<div class="section"><ha-icon icon="mdi:progress-download"></ha-icon> Stahování</div>` : "")
      + active.map((j) => `
      <div style="margin:6px 0">
        <div class="dlrow">
          <span class="muted">${this._esc(j.name)}</span>
          <span class="muted">${j.status === "queued" ? "ve frontě" : j.percent + " %"}</span>
        </div>
        <div class="prog"><div style="width:${j.percent || 0}%"></div></div>
      </div>`).join("") + (files.length ? `
      <div class="section"><ha-icon icon="mdi:folder-download-outline"></ha-icon> Stažené
        ${sensor && sensor.attributes.free_gb != null ? `<span class="muted" style="font-weight:400">· volných ${sensor.attributes.free_gb} GB</span>` : ""}</div>
      ${files.map((f, i) => `
        <div class="file">
          <span class="label">${this._esc(f.name)}${f.subtitles ? ` <span class="muted">· ${f.subtitles}× titulky</span>` : ""}</span>
          <span class="muted">${this._size(f.size)}</span>
          <span class="icons">
            <ha-icon-button data-fileplay="${i}" title="Přehrát"><ha-icon icon="mdi:play"></ha-icon></ha-icon-button>
            <ha-icon-button data-fileshare="${i}" title="Poslat odkaz do mobilu"><ha-icon icon="mdi:cellphone-play"></ha-icon></ha-icon-button>
            <ha-icon-button data-filedel="${i}" title="Smazat i s titulky"><ha-icon icon="mdi:delete-outline"></ha-icon></ha-icon-button>
          </span>
        </div>`).join("")}` : "");
    this._bindFiles(box);
  }

  _bindFiles(box) {
    box.querySelectorAll("[data-fileplay]").forEach((el) =>
      el.addEventListener("click", () => this._playFile(this._files[+el.dataset.fileplay])));
    box.querySelectorAll("[data-fileshare]").forEach((el) =>
      el.addEventListener("click", () => this._shareFile(this._files[+el.dataset.fileshare])));
    box.querySelectorAll("[data-filedel]").forEach((el) =>
      el.addEventListener("click", () => this._deleteFile(this._files[+el.dataset.filedel])));
  }

  async _playFile(file) {
    const entityId = this._state.player || this._players()[0];
    if (!entityId) { this._toast("Není nastavený žádný přehrávač."); return; }
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
    const target = this._state.phone || this._phones()[0];
    await this._guard(async () => {
      const res = await this._call("share_file", { path: file.path, notify_service: target || undefined });
      this._toast(res.url ? `Odkaz odeslán: ${this._phoneName(target)}` : "Odkaz se nepodařilo vytvořit");
    });
  }

  async _deleteFile(file) {
    if (!window.confirm(`Smazat ${file.name}${file.subtitles ? " i s titulky" : ""}?`)) return;
    await this._guard(async () => {
      await this._call("delete_file", { path: file.path }, false);
      this._toast("Smazáno");
    });
  }

  _size(bytes) {
    const gb = (bytes || 0) / 1024 ** 3;
    return gb >= 1 ? `${gb.toFixed(1)} GB` : `${Math.round((bytes || 0) / 1024 ** 2)} MB`;
  }

  /** Výběr ve vzhledu HA. `ha-control-select-menu` v 2026.9 výběr nijak nehlásí, proto nativní select. */
  _pick(id, label, options, value) {
    return `<label class="pick">
      <span>${this._esc(label)}</span>
      <select id="${id}" data-pick="${id}">
        ${options.map((o) => `<option value="${this._esc(o.value)}" ${o.value === value ? "selected" : ""}>${this._esc(o.label)}</option>`).join("")}
      </select>
    </label>`;
  }

  /** Jeden posluchač na celý obsah — přežije překreslení a funguje i uvnitř ha-icon-button. */
  _onClick(event) {
    const st = this._state;
    const keys = ["open", "back", "ep", "play", "phone", "dl", "link", "toggle", "hist", "histclear", "cont",
                  "watch", "wopen", "wremove", "wseen", "trakt"];
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
    if (data.cont !== undefined) return this._playContinue(st.continueItems[+data.cont]);
    if (data.watch !== undefined) return this._toggleWatch();
    if (data.wopen !== undefined) {
      const w = this._watchlist()[+data.wopen];
      return this._openItem({ id: w.id, type: "series", title: w.title, alt: w.alt, poster: w.poster });
    }
    if (data.trakt !== undefined) {
      const t = this._traktList()[+data.trakt];
      if (!t) return undefined;
      return this._openItem({ id: t.id, type: t.type, title: t.title, year: t.year, alt: null, poster: "" });
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
      st.loading = +data.open;
      return this._openItem(st.results[+data.open]);
    }
    if (data.back !== undefined) {
      const target = data.back === "back" ? (st.stack.pop() || "search") : data.back;
      if (data.back !== "back") st.stack = [];
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
    return undefined;
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

if (!customElements.get("nokturno-card-editor")) customElements.define("nokturno-card-editor", NokturnoCardEditor);

// modul může přijít dvakrát (extra_module_url z integrace + Lovelace resource) — definovat jen jednou
if (!customElements.get("nokturno-card")) customElements.define("nokturno-card", NokturnoCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "nokturno-card")) window.customCards.push({
  type: "nokturno-card",
  preview: true,
  documentationURL: "https://github.com/matata86/nokturno-ha",
  name: "Nokturno",
  description: "Hledání ve WebShare, Sosáči a Luně — přehrání v Kodi, stažení nebo odeslání do mobilu.",
});
