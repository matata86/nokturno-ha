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

const CARD_VERSION = "8.3.0b6";
console.info(`%c NOKTURNO-CARD %c ${CARD_VERSION} `, "background:#5b4b8a;color:#fff;border-radius:3px 0 0 3px", "background:#f0b429;color:#222;border-radius:0 3px 3px 0");

const SOURCE_COLORS = { "Luna": "#8e7cc3", "WebShare": "#4a90d9", "Sosáč": "#e08b3c",
                        "HellSpy": "#d9584a", "Sledujteto": "#2a9d8f", "FastShare": "#c99a1e",
                        "Přehraj.to": "#c94f7c", "Torrent": "#3f9e6f" };
const KINDS = [
  { value: "movie", label: "Filmy" },
  { value: "series", label: "Seriály" },
];

/* Slovenčina. Klíč je přesný český text z karty, hodnota jeho slovenská verze;
   {0}, {1}… jsou dosazované hodnoty. Karta mluví slovensky, když má uživatel v HA
   jazyk začínající na „sk“, jinak česky jako dřív. Nový text: v kódu česky přes
   `this._t("…")` a sem jeho překlad — chybějící klíč se prostě ukáže česky. */
const SK = {
  "Cache hledání a streamů vymazána": "Cache vyhľadávania a streamov vymazaná",
  "Není nastavený žádný přehrávač.": "Nie je nastavený žiadny prehrávač.",
  "Spouštím na {0}": "Spúšťam na {0}",
  "Do kterého mobilu?": "Do ktorého mobilu?",
  "Kde přehrát?": "Kde prehrať?",
  "Zavřít": "Zavrieť",
  "Smazat": "Zmazať",
  "Zpět": "Späť",
  "Stahuji do {0}": "Sťahujem do {0}",
  "úložiště": "úložiska",
  "Na trackerech nic nenašel": "Na trackeroch sa nič nenašlo",
  "Fulltext nic dalšího nenašel": "Fulltext nič ďalšie nenašiel",
  "Torrent zařazen do stahování": "Torrent zaradený do sťahovania",
  "Nenašel jsem žádný mobil s aplikací Home Assistant.": "Nenašiel som žiadny mobil s aplikáciou Home Assistant.",
  "Odkaz odeslán: {0}": "Odkaz odoslaný: {0}",
  "Odkaz zkopírován — vlož ho do VLC nebo prohlížeče": "Odkaz skopírovaný — vlož ho do VLC alebo prehliadača",
  "Zkopíruj odkaz (Ctrl+C):": "Skopíruj odkaz (Ctrl+C):",
  "Titul se nepodařilo najít.": "Titul sa nepodarilo nájsť.",
  "Název filmu nebo seriálu": "Názov filmu alebo seriálu",
  "Hledat ve WebShare, Sosáči a Luně": "Hľadať vo WebShare, Sosáči a Lune",
  "Hledat": "Hľadať",
  "Vymazat cache hledání a streamů": "Vymazať cache vyhľadávania a streamov",
  "Zopakovat hledání „{0}“": "Zopakovať hľadanie „{0}“",
  "Smazat historii": "Zmazať históriu",
  "Zadej název — hledá se ve WebShare, Sosáči i Luně naráz.": "Zadaj názov — hľadá sa vo WebShare, Sosáči aj Lune naraz.",
  "Pokračovat ve sledování": "Pokračovať v sledovaní",
  "Hlídané": "Strážené",
  "Otevřít streamy — {0} k dispozici": "Otvoriť streamy — {0} k dispozícii",
  "Zatím žádný stream; hlídám a dám vědět": "Zatiaľ žiadny stream; strážim a dám vedieť",
  "jen torrent": "len torrent",
  "lze pustit": "dá sa pustiť",
  "hlídám": "strážim",
  "zatím ne": "zatiaľ nie",
  "kontrolovat dál": "kontrolovať ďalej",
  "Streamy jsou, ale ne v požadované kvalitě/zvuku — kliknutím přestaneš kontrolovat dál": "Streamy sú, ale nie v požadovanej kvalite/zvuku — kliknutím prestaneš kontrolovať ďalej",
  "Streamy jsou, ale ne v požadované kvalitě/zvuku (např. 5.1) — označit, ať se to dál sleduje": "Streamy sú, ale nie v požadovanej kvalite/zvuku (napr. 5.1) — označiť, nech sa to ďalej sleduje",
  "Můj seznam": "Môj zoznam",
  "Přesunout do Mého seznamu": "Presunúť do Môjho zoznamu",
  "Přidáno do Mého seznamu": "Pridané do Môjho zoznamu",
  "Odebráno z Mého seznamu": "Odobrané z Môjho zoznamu",
  "Přidat do Mého seznamu": "Pridať do Môjho zoznamu",
  "Odebrat z Mého seznamu": "Odobrať z Môjho zoznamu",
  "· {0} streamů": "· {0} streamov",
  "nový díl": "nový diel",
  "sleduji": "sledujem",
  "ke sledování": "na sledovanie",
  "zatím bez streamu": "zatiaľ bez streamu",
  "odvysíláno": "odvysielané",
  "Označit nový díl jako viděný": "Označiť nový diel ako videný",
  "Otevřít": "Otvoriť",
  "Přestat sledovat": "Prestať sledovať",
  "Seriál už nesleduji": "Seriál už nesledujem",
  "Nové díly budu hlásit": "Nové diely budem hlásiť",
  "Odebráno ze seznamu": "Odobraté zo zoznamu",
  "Přidáno — dám vědět, až bude ke sledování": "Pridané — dám vedieť, keď bude na sledovanie",
  "Odebráno z Pokračovat ve sledování": "Odobraté z Pokračovať v sledovaní",
  "Napiš název — hledat budu rovnou v databázi filmů.": "Napíš názov — hľadať budem rovno v databáze filmov.",
  "V databázi filmů nic takového není.": "V databáze filmov nič také nie je.",
  "Napiš nejdřív název do pole pro hledání.": "Najprv napíš názov do poľa na hľadanie.",
  "Hlídám „{0}\" — dám vědět, až bude ke sledování": "Strážim „{0}“ — dám vedieť, keď bude na sledovanie",
  "Zpět na úvodní obrazovku": "Späť na úvodnú obrazovku",
  "Zpět na výsledky z WebShare, Sosáče a Luny": "Späť na výsledky z WebShare, Sosáča a Luny",
  "Zpět k výsledkům ze zdrojů": "Späť k výsledkom zo zdrojov",
  "Hledat v databázi filmů (IMDb/TMDB) — najde i tituly, které zdroje nemají": "Hľadať v databáze filmov (IMDb/TMDB) — nájde aj tituly, ktoré zdroje nemajú",
  "Hledat v databázi filmů": "Hľadať v databáze filmov",
  "Ve zdrojích nic nenalezeno — zkus databázi filmů.": "V zdrojoch sa nič nenašlo — skús databázu filmov.",
  "Z databáze filmů — klepnutím otevřeš detail; záložkou v něm si titul uložíš mezi hlídané.": "Z databázy filmov — ťuknutím otvoríš detail; záložkou v ňom si titul uložíš medzi strážené.",
  "Sledovat nové díly": "Sledovať nové diely",
  "Sezóna": "Séria",
  "Speciály": "Špeciály",
  "Zobrazit streamy epizody": "Zobraziť streamy epizódy",
  "Přeskočeno — streamy jsou z ostatních zdrojů.": "Preskočené — streamy sú z ostatných zdrojov.",
  "Odebrat z hlídaných": "Odobrať zo strážených",
  "Přidat mezi hlídané": "Pridať medzi strážené",
  "Odebrat z Pokračovat ve sledování": "Odobrať z Pokračovať v sledovaní",
  "Prohledat torrentové trackery přes Prowlarr — trvá pár sekund, proto se hledá až na vyžádání": "Prehľadať torrentové trackery cez Prowlarr — trvá pár sekúnd, preto sa hľadá až na požiadanie",
  "Hledám torrenty…": "Hľadám torrenty…",
  "Hledat torrenty": "Hľadať torrenty",
  "Uvolněné hledání podle slov v názvu souboru — najde i to, co přísný filtr zahodí jako podobný, ale jiný titul": "Voľnejšie hľadanie podľa slov v názve súboru — nájde aj to, čo prísny filter zahodí ako podobný, ale iný titul",
  "Hledám…": "Hľadám…",
  "Zkusit fulltext na {0}": "Skúsiť fulltext na {0}",
  "Pro tento titul se nenašel žádný stream.": "Pre tento titul sa nenašiel žiadny stream.",
  "Ulož si ho záložkou nahoře a dám vědět, jakmile se objeví.": "Ulož si ho záložkou hore a dám vedieť, hneď ako sa objaví.",
  "hraje i mimo domácí síť": "hrá aj mimo domácej siete",
  "Hraje i mimo domácí síť": "Hrá aj mimo domácej siete",
  "Neověřeno — z ručního fulltextového hledání, může to být i jiný titul": "Neoverené — z ručného fulltextového hľadania, môže to byť aj iný titul",
  "Zařadit ke stažení do qBittorrentu — až se soubor stáhne, objeví se mezi staženými": "Zaradiť na stiahnutie do qBittorrentu — keď sa súbor stiahne, objaví sa medzi stiahnutými",
  "Stáhnout torrent": "Stiahnuť torrent",
  "Přehrát": "Prehrať",
  "Poslat do mobilu": "Poslať do mobilu",
  "Stáhnout": "Stiahnuť",
  "Zkopírovat odkaz": "Skopírovať odkaz",
  "Klepnutím rozbalíš": "Ťuknutím rozbalíš",
  "Stahování": "Sťahovanie",
  "ve frontě": "vo fronte",
  "čeká na svoje místo ve frontě": "čaká na svoje miesto vo fronte",
  "Spustit hned": "Spustiť hneď",
  "Zrušit stahování": "Zrušiť sťahovanie",
  "Stažené": "Stiahnuté",
  "· volných {0} GB": "· voľných {0} GB",
  "Poslat odkaz do mobilu": "Poslať odkaz do mobilu",
  "Smazat i s titulky": "Zmazať aj s titulkami",
  "Stahování „{0}\" zrušeno": "Sťahovanie „{0}“ zrušené",
  "Stahování „{0}\" spuštěno": "Sťahovanie „{0}“ spustené",
  "Odkaz se nepodařilo vytvořit": "Odkaz sa nepodarilo vytvoriť",
  "Smazat soubor?": "Zmazať súbor?",
  "i s titulky": "aj s titulkami",
  "Když film přišel z torrentu, odebere se i ten z qBittorrentu.": "Keď film prišiel z torrentu, odoberie sa aj ten z qBittorrentu.",
  "Smazáno": "Zmazané",
  "zbývá {0} s": "zostáva {0} s",
  "zbývá {0} min": "zostáva {0} min",
  "zbývá {0} h {1} min": "zostáva {0} h {1} min",
  "Titul zatím žádný zdroj nemá — hlídám ho.": "Titul zatiaľ nemá žiadny zdroj — strážim ho.",
  "{0} sdílí, {1} stahuje": "{0} zdieľa, {1} sťahuje",
  "stáhne se přes qBittorrent, přehrát půjde až potom": "stiahne sa cez qBittorrent, prehrať pôjde až potom",
  "Zobrazit nadpis a ikonu": "Zobraziť nadpis a ikonu",
  "Výchozí přehrávač": "Predvolený prehrávač",
  "Přehrávače na výběr": "Prehrávače na výber",
  "Výchozí mobil": "Predvolený mobil",
  "Senzor stahování": "Senzor sťahovania",
  "Domů": "Domov",
  "Knihovna": "Knižnica",
  "Zatím nic rozkoukaného ani hlídaného.": "Zatiaľ nič rozkukané ani strážené.",
  "Zatím nic v Mém seznamu ani mezi sledovanými seriály.": "Zatiaľ nič v Mojom zozname ani medzi sledovanými seriálmi.",
};

/** Text v jazyce UI z HA (`hass.locale.language`, u starších verzí `hass.language`). */
function nokturnoText(hass, text, ...args) {
  const lang = String((hass && ((hass.locale && hass.locale.language) || hass.language)) || "").toLowerCase();
  const out = lang.startsWith("sk") && SK[text] !== undefined ? SK[text] : text;
  return args.length ? out.replace(/\{(\d+)\}/g, (m, i) => (args[+i] == null ? "" : String(args[+i]))) : out;
}

/** Id senzoru stahování. Výchozí `sensor.nokturno_stahovani` vzniklo z českého názvu;
 *  od 4.0 se název senzoru překládá, takže instalace v jiném jazyce má jiné entity_id —
 *  když nastavené id v HA není, najde se senzor podle jeho atributů. */
function downloadsSensorId(hass, wanted) {
  const st = (hass && hass.states) || {};
  if (st[wanted]) return wanted;
  return Object.keys(st).find((id) =>
    id.startsWith("sensor.nokturno_") && st[id].attributes && st[id].attributes.downloads !== undefined) || wanted;
}

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
      continueItems: null, continueSource: null, stack: [], homeTab: "domov",
    };
    this._started = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._started) this._config.downloads = downloadsSensorId(hass, this._config.downloads);
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
      return;
    }
    // HA sem posílá nový `hass` při změně libovolné entity — na plném dashboardu i
    // několikrát za sekundu. Karta ale závisí jen na senzorech integrace; dokud se ty
    // nezměnily, nemá co dělat. Bez téhle zkratky se při každém tiknutí libovolného
    // senzoru v domě znovu skládalo HTML stažených souborů a procházely všechny
    // entity — na dashboardu se stovkami entit to prohlížeč dovedlo k „stránka
    // neodpovídá“.
    if (!this._root || !this._sensorsChanged()) return;
    this._renderDownloads();
    this._renderProgress();
    // změna sledovaných seriálů, historie, Hlídaných (vlaječka „kontrolovat dál")
    // nebo Mého seznamu → překreslit úvod / detail (a zahodit dočasné stavy)
    const key = JSON.stringify([this._sensorAttr("series"), this._sensorAttr("search_history"),
                                 this._sensorAttr("items"), this._sensorAttr("favourites")]);
    if (key !== this._sensorKey) {
      this._sensorKey = key;
      this._watchOverride = {};
      this._wantOverride = {};
      this._favOverride = {};
      if (this._state.view === "search" || this._state.view === "episodes" || this._state.view === "streams") this._paint();
    }
  }

  /** Id senzorů integrace. Procházet všechny entity při každé změně `hass` je drahé,
   *  proto se seznam drží a obnovuje jen jednou za minutu (nová entita se objeví
   *  nejpozději za tu dobu). Senzor stahování z konfigurace je v seznamu vždy první. */
  _sensorIds() {
    const now = Date.now();
    if (this._sensorIdsCache && now - this._sensorIdsAt < 60000) return this._sensorIdsCache;
    const states = (this._hass && this._hass.states) || {};
    const ids = Object.keys(states).filter((id) =>
      id.startsWith("sensor.") && id.includes("nokturno") && id !== this._config.downloads);
    this._sensorIdsCache = [this._config.downloads, ...ids].filter(Boolean);
    this._sensorIdsAt = now;
    return this._sensorIdsCache;
  }

  /** Změnil se od minula některý senzor integrace? Stavové objekty HA jsou neměnné —
   *  nový vzniká jen při skutečné změně, takže stačí porovnat odkazy. */
  _sensorsChanged() {
    const states = (this._hass && this._hass.states) || {};
    const snap = this._sensorIds().map((id) => states[id]);
    const prev = this._sensorSnap;
    this._sensorSnap = snap;
    return !prev || prev.length !== snap.length || snap.some((s, i) => s !== prev[i]);
  }

  /** Atribut z toho senzoru integrace, který ho má (historie je u stahování, seriály u „Nové díly“). */
  _sensorAttr(name) {
    const states = (this._hass && this._hass.states) || {};
    for (const id of this._sensorIds()) {
      const s = states[id];
      if (s && s.attributes[name] !== undefined) return s.attributes[name];
    }
    return null;
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

  async _clearCache() {
    await this._guard(async () => {
      await this._call("clear_cache", {}, false);
      this._toast(this._t("Cache hledání a streamů vymazána"));
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
    this._state.continueSource = null;
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
      let warnings = [];
      try {
        const res = await this._call("streams", { id: item.id, type, title: item.title, year: item.year });
        streams = res.streams || [];
        warnings = res.warnings || [];
      } catch (err) { /* stejně tak film */ }
      st.streams = streams;
      st.warnings = warnings;
      st.streamTarget = { id: item.id, type };
      st.torrents = false;
      st.fulltext = false;
      st.view = "streams";
    });
  }

  async _loadStreams(data) {
    this._state.stack.push(this._state.view);
    await this._guard(async () => {
      const res = await this._call("streams", { ...data });
      this._state.streams = res.streams || [];
      this._state.warnings = res.warnings || [];
      this._state.streamTarget = data;
      this._state.torrents = false;   // torrenty se u nového titulu hledají znovu
      this._state.fulltext = false;   // stejně tak ruční fulltext
      this._state.view = "streams";
    });
  }

  /** Co poslat službě, aby přehrála/stáhla PRÁVĚ tenhle řádek.
      Posílá se adresa souboru — server si poslední výpis streamů pamatuje a vezme
      z něj celý řádek. Pořadí (`stream`) zůstává jako záloha pro starší integraci:
      server z něj počítal seznam znovu a druhý průchod míval jiné pořadí, takže se
      občas přehrál jiný soubor, než na který se kliklo. */
  _target(stream) {
    const target = { ...this._state.streamTarget };
    if (!target.url) {
      target.stream = stream.index;
      if (stream.url) target.url = stream.url;
    }
    return target;
  }

  async _play(stream, force = false) {
    const entityId = await this._choose("player", force);
    if (!entityId) { if (!this._players().length) this._toast(this._t("Není nastavený žádný přehrávač.")); return; }
    this._state.player = entityId;
    await this._guard(async () => {
      await this._call("play", { ...this._target(stream), entity_id: entityId }, false);
      this._toast(this._t("Spouštím na {0}", this._friendly(entityId)));
    });
  }

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
      než kolik se jich reálně používá. Přehrávač v režimu „první v seznamu"
      vrátí rovnou první, dokud `force` (dlouhý stisk) modal nevynutí. */
  _choose(kind, force = false) {
    const list = kind === "phone" ? this._phones() : this._players();
    const name = (v) => (kind === "phone" ? this._phoneName(v) : this._friendly(v));
    if (!list.length) return Promise.resolve(null);
    if (list.length === 1) return Promise.resolve(list[0]);
    // režim „první v seznamu" — modal jen na vynucení (dlouhý stisk)
    if (kind === "player" && !force && this._multiPlay() === "first") return Promise.resolve(list[0]);
    return this._modal(`<div class="panel">
      <div class="phead">
        <span class="ptitle">${kind === "phone" ? this._t("Do kterého mobilu?") : this._t("Kde přehrát?")}</span>
        <button class="pclose" title="${this._t("Zavřít")}">×</button>
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
        <button class="pclose" title="${this._t("Zavřít")}">×</button></div>
      <div class="ptext">${this._esc(text)}</div>
      <div class="pfoot">
        <button class="pbtn" data-no="1">${this._t("Zpět")}</button>
        <button class="pbtn danger" data-yes="1">${this._esc(this._t(label))}</button>
      </div>
    </div>`, (wrap, close) => {
      wrap.querySelector("[data-no]").addEventListener("click", () => close(null));
      wrap.querySelector("[data-yes]").addEventListener("click", () => close(true));
    }).then((value) => value === true);
  }

  async _download(stream) {
    await this._guard(async () => {
      const res = await this._call("download", this._target(stream));
      this._toast(this._t("Stahuji do {0}", res.path || this._t("úložiště")));
    });
  }

  /** Které fulltextové zdroje jsou nastavené — senzor stahování to hlásí v `sources`. */
  _fulltextSources() {
    const sensor = this._hass && this._hass.states[this._config.downloads];
    const src = (sensor && sensor.attributes.sources) || {};
    const out = [];
    if (src.webshare) out.push("ws");
    if (src.hellspy) out.push("hs");
    if (src.sledujteto) out.push("st");
    if (src.fastshare) out.push("fs");
    return out;
  }

  /** Prowlarr nastavený? Senzor stahování to hlásí v atributu `sources`. */
  _hasTorrents() {
    const sensor = this._hass && this._hass.states[this._config.downloads];
    return !!(sensor && sensor.attributes.sources && sensor.attributes.sources.torrent);
  }

  /** Torrenty se hledají až na vyžádání — trackery odpovídají v řádu sekund
      a u titulu, na který stream je, by to jen zdržovalo otevření detailu. */
  async _findTorrents() {
    this._state.findingTorrents = true;   // vlastní příznak: jinak by tlačítko hlásilo hledání při každé akci
    await this._guard(async () => {
      const res = await this._call("torrents", { ...this._state.streamTarget });
      // torrenty patří nad streamy — kvůli nim se hledalo, tak ať jsou hned vidět
      this._state.streams = (res.streams || []).concat(this._state.streams);
      this._state.torrents = true;
      if (!(res.streams || []).length) this._toast(this._t("Na trackerech nic nenašel"));
    });
    this._state.findingTorrents = false;
    this._paint();
  }

  /** Ruční, uvolněné hledání na WebShare/HellSpy/Sledujteto/FastShare — pro případ, že přísný
      automatický filtr (viz `engine._title_queries`) skutečnou shodu zahodil,
      protože název souboru je neobvyklý. Výsledek karta označí jako neověřený,
      posouzení nechává na uživateli. */
  async _findFulltext() {
    this._state.findingFulltext = true;
    await this._guard(async () => {
      const res = await this._call("fulltext_search", { ...this._state.streamTarget });
      const known = new Set(this._state.streams.map((s) => s.url));
      const added = (res.streams || []).filter((s) => !known.has(s.url));
      this._state.streams = this._state.streams.concat(added);
      this._state.fulltext = true;
      if (!added.length) this._toast(this._t("Fulltext nic dalšího nenašel"));
    });
    this._state.findingFulltext = false;
    this._paint();
  }

  async _downloadTorrent(stream) {
    await this._guard(async () => {
      await this._call("download_torrent", { url: stream.url, name: stream.file || "" }, false);
      this._toast(this._t("Torrent zařazen do stahování"));
    });
  }

  async _toPhone(stream) {
    const target = await this._choose("phone");
    if (!target) { if (!this._phones().length) this._toast(this._t("Nenašel jsem žádný mobil s aplikací Home Assistant.")); return; }
    this._state.phone = target;
    await this._guard(async () => {
      await this._call("send_link", {
        ...this._target(stream),
        notify_service: target,
        name: `${this._state.title || ""} — ${stream.label}`.trim(),
      }, false);
      this._toast(this._t("Odkaz odeslán: {0}", this._phoneName(target)));
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
        this._toast(this._t("Odkaz zkopírován — vlož ho do VLC nebo prohlížeče"));
      } else {
        window.prompt(this._t("Zkopíruj odkaz (Ctrl+C):"), res.url);
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
    // jen odsud jde titul z Pokračovat ve sledování odebrat — potřebuje vědět
    // na kterém Kodi je rozkoukaný a jeho přesný odkaz (`remove_progress` v integraci)
    this._state.continueSource = item.entity_id ? { entity_id: item.entity_id, file: item.file } : null;
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
      if (!found) { this._toast(this._t("Titul se nepodařilo najít.")); this._state.stack.pop(); return; }
      this._state.item = found;
      const streams = await this._call("streams", { id: found.id, type, alt: found.alt, title: found.title, year: found.year });
      this._state.streams = streams.streams || [];
      this._state.warnings = streams.warnings || [];
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
    const sensor = this._hass && this._hass.states[this._config.downloads];
    const zIntegrace = (sensor && sensor.attributes.players) || [];
    if (zIntegrace.length) return zIntegrace;
    return Object.keys((this._hass && this._hass.states) || {})
      .filter((id) => id.startsWith("media_player."));
  }

  /** Co má Přehrát dělat s víc přehrávači — z nastavení integrace. */
  _multiPlay() {
    const sensor = this._hass && this._hass.states[this._config.downloads];
    return (sensor && sensor.attributes.multi_play) || "ask";
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
        /* Hledat + koš vedle sebe v jednom řádku, ne každý zvlášť pod sebou */
        .searchrow { display:flex; gap:8px; align-items:stretch; }
        ha-control-button#go { flex:1; }
        ha-control-button#go ha-icon { --mdc-icon-size:20px; margin-right:4px; vertical-align:-4px; }
        ha-control-button#go .pct { margin-left:4px; font-size:.8rem; opacity:.85; white-space:nowrap; }
        ha-control-button#go::part(base), ha-control-button#go { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        ha-control-button#clearcache { flex:0 0 40px; --control-button-padding: 0; }
        ha-control-button#clearcache ha-icon { --mdc-icon-size:18px; }
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
        .mask { position:absolute; inset:0; display:flex; flex-direction:column; gap:6px;
                align-items:center; justify-content:center;
                background: rgba(0,0,0,.55); color:#fff; border-radius:12px; }
        .mask ha-icon { --mdc-icon-size:34px; }
        .mask .pct { font-size:.85rem; font-weight:600; min-height:1em; }
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
        /* min-height jako tlačítko v .icons (40px) — ať řádek nezmenší, když žádnou ikonu nemá */
        .stream.stacked { grid-template-columns:auto minmax(0, 1fr) auto;
                          grid-template-areas:"tag label icons"; align-items:center; row-gap:0; min-height:40px; }
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
        /* taby úvodní obrazovky — Domů / Knihovna / Stažené */
        .tabs { display:flex; gap:4px; margin-top:12px; border-bottom:1px solid var(--divider-color); }
        .tab { flex:1; display:flex; align-items:center; justify-content:center; gap:5px; border:none;
               background:none; color: var(--secondary-text-color); font:inherit; font-size:.82rem;
               padding:8px 4px; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px; }
        .tab ha-icon { --mdc-icon-size:16px; }
        .tab.active { color: var(--primary-color); border-bottom-color: var(--primary-color); font-weight:500; }
        .tabbadge { background: var(--primary-color); color:#fff; border-radius:9px; min-width:16px;
                    height:16px; padding:0 4px; font-size:.65rem; line-height:16px; text-align:center; }
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
        .warn { display:flex; gap:8px; align-items:flex-start; margin:8px 0 2px; padding:8px 10px; border-radius:10px;
          font-size:.85rem; color:var(--primary-text-color); background:rgba(var(--rgb-warning-color, 255,152,0), .14);
          border:1px solid rgba(var(--rgb-warning-color, 255,152,0), .45); }
        .warn ha-icon { --mdc-icon-size:18px; color:var(--warning-color, #ff9800); flex:none; margin-top:1px; }
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
        /* vlastní vrstva — otáčení kolečka nesmí překreslovat plakát pod maskou */
        .spin { animation: sp 1s linear infinite; display:inline-block; will-change:transform; }
        @keyframes sp { to { transform: rotate(360deg); } }
      </style>
      <ha-card>
        <div class="head"${this._config.show_header ? "" : " hidden"}>
          <ha-icon icon="mdi:movie-search"></ha-icon>
          <h2>${this._esc(this._config.title)}</h2>
        </div>
        <div class="bar" id="search">
          <ha-input id="q" placeholder="${this._t("Název filmu nebo seriálu")}" with-clear></ha-input>
          <div class="searchrow">
            <ha-control-button id="go" title="${this._t("Hledat ve WebShare, Sosáči a Luně")}"><ha-icon icon="mdi:magnify"></ha-icon> ${this._t("Hledat")}<span class="pct"></span></ha-control-button>
            <ha-control-button id="clearcache" title="${this._t("Vymazat cache hledání a streamů")}"><ha-icon icon="mdi:trash-can-outline"></ha-icon></ha-control-button>
          </div>
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
    this._root.querySelector("#clearcache").addEventListener("click", () => this._clearCache());
    this._root.querySelector("#body").addEventListener("click", (e) => this._onClick(e));
    this._root.querySelector("#body").addEventListener("pointerdown", () => {
      // dlouhý stisk (≥ 500 ms) vyvolá výběr přehrávače i v režimu „první v seznamu"
      clearTimeout(this._pressTimer);
      this._longPress = false;
      this._pressTimer = setTimeout(() => { this._longPress = true; }, 500);
    });
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
    if (!this._state.busy) go.querySelector(".pct").textContent = "";
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

  /** Úvodní obrazovka: poslední dotazy nad taby, obsah podle vybraného tabu
      (Domů = rozkoukané + hlídané, Knihovna = Můj seznam + sledované seriály,
      Stažené = probíhající i hotová stahování — kreslí `_renderDownloads`). */
  _home() {
    const st = this._state;
    const sensor = this._hass && this._hass.states[this._config.downloads];
    const history = (sensor && sensor.attributes.search_history) || [];
    let html = history.length
      ? `<div class="chips">${history.map((q, i) => `<button class="chip" data-hist="${i}" title="${this._t("Zopakovat hledání „{0}“", this._esc(q))}">${this._esc(q)}</button>`).join("")}
         <button class="chip x" data-histclear="1" title="${this._t("Smazat historii")}">×</button></div>`
      : `<div class="muted" style="margin-top:10px">${this._t("Zadej název — hledá se ve WebShare, Sosáči i Luně naráz.")}</div>`;
    if (st.continueItems === null) this._loadContinue();
    const cont = st.continueItems || [];
    const trakt = this._traktList();
    const fav = this._favourites();
    const series = this._watchlist();
    const jobs = (sensor && sensor.attributes.downloads) || [];
    const activeCount = jobs.filter((j) => j.status === "running" || j.status === "queued").length;
    const tabs = [
      { id: "domov", label: this._t("Domů"), icon: "mdi:home-outline" },
      { id: "knihovna", label: this._t("Knihovna"), icon: "mdi:bookmark-multiple-outline" },
      { id: "stazene", label: this._t("Stažené"), icon: "mdi:folder-download-outline", badge: activeCount },
    ];
    html += `<div class="tabs">${tabs.map((tb) => `
      <button class="tab${st.homeTab === tb.id ? " active" : ""}" data-hometab="${tb.id}">
        <ha-icon icon="${tb.icon}"></ha-icon> ${tb.label}${tb.badge ? `<span class="tabbadge">${tb.badge}</span>` : ""}
      </button>`).join("")}</div>`;
    if (st.homeTab === "domov") html += this._homeTabDomov(cont, trakt);
    else if (st.homeTab === "knihovna") html += this._homeTabKnihovna(fav, series);
    // obsah tabu Stažené kreslí samostatně `_renderDownloads` do #downloads
    return html;
  }

  _homeTabDomov(cont, trakt) {
    const st = this._state;
    let html = "";
    const manyKodi = new Set(cont.map((c) => c.entity_id)).size > 1;
    if (cont.length) {
      // stejný textový řádkový styl jako „Hlídané"/„Sledované seriály" — bez plakátu.
      // Plakáty/fanart v plné velikosti se tu dřív dekódovaly do paměti prohlížeče
      // (desítky MB na obrázek) a při delším prohlížení to vedlo ke „stránka neodpovídá".
      html += `<div class="section"><ha-icon icon="mdi:play-circle-outline"></ha-icon> ${this._t("Pokračovat ve sledování")}</div>
        <div>${cont.map((c, i) => {
          const loading = st.busy && st.loading === `cont:${i}`;
          return `
          <div class="stream stacked" data-cont="${i}" style="cursor:pointer" title="${this._esc(c.plot)}">
            <span class="tag" style="background:var(--success-color, #2e8b57)">
              <ha-icon icon="${loading ? "mdi:loading" : "mdi:play-circle-outline"}" class="ext${loading ? " spin" : ""}"></ha-icon>
              ${this._t("pokračovat")}</span>
            <span class="label">${this._esc(c.label)}${manyKodi ? ` <span class="muted">· ${this._esc(c.player)}</span>` : ""}</span>
            <span class="icons">
              <ha-icon-button data-contremove="${i}" title="${this._t("Odebrat z Pokračovat ve sledování")}">
                <ha-icon icon="mdi:close-circle-outline"></ha-icon>
              </ha-icon-button>
            </span>
          </div>`;
        }).join("")}</div>`;
    }
    if (trakt.length) {
      html += `<div class="section"><ha-icon icon="mdi:bell-outline"></ha-icon> ${this._t("Hlídané")}</div>
        <div>${trakt.slice(0, 12).map((t, i) => {
          const opening = st.busy && st.loading === `trakt:${i}`;
          const flagging = st.busy && st.loading === `traktflag:${i}`;
          const moving = st.busy && st.loading === `favmove:${i}`;
          // do Mého seznamu jde přesunout jen titul, který má stream a není označený
          // k dalšímu hlídání kvality/zvuku — ten se má dál kontrolovat, ne odložit
          const canMove = t.streams && !t.flagged;
          return `
          <div class="stream stacked" data-trakt="${i}" style="cursor:pointer" title="${t.streams ? this._t("Otevřít streamy — {0} k dispozici", t.streams) : this._t("Zatím žádný stream; hlídám a dám vědět")}">
            <span class="tag" style="background:${t.streams ? (t.flagged ? "var(--warning-color, #b8860b)" : "var(--success-color, #2e8b57)") : "var(--disabled-text-color, #777)"}">
              <ha-icon icon="${opening ? "mdi:loading" : (t.streams ? (t.flagged ? "mdi:flag-outline" : "mdi:play-circle-outline") : (t.pending ? "mdi:radar" : "mdi:clock-outline"))}" class="ext${opening ? " spin" : ""}"></ha-icon>
              ${this._t(t.streams ? (t.flagged ? "kontrolovat dál" : (t.torrent ? "jen torrent" : "lze pustit")) : (t.pending ? "hlídám" : "zatím ne"))}</span>
            <span class="label">${this._esc(t.title)}${t.year ? ` <span class="muted">(${this._esc(t.year)})</span>` : ""}${
              t.streams ? ` <span class="muted">${this._t("· {0} streamů", t.streams)}</span>` : ""}</span>
            ${t.streams ? `<span class="icons">
              ${canMove ? `<ha-icon-button data-favmove="${i}" title="${this._t("Přesunout do Mého seznamu")}">
                <ha-icon icon="${moving ? "mdi:loading" : "mdi:bookmark-plus-outline"}" class="${moving ? "spin" : ""}"></ha-icon>
              </ha-icon-button>` : ""}
              <ha-icon-button data-traktflag="${i}" title="${t.flagged
                ? this._t("Streamy jsou, ale ne v požadované kvalitě/zvuku — kliknutím přestaneš kontrolovat dál")
                : this._t("Streamy jsou, ale ne v požadované kvalitě/zvuku (např. 5.1) — označit, ať se to dál sleduje")}">
                <ha-icon icon="${flagging ? "mdi:loading" : (t.flagged ? "mdi:flag" : "mdi:flag-outline")}" class="${flagging ? "spin" : ""}"></ha-icon>
              </ha-icon-button>
            </span>` : ""}
          </div>`;
        }).join("")}</div>`;
    }
    if (!cont.length && !trakt.length) html += `<div class="muted empty">${this._t("Zatím nic rozkoukaného ani hlídaného.")}</div>`;
    return html;
  }

  _homeTabKnihovna(fav, series) {
    const st = this._state;
    let html = "";
    if (fav.length) {
      html += `<div class="section"><ha-icon icon="mdi:bookmark-multiple-outline"></ha-icon> ${this._t("Můj seznam")}</div>
        <div>${fav.slice(0, 20).map((f, i) => {
          const opening = st.busy && st.loading === `fav:${i}`;
          return `
          <div class="stream stacked" data-fav="${i}" style="cursor:pointer">
            <span class="tag" style="background:var(--primary-color, #555)"><ha-icon icon="${opening ? "mdi:loading" : "mdi:bookmark-outline"}" class="ext${opening ? " spin" : ""}"></ha-icon> ${this._t("Můj seznam")}</span>
            <span class="label">${this._esc(f.title)}</span>
          </div>`;
        }).join("")}</div>`;
    }
    if (series.length) {
      html += `<div class="section"><ha-icon icon="mdi:television-play"></ha-icon> Sledované seriály</div>
        <div>${series.map((w, i) => `
          <div class="stream stacked">
            <span class="tag" style="background:${w.new ? "var(--success-color, #2e8b57)" : "var(--disabled-text-color, #777)"}">
              <ha-icon icon="${w.new ? "mdi:new-box" : "mdi:eye-outline"}" class="ext"></ha-icon>
              ${w.new ? this._t("nový díl") : this._t("sleduji")}</span>
            <span class="label${w.new ? "" : " label--meta"}">${this._esc(w.title)}${w.new
              ? ` — ${w.new.season}x${String(w.new.episode).padStart(2, "0")} ${this._esc(w.new.title)}`
              : `<span class="muted">${w.available
                  ? `${this._t("ke sledování")} ${w.available.season}x${String(w.available.episode).padStart(2, "0")}${w.available.torrent ? ` (${this._t("jen torrent")})` : ""}`
                  : this._t("zatím bez streamu")}${w.latest && (!w.available || w.latest.episode !== w.available.episode || w.latest.season !== w.available.season)
                  ? `, ${this._t("odvysíláno")} ${w.latest.season}x${String(w.latest.episode).padStart(2, "0")}` : ""}</span>`}</span>
            <span class="icons">
              ${w.new ? `<ha-icon-button data-wseen="${i}" title="${this._t("Označit nový díl jako viděný")}"><ha-icon icon="mdi:check"></ha-icon></ha-icon-button>` : ""}
              <ha-icon-button data-wopen="${i}" title="${this._t("Otevřít")}"><ha-icon icon="mdi:folder-play-outline"></ha-icon></ha-icon-button>
              <ha-icon-button data-wremove="${i}" title="${this._t("Přestat sledovat")}"><ha-icon icon="mdi:eye-off-outline"></ha-icon></ha-icon-button>
            </span>
          </div>`).join("")}</div>`;
    }
    if (!fav.length && !series.length) html += `<div class="muted empty">${this._t("Zatím nic v Mém seznamu ani mezi sledovanými seriály.")}</div>`;
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
      this._toast(watching ? this._t("Seriál už nesleduji") : this._t("Nové díly budu hlásit"));
    });
  }

  /** Seznam Hlídaných (ze senzoru „Hlídané"). Titul právě přesunutý do Mého
      seznamu (`_favOverride`) mizí hned, ne až po potvrzení senzorem. */
  _traktList() {
    const over = this._favOverride || {};
    return (this._sensorAttr("items") || []).filter((i) => i && i.id && !over[i.id]);
  }

  /** Můj seznam — lokální oblíbené, sdílené s Kodi/Stremiem. `_favOverride` (přesun
      z Hlídaných i tlačítko přímo v detailu) se projeví hned, senzor to potvrdí
      o chvíli později (stejný vzor jako `_watchlist`/`_watchOverride`). */
  _favourites() {
    const list = [...(this._sensorAttr("favourites") || [])];
    const over = this._favOverride || {};
    const kept = list.filter((f) => over[f.id] !== false).map((f) => (over[f.id] ? { ...f, ...over[f.id] } : f));
    Object.values(over).forEach((f) => { if (f && !kept.some((k) => k.id === f.id)) kept.push(f); });
    return kept;
  }

  _isFavourite(id) {
    if (!id) return false;
    const over = this._favOverride || {};
    if (id in over) return over[id] !== false;
    return (this._sensorAttr("favourites") || []).some((f) => f.id === id);
  }

  /** `items.json`/Kodi ukládá název rovnou s rokem („Matrix (1999)" — `display_name()`),
      aby se v Mém seznamu nezobrazoval rok dvakrát. Optimistický zápis z karty musí
      název sestavit stejně, jinak by po potvrzení senzorem jméno „skoklo". */
  _withYear(title, year) {
    title = String(title || "");
    year = String(year || "");
    return year && !title.includes(year) ? `${title} (${year})` : title;
  }

  /** Položka Hlídaných odpovídající právě otevřenému titulu/dílu — pro vlaječku
      „kontrolovat dál" v hlavičce detailu streamů. */
  _currentTraktEntry() {
    const st = this._state;
    const id = (st.episode && st.episode.id) || (st.item && st.item.id);
    if (!id) return null;
    return this._traktList().find((t) => t.id === id) || null;
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

  /** Hlídané — vlastní seznam i z Traktu; kontroluje se denně, jestli už má stream. */
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
      this._toast(wanted ? this._t("Odebráno ze seznamu") : this._t("Přidáno — dám vědět, až bude ke sledování"));
    });
  }

  /** Můj seznam z hlavičky detailu — nezávisle na Hlídaných, funguje i pro titul,
      který se v Hlídaných vůbec neobjevuje (`favourite_toggle` umí přidat i odebrat). */
  async _toggleFavourite() {
    const target = this._wantTarget();
    if (!target) return;
    const already = this._isFavourite(target.id);
    this._favOverride = this._favOverride || {};
    this._favOverride[target.id] = already
      ? false
      : { id: target.id, title: this._withYear(target.title, target.year), year: target.year,
          poster: target.poster, alt: target.alt, type: target.type };
    this._paint();
    await this._guard(async () => {
      await this._call("favourite_toggle", { id: target.id, type: target.type, title: target.title,
        year: target.year || undefined, alt: target.alt || undefined, poster: target.poster || undefined }, false);
      this._toast(already ? this._t("Odebráno z Mého seznamu") : this._t("Přidáno do Mého seznamu"));
    });
  }

  /** Odebrání z Pokračovat ve sledování — buď u titulu otevřeného odtamtud (`continueSource`,
      nastaví ho `_openContinue`), nebo rovnou ikonou u řádku na úvodní obrazovce (`explicit`).
      `continueSource` se čistí jen v prvním případě, ať nejde poslat dvakrát a na cizí Kodi. */
  async _removeProgress(explicit) {
    const source = explicit || this._state.continueSource;
    if (!source) return;
    if (!explicit) this._state.continueSource = null;
    // odebrat jen tu jednu položku lokálně — nulování celého seznamu vynutí nové
    // načtení (`continueItems === null` v `_home()`) a mezitím sekce zabliká prázdná
    if (this._state.continueItems) {
      this._state.continueItems = this._state.continueItems.filter(
        (c) => !(c.entity_id === source.entity_id && c.file === source.file));
    }
    this._paint();
    await this._guard(async () => {
      await this._call("remove_progress", source, false);
      this._toast(this._t("Odebráno z Pokračovat ve sledování"));
    });
  }

  /** Hlídat titul, který zatím žádný zdroj nemá — stačí název z vyhledávacího pole. */
  /** Databáze filmů (IMDb/TMDB) — najde i tituly, které zatím žádný zdroj nemá. */
  async _searchCatalog() {
    const query = (this._readInput() || this._state.query || "").trim();
    if (!query) {
      // „+“ u prázdných Hlídaných: rovnou nachystat hledání v databázi
      this._state.pendingCatalog = true;
      this._toast(this._t("Napiš název — hledat budu rovnou v databázi filmů."));
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
      if (!st.results.length) this._toast(this._t("V databázi filmů nic takového není."));
    });
  }

  async _wantQuery() {
    const query = (this._state.query || this._readInput() || "").trim();
    if (!query) { this._toast(this._t("Napiš nejdřív název do pole pro hledání.")); return; }
    this._state.searching = true;
    await this._guard(async () => {
      await this._call("want_to_watch", { query, type: this._state.type === "series" ? "series" : "movie" }, false);
      this._toast(this._t("Hlídám „{0}\" — dám vědět, až bude ke sledování", query));
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
    // poslední známý stav ze senzoru — ukáže se hned, živý dotaz na Kodi ho pak
    // na pozadí potichu doplní/opraví (viz `continue_cache` v sensor.py)
    this._state.continueItems = this._sensorAttr("continue_cache") || [];
    try {
      const res = await this._call("continue_watching", {});
      this._state.continueItems = res.items || [];
      if (this._state.view === "search") this._paint();
    } catch (err) { /* Kodi vypnuté — cache zůstává, ať sekce nezmizí */ }
  }

  _results() {
    const st = this._state;
    // databáze filmů je po ruce vždycky — zdroje můžou najít něco jiného, než uživatel hledal
    const home = `<div class="chips">
      <button class="chip" data-back="search" title="${this._t("Zpět na úvodní obrazovku")}"><ha-icon icon="mdi:home-outline" style="--mdc-icon-size:14px"></ha-icon> Úvod</button>
      ${st.catalog
        ? `<button class="chip" data-research="1" title="${this._t("Zpět na výsledky z WebShare, Sosáče a Luny")}"><ha-icon icon="mdi:magnify" style="--mdc-icon-size:14px"></ha-icon> ${this._t("Zpět k výsledkům ze zdrojů")}</button>`
        : `<button class="chip" data-catalog="1" title="${this._t("Hledat v databázi filmů (IMDb/TMDB) — najde i tituly, které zdroje nemají")}"><ha-icon icon="mdi:database-search-outline" style="--mdc-icon-size:14px"></ha-icon> ${this._t("Hledat v databázi filmů")}</button>`}
    </div>`;
    if (!st.results.length) return home + `<div class="muted" style="margin-top:10px">${st.catalog
      ? this._t("V databázi filmů nic takového není.")
      : this._t("Ve zdrojích nic nenalezeno — zkus databázi filmů.")}</div>`;
    const files = st.results.every((r) => r.type === "file");
    const hint = st.catalog
      ? `<div class="muted" style="margin-top:8px">${this._t("Z databáze filmů — klepnutím otevřeš detail; záložkou v něm si titul uložíš mezi hlídané.")}</div>` : "";
    return home + hint + `<div class="grid${files ? " files" : ""}">` + st.results.map((r, i) => `
      <button class="poster" data-open="${i}" title="${this._esc(
        [r.title + (r.year ? ` (${r.year})` : ""), r.description].filter(Boolean).join("\n"))}">
        <span class="thumb">
          <ha-icon icon="mdi:filmstrip"></ha-icon>
          ${r.poster ? `<img src="${this._esc(this._thumb(r.poster))}" decoding="async" referrerpolicy="no-referrer" />` : ""}
          ${st.busy && st.loading === `res:${i}` ? `<span class="mask"><ha-icon class="spin" icon="mdi:loading"></ha-icon><span class="pct"></span></span>` : ""}
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
          <ha-icon-button data-back="back" title="${this._t("Zpět")}"><ha-icon icon="mdi:arrow-left"></ha-icon></ha-icon-button>
          <span class="name">${this._esc(st.item.title)}${st.item.year ? ` <span class="muted">(${st.item.year})</span>` : ""}</span>
          <ha-icon-button data-watch="1" title="${this._isWatched(st.item.id) ? this._t("Přestat sledovat") : this._t("Sledovat nové díly")}">
            <ha-icon icon="${this._isWatched(st.item.id) ? "mdi:eye-check" : "mdi:eye-plus-outline"}"></ha-icon>
          </ha-icon-button>
        </div>
        <span class="picks">
          ${this._pick("season", this._t("Sezóna"), st.seasons.map((n) => ({ value: String(n), label: n === 0 ? this._t("Speciály") : this._t("Sezóna") + " " + n })), String(st.season))}
        </span>
      </div>
      <div>${list.map((e, i) => `
        <div class="ep" data-ep="${i}" title="${this._t("Zobrazit streamy epizody")}">
          <span class="n">${e.season}x${String(e.episode).padStart(2, "0")}</span>
          <span>${this._esc(e.title)}</span>
        </div>`).join("")}</div>`;
  }

  /** Zdroje, které se při hledání přeskočily (vypnutý addon Luny…) — výsledky jsou z ostatních. */
  _streamWarnings() {
    const w = this._state.warnings || [];
    if (!w.length) return "";
    return `<div class="warn"><ha-icon icon="mdi:alert-outline"></ha-icon><span>${
      w.map((line) => this._esc(line)).join("<br>")}<br><span class="muted">${this._t("Přeskočeno — streamy jsou z ostatních zdrojů.")}</span></span></div>`;
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
          <ha-icon-button data-back="back" title="${this._t("Zpět")}"><ha-icon icon="mdi:arrow-left"></ha-icon></ha-icon-button>
          <span class="name">${this._esc(st.title)}${st.item && st.item.year && !st.episode
            && !String(st.title).includes(String(st.item.year)) ? ` <span class="muted">(${st.item.year})</span>` : ""}</span>
          ${st.item ? (() => {
            const saved = this._isWanted((this._wantTarget() || {}).id);
            return `<ha-icon-button data-want="1" title="${saved ? this._t("Odebrat z hlídaných") : this._t("Přidat mezi hlídané")}">
            <ha-icon icon="${saved ? "mdi:bell-check" : "mdi:bell-plus-outline"}"></ha-icon>
          </ha-icon-button>`; })() : ""}
          ${st.item ? (() => {
            const inFav = this._isFavourite((this._wantTarget() || {}).id);
            return `<ha-icon-button data-favtoggle="1" title="${inFav ? this._t("Odebrat z Mého seznamu") : this._t("Přidat do Mého seznamu")}">
            <ha-icon icon="${inFav ? "mdi:bookmark-multiple" : "mdi:bookmark-multiple-outline"}"></ha-icon>
          </ha-icon-button>`; })() : ""}
          ${st.continueSource ? `<ha-icon-button data-removeprogress="1" title="${this._t("Odebrat z Pokračovat ve sledování")}">
            <ha-icon icon="mdi:close-circle-outline"></ha-icon>
          </ha-icon-button>` : ""}
          ${(() => {
            const t = this._currentTraktEntry();
            if (!t || !t.streams) return "";
            const flagging = st.busy && st.loading === "traktflagdetail";
            return `<ha-icon-button data-traktflagdetail="1" title="${t.flagged
              ? this._t("Streamy jsou, ale ne v požadované kvalitě/zvuku — kliknutím přestaneš kontrolovat dál")
              : this._t("Streamy jsou, ale ne v požadované kvalitě/zvuku (např. 5.1) — označit, ať se to dál sleduje")}">
              <ha-icon icon="${flagging ? "mdi:loading" : (t.flagged ? "mdi:flag" : "mdi:flag-outline")}" class="${flagging ? "spin" : ""}"></ha-icon>
            </ha-icon-button>`;
          })()}
        </div>
      </div>` + this._streamWarnings();
    // torrenty jsou poslední možnost, ale tlačítko patří nahoru k ostatnímu ovládání.
    // Hledání trvá pár sekund, takže se točí kolečko i v tlačítku, nejen přes fotku.
    const torrentBtn = st.torrents || !this._hasTorrents() ? "" : `<div class="chips" style="margin:8px 0 2px">
      <button class="chip" data-findtorrents="1"${st.busy ? " disabled" : ""} title="${this._t("Prohledat torrentové trackery přes Prowlarr — trvá pár sekund, proto se hledá až na vyžádání")}">
        <ha-icon class="${st.findingTorrents ? "spin" : ""}" icon="${st.findingTorrents ? "mdi:loading" : "mdi:magnify-scan"}" style="--mdc-icon-size:14px"></ha-icon> ${st.findingTorrents ? this._t("Hledám torrenty…") : this._t("Hledat torrenty")}
      </button></div>`;
    // ruční, uvolněné hledání na fulltextových zdrojích — pro případ, že přísný filtr
    // skutečnou shodu zahodil (nebo naopak, i mezi nalezenými je dobré umět ověřit).
    // Proto je dole i u titulu, který streamy už má — ne jen v prázdném stavu.
    const fsrc = this._fulltextSources();
    const fNames = fsrc.map((k) => ({ ws: "WebShare", hs: "HellSpy", st: "Sledujteto", fs: "FastShare" })[k]);
    const fLabel = fNames.length > 1 ? `${fNames.slice(0, -1).join(", ")} a ${fNames[fNames.length - 1]}` : (fNames[0] || "");
    const fulltextBtn = st.fulltext || !fsrc.length ? "" : `<div class="chips" style="margin:8px 0 2px">
      <button class="chip" data-findfulltext="1"${st.busy ? " disabled" : ""} title="${this._t("Uvolněné hledání podle slov v názvu souboru — najde i to, co přísný filtr zahodí jako podobný, ale jiný titul")}">
        <ha-icon class="${st.findingFulltext ? "spin" : ""}" icon="${st.findingFulltext ? "mdi:loading" : "mdi:text-search"}" style="--mdc-icon-size:14px"></ha-icon> ${st.findingFulltext ? this._t("Hledám…") : this._t("Zkusit fulltext na {0}", fLabel)}
      </button></div>`;
    if (!st.streams.length) return head + torrentBtn + fulltextBtn + `<div class="muted empty">${this._t("Pro tento titul se nenašel žádný stream.")}${
      st.item && st.item.source === "katalog" ? " " + this._t("Ulož si ho záložkou nahoře a dám vědět, jakmile se objeví.") : ""}</div>`;
    const legend = st.streams.some((s) => s.direct)
      ? `<div class="legend"><ha-icon icon="mdi:earth"></ha-icon> = ${this._t("hraje i mimo domácí síť")}</div>` : "";
    return head + torrentBtn + legend + `<div>${st.streams.map((s, i) => `
      <div class="stream" title="${this._esc(this._streamTitle(s))}">
        <span class="tag" style="background:${SOURCE_COLORS[s.source] || (String(s.url || "").startsWith("dav:") ? "var(--success-color, #5f9e3a)" : "var(--disabled-text-color, #777)")}">${this._esc(s.source || "?")}${
          s.direct ? `<ha-icon class="ext" icon="mdi:earth" title="${this._t("Hraje i mimo domácí síť")}"></ha-icon>` : ""}${
          s._loose ? `<ha-icon class="ext" icon="mdi:help-circle-outline" title="${this._t("Neověřeno — z ručního fulltextového hledání, může to být i jiný titul")}"></ha-icon>` : ""}</span>
        <span class="label">${this._esc(String(s.label || "").replace(s.source + "  ·  ", ""))}</span>
        <span class="icons wide">${s.kind === "torrent"
          // torrent není odkaz na video: nedá se přehrát ani poslat do mobilu,
          // nejdřív ho musí stáhnout torrentový klient
          ? `<ha-control-button class="span4" data-torrent="${i}" title="${this._t("Zařadit ke stažení do qBittorrentu — až se soubor stáhne, objeví se mezi staženými")}"><ha-icon icon="mdi:download-network-outline"></ha-icon> ${this._t("Stáhnout torrent")}</ha-control-button>`
          : `<ha-control-button data-play="${i}" title="${this._t("Přehrát")}"><ha-icon icon="mdi:play"></ha-icon></ha-control-button>
          <ha-control-button data-phone="${i}" title="${this._t("Poslat do mobilu")}"><ha-icon icon="mdi:cellphone-play"></ha-icon></ha-control-button>
          <ha-control-button data-dl="${i}" title="${this._t("Stáhnout")}"><ha-icon icon="mdi:download"></ha-icon></ha-control-button>
          <ha-control-button data-link="${i}" title="${this._t("Zkopírovat odkaz")}"><ha-icon icon="mdi:link-variant"></ha-icon></ha-control-button>`}
        </span>
      </div>`).join("")}</div>${fulltextBtn}`;
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
          <img src="${this._esc(art)}" decoding="async" referrerpolicy="no-referrer" />
          ${st.busy ? `<span class="mask"><ha-icon class="spin" icon="mdi:loading"></ha-icon><span class="pct"></span></span>` : ""}
        </span>` : ""}
        ${text ? `<div class="desc${st.descOpen ? " open" : ""}" data-toggle="desc" title="${this._t("Klepnutím rozbalíš")}">${this._esc(text)}</div>` : ""}
      </div>`;
  }

  /** Procenta z atributů senzoru (streamy i hledání) — patchne jen text, bez celého překreslení. */
  _renderProgress() {
    if (!this._root) return;
    const pct = (prog) => (prog && prog.total) ? Math.round((prog.done / prog.total) * 100) + " %" : "";
    const streamText = pct(this._sensorAttr("stream_progress"));
    const searchText = pct(this._sensorAttr("search_progress"));
    const maskEls = this._root.querySelectorAll(".mask .pct");
    // stejný text nepřepisovat — každé přiřazení textContent je nový uzel a překreslení
    // vrstvy i s plakátem pod maskou, a senzor tiká po celou dobu hledání streamů
    const setText = (el, text) => { if (el && el.textContent !== text) el.textContent = text; };
    maskEls.forEach((el) => setText(el, streamText));
    // tlačítko Hledat se točí při každém načítání, ne jen při hledání — ukáže
    // tedy procenta hledání, a když zrovna neběží, procenta načítání streamů
    setText(this._root.querySelector("#go .pct"), searchText || streamText);
  }

  _renderDownloads() {
    if (!this._root) return;
    const box = this._root.querySelector("#downloads");
    const sensor = this._hass && this._hass.states[this._config.downloads];
    const jobs = (sensor && sensor.attributes.downloads) || [];
    const files = (sensor && sensor.attributes.files) || [];
    const activeAll = jobs.filter((j) => j.status === "running" || j.status === "queued");
    // Stažené je vlastní tab na úvodní obrazovce; v detailu titulu by jen odváděly pozornost od streamů.
    const home = !["results", "episodes", "streams"].includes(this._state.view) && this._state.homeTab === "stazene";
    const active = home ? activeAll : [];
    const shown = home ? files : [];
    this._files = shown;
    this._active = active;
    // badge na tabu Stažené: aktualizuje se i mimo _paint, tiky senzoru chodí častěji
    const tabBtn = this._root.querySelector('.tab[data-hometab="stazene"]');
    if (tabBtn) {
      let badge = tabBtn.querySelector(".tabbadge");
      if (activeAll.length) {
        if (!badge) { badge = document.createElement("span"); badge.className = "tabbadge"; tabBtn.appendChild(badge); }
        badge.textContent = activeAll.length;
      } else if (badge) badge.remove();
    }
    if (!active.length && !shown.length) {
      if (!box.hidden || box.firstChild) { box.hidden = true; box.innerHTML = ""; }
      return;
    }
    box.hidden = false;
    box.innerHTML = (active.length ? `<div class="section"><ha-icon icon="mdi:progress-download"></ha-icon> ${this._t("Stahování")}</div>` : "")
      + active.map((j, i) => `
      <div class="dljob">
        <div class="dlrow">
          <span class="muted">${this._esc(j.name)}</span>
          <span class="muted">${j.status === "queued" ? this._t("ve frontě") : j.percent + " %"}</span>
        </div>
        <div class="prog"><div style="width:${j.percent || 0}%"></div></div>
        <div class="dlrow dlinfo">
          <span class="muted">${j.status === "queued" ? this._t("čeká na svoje místo ve frontě")
            : [this._speed(j.speed), this._eta(j.eta),
               j.size ? `${this._size(j.done)} z ${this._size(j.size)}` : ""].filter(Boolean).join(" · ")}</span>
          ${j.status === "queued" ? `<ha-icon-button data-dlstart="${i}" title="${this._t("Spustit hned")}">
            <ha-icon icon="mdi:play"></ha-icon></ha-icon-button>` : ""}
          <ha-icon-button data-dlcancel="${i}" title="${this._t("Zrušit stahování")}">
            <ha-icon icon="mdi:close"></ha-icon></ha-icon-button>
        </div>
      </div>`).join("") + (shown.length ? `
      <div class="section"><ha-icon icon="mdi:folder-download-outline"></ha-icon> ${this._t("Stažené")}
        ${sensor && sensor.attributes.free_gb != null ? `<span class="muted" style="font-weight:400">${this._t("· volných {0} GB", sensor.attributes.free_gb)}</span>` : ""}</div>
      ${shown.map((f, i) => `
        <div class="file" title="${this._esc(f.path)}">
          <span class="label">${this._esc(f.name)}${f.subtitles ? ` <span class="muted">· ${f.subtitles}× titulky</span>` : ""}</span>
          <span class="muted">${this._size(f.size)}</span>
          <span class="icons">
            <ha-icon-button data-fileplay="${i}" title="${this._t("Přehrát")}"><ha-icon icon="mdi:play"></ha-icon></ha-icon-button>
            <ha-icon-button data-fileshare="${i}" title="${this._t("Poslat odkaz do mobilu")}"><ha-icon icon="mdi:cellphone-play"></ha-icon></ha-icon-button>
            <ha-icon-button data-filedel="${i}" title="${this._t("Smazat i s titulky")}"><ha-icon icon="mdi:delete-outline"></ha-icon></ha-icon-button>
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
    box.querySelectorAll("[data-dlstart]").forEach((el) =>
      el.addEventListener("click", () => this._startDownload(this._active[+el.dataset.dlstart])));
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
      this._toast(this._t("Stahování „{0}\" zrušeno", job.name));
    });
  }

  async _startDownload(job) {
    if (!job) return;
    await this._guard(async () => {
      await this._call("start_download", { download_id: job.id }, false);
      this._toast(this._t("Stahování „{0}\" spuštěno", job.name));
    });
  }

  async _playFile(file) {
    const entityId = await this._choose("player");
    if (!entityId) { if (!this._players().length) this._toast(this._t("Není nastavený žádný přehrávač.")); return; }
    this._state.player = entityId;
    await this._guard(async () => {
      await this._hass.callService("media_player", "play_media", {
        entity_id: entityId,
        media_content_type: "video",
        media_content_id: `media-source://media_source/local/${this._folder()}${file.name}`,
      });
      this._toast(this._t("Spouštím na {0}", this._friendly(entityId)));
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
      this._toast(res.url ? this._t("Odkaz odeslán: {0}", this._phoneName(target)) : this._t("Odkaz se nepodařilo vytvořit"));
    });
  }

  async _deleteFile(file) {
    if (!file) return;
    const ok = await this._confirm(this._t("Smazat soubor?"),
      `${file.name}${file.subtitles ? " " + this._t("i s titulky") : ""}. ${this._t("Když film přišel z torrentu, odebere se i ten z qBittorrentu.")}`);
    if (!ok) return;
    await this._guard(async () => {
      await this._call("delete_file", { path: file.path }, false);
      this._toast(this._t("Smazáno"));
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
    if (seconds < 60) return this._t("zbývá {0} s", Math.round(seconds));
    const min = Math.round(seconds / 60);
    if (min < 60) return this._t("zbývá {0} min", min);
    const h = Math.floor(min / 60);
    return this._t("zbývá {0} h {1} min", h, String(min % 60).padStart(2, "0"));
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
    const long = this._longPress;
    this._longPress = false;
    clearTimeout(this._pressTimer);
    const keys = ["open", "back", "ep", "play", "phone", "dl", "link", "toggle", "hist", "histclear", "cont",
                  "contremove", "watch", "wopen", "wremove", "wseen", "trakt", "traktflag", "traktflagdetail",
                  "want", "catalog", "research", "torrent", "findtorrents", "findfulltext", "removeprogress",
                  "favmove", "fav", "favtoggle", "hometab"];
    const hit = event.composedPath().find((el) => el.dataset && keys.some((k) => k in el.dataset));
    if (!hit) return;
    const data = hit.dataset;
    if (data.hometab !== undefined) { st.homeTab = data.hometab; this._paint(); return; }
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
    if (data.contremove !== undefined) {
      const item = st.continueItems[+data.contremove];
      if (!item || !item.entity_id) return undefined;
      return this._removeProgress({ entity_id: item.entity_id, file: item.file });
    }
    if (data.watch !== undefined) return this._toggleWatch();
    if (data.wopen !== undefined) {
      const w = this._watchlist()[+data.wopen];
      return this._openItem({ id: w.id, type: "series", title: w.title, alt: w.alt, poster: w.poster });
    }
    if (data.want !== undefined) return this._toggleWant();
    if (data.removeprogress !== undefined) return this._removeProgress();
    if (data.wantquery !== undefined) return this._wantQuery();
    if (data.catalog !== undefined) return this._searchCatalog();
    if (data.research !== undefined) { st.catalog = false; return this._search(); }
    if (data.traktflag !== undefined) {
      const t = this._traktList()[+data.traktflag];
      if (!t) return undefined;
      st.loading = `traktflag:${data.traktflag}`;
      return this._guard(async () => { await this._call("trakt_flag", { id: t.id }, false); });
    }
    if (data.traktflagdetail !== undefined) {
      const t = this._currentTraktEntry();
      if (!t) return undefined;
      st.loading = "traktflagdetail";
      return this._guard(async () => { await this._call("trakt_flag", { id: t.id }, false); });
    }
    if (data.favmove !== undefined) {
      const t = this._traktList()[+data.favmove];
      if (!t) return undefined;
      // zmizí z Hlídaných a objeví se v Mém seznamu hned, senzor to potvrdí až po chvíli
      this._favOverride = this._favOverride || {};
      this._favOverride[t.id] = { id: t.id, title: this._withYear(t.title, t.year), year: t.year,
                                   poster: t.poster, alt: t.alt, type: t.type };
      st.loading = `favmove:${data.favmove}`;
      return this._guard(async () => {
        await this._call("favourite_add", { id: t.id }, false);
        this._toast(this._t("Přidáno do Mého seznamu"));
      });
    }
    if (data.fav !== undefined) {
      const f = this._favourites()[+data.fav];
      if (!f) return undefined;
      st.loading = `fav:${data.fav}`;
      return this._openItem({ id: f.id, type: f.type || "movie", title: f.title, year: f.year,
                              alt: f.alt || null, poster: f.poster || "" });
    }
    if (data.favtoggle !== undefined) return this._toggleFavourite();
    if (data.trakt !== undefined) {
      const t = this._traktList()[+data.trakt];
      if (!t) return undefined;
      if (t.pending) { this._toast(this._t("Titul zatím žádný zdroj nemá — hlídám ho.")); return undefined; }
      st.loading = `trakt:${data.trakt}`;
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
    if (data.play !== undefined) return this._play(st.streams[+data.play], long);
    if (data.phone !== undefined) return this._toPhone(st.streams[+data.phone]);
    if (data.dl !== undefined) return this._download(st.streams[+data.dl]);
    if (data.link !== undefined) return this._openLink(st.streams[+data.link]);
    if (data.torrent !== undefined) return this._downloadTorrent(st.streams[+data.torrent]);
    if (data.findtorrents !== undefined) return this._findTorrents();
    if (data.findfulltext !== undefined) return this._findFulltext();
    return undefined;
  }

  /** Popis pro tooltip — celý název souboru a co karta zkrátila. */
  _streamTitle(s) {
    const rows = [s.label];
    if (s.file && !s.label.includes(s.file)) rows.push(s.file);
    if (s.subs && s.subs.length) rows.push("titulky: " + s.subs.join(", "));
    if (s.length_min) rows.push(`${s.length_est ? "~" : ""}${Math.floor(s.length_min / 60)}:${String(s.length_min % 60).padStart(2, "0")}`);
    if (s.bitrate) rows.push(`${s.bitrate_est ? "~" : ""}${s.bitrate} Mb/s`);
    if (s.direct) rows.push(this._t("hraje i mimo domácí síť"));
    if (s.kind === "torrent") {
      rows.push(`${s.tracker || "tracker"}: ${this._t("{0} sdílí, {1} stahuje", s.seeders, s.leechers)}`);
      rows.push(this._t("stáhne se přes qBittorrent, přehrát půjde až potom"));
    }
    return rows.filter(Boolean).join("\n");
  }

  /** Text karty v jazyce UI — viz slovník SK nahoře. */
  _t(text, ...args) { return nokturnoText(this._hass, text, ...args); }

  /** Dlaždice v mřížce je ~110×160 px, TMDB ale posílá plakát w500 (Sosáč dokonce
   *  600×900). Prohlížeč si každý drží jako dekódovanou bitmapu — u 24 výsledků
   *  a opakovaného hledání to zbytečně nafukuje paměť záložky. w342 stačí i na HiDPI. */
  _thumb(url) {
    return String(url || "")
      .replace(/(image\.tmdb\.org\/t\/p\/)(w500|w780|original)\//, "$1w342/")
      .replace(/(image\.tmdb\.org\/t\/p\/)w600_and_h900_bestv2\//, "$1w300_and_h450_bestv2/");
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

  _t(text, ...args) { return nokturnoText(this._hass, text, ...args); }

  _phoneOptions() {
    const sensor = this._hass && this._hass.states[downloadsSensorId(this._hass, this._config.downloads || "sensor.nokturno_stahovani")];
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
    const label = {
      title: "Nadpis karty",
      show_header: "Zobrazit nadpis a ikonu",
      player: "Výchozí přehrávač",
      players: "Přehrávače na výběr",
      phone: "Výchozí mobil",
      downloads: "Senzor stahování",
    }[schema.name] || schema.name;
    return this._t(label);
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
