# Nokturno pro Home Assistant

[![Podpoř autora na Ko-fi](https://img.shields.io/badge/Ko--fi-podpo%C5%99%20autora-ff5e5b?logo=ko-fi&logoColor=white)](https://ko-fi.com/matata86)
[![HACS: vlastní repozitář](https://img.shields.io/badge/HACS-vlastn%C3%AD%20repozit%C3%A1%C5%99-41BDF5.svg)](https://hacs.xyz/)

Hledání filmů a seriálů ve **WebShare**, **Sosáči** a **Luně** přímo z Home Assistantu — s přehráním v Kodi, stažením do HA nebo odesláním odkazu do mobilu.

> **Patří k sobě:** [**plugin.video.nokturno**](https://github.com/matata86/plugin.video.nokturno) je klient pro Kodi, tahle integrace jeho protějšek v Home Assistantu. Sdílejí knihovny zdrojů i účty a přehrávání na TV vede přes doplněk, takže si Kodi drží „Pokračovat ve sledování". Streamovací server Luna jde provozovat jako [addon HA](https://github.com/matata86/ha-addons).

<img src="docs/01-uvod.png" width="380" alt="Úvodní obrazovka karty"> <img src="docs/03-streamy.png" width="380" alt="Seznam streamů">

## Obsah

- [Co to umí](#co-to-umí)
- [Instalace](#instalace)
- [Nastavení integrace](#nastavení-integrace)
- [Karta na dashboard](#karta-na-dashboard)
- [Ovládací prvky karty](#ovládací-prvky-karty)
- [Entity](#entity)
- [Služby](#služby)
- [Události](#události)
- [Příklady automatizací](#příklady-automatizací)
- [Jak to funguje uvnitř](#jak-to-funguje-uvnitř)
- [Řešení potíží](#řešení-potíží)

## Co to umí

- **Jedno hledání ve všech zdrojích** — stejný titul z Luny i Sosáče se sloučí do jedné položky, streamy se pak nabídnou ze všech zdrojů naráz. U každého streamu je zdroj, kvalita, název souboru, jazyky zvuku i titulků a velikost.
- **Přehrání v Kodi přes doplněk Nokturno**, takže si Kodi vede „Pokračovat ve sledování" a pamatuje si pozici. Ostatní přehrávače (TV, Cast) dostanou přímé URL.
- **Odeslání do mobilu** — notifikace s odkazem, klepnutím se spustí ve VLC (posílá se jako Android intent s typem videa, jinak by telefon soubor jen stáhl).
- **Stahování do `/media/nokturno`** s frontou a průběhem; hotové soubory jsou vidět v kartě, dají se přehrát, smazat nebo poslat do mobilu odkazem přes Nabu Casa. Titulky se stáhnou vedle videa a mažou se spolu s ním.
- **Odkazy použitelné mimo domácí síť** (ikona 🌐) — přímo z CDN WebShare nebo ze Sosáče; ostatní se přepíšou na adresu z Tailscale/VPN, když ji vyplníš a addon Tailscale běží.
- **Pokračovat ve sledování** ze všech Kodi v domácnosti; klepnutí otevře streamy titulu, takže si vybereš, kde a jak pokračovat.
- **Sledované seriály** — nový díl se hlásí, až když se dá pustit, ne když ho jen eviduje TMDB.
- **Seznam „k zhlédnutí"** — u titulu klepneš na záložku a integrace jednou denně kontroluje, jestli už má stream; jakmile se objeví, přijde oznámení. Přidat jde i titul, který **zatím žádný zdroj nemá** (chystaný film) — hledá se v databázi filmů (IMDb/TMDB přes Cinemetu). Funguje samostatně, **Trakt k tomu není potřeba**.
- **Trakt.tv** (volitelně) — propojení účtu, hlášení přehrávání, zápis do historie a načtení seznamu k zhlédnutí z Traktu. Pozor: Trakt od července 2026 vydává API klíče jen pro VIP účty, takže bez VIP tuhle část nezapneš — vlastní seznam funguje i tak.
- **Rok v dotazu je filtr** — „Pět švestek 2026" najde jen film z roku 2026, ne stejnojmenný o čtyřicet let starší. Číslo, které je součástí názvu („2012", „Blade Runner 2049"), se jako rok nebere. Rok se hlídá i u souborů z fulltextu WebShare, takže se k titulu nepřimíchá stejnojmenný film z jiného roku.
- **Databáze filmů po ruce vždycky** — tlačítko *Hledat v databázi filmů* je u každých výsledků, ne jen když zdroje nic nenajdou. Klepnutím na titul se otevře jeho detail s plakátem a popisem (u chystaných filmů, které popis nikde nemají, aspoň žánr, režie a obsazení) a záložkou v něm si ho uložíš do seznamu k zhlédnutí. Dokud jsi v databázi, hledá tam i tlačítko *Hledat*.
- **Hlasovka jedním krokem** — službám stačí `query` místo ID.

## Instalace

### HACS (doporučeno)

1. HACS → tři tečky vpravo nahoře → **Vlastní repozitáře**
2. URL `https://github.com/matata86/nokturno-ha`, typ **Integrace**
3. Najdi **Nokturno**, nainstaluj a restartuj Home Assistant
4. **Nastavení → Zařízení a služby → Přidat integraci → Nokturno**

Kartu integrace naservíruje sama a sama si ji zapíše do zdrojů Lovelace (`/nokturno/nokturno-card.js?v=…`) — nic nepřidávej ručně. Pokud jsi ji tam dřív přidal z `/local/…`, ten záznam odeber.

### Ručně

Zkopíruj složku `custom_components/nokturno` do své konfigurace a restartuj HA.

> **Po aktualizaci** mobilní aplikaci úplně zavři a otevři znovu, ať si stáhne novou verzi karty.

## Nastavení integrace

Průvodce má dva kroky. **Účty** — vyplň jen zdroje, které chceš používat:

| Pole | Popis |
|---|---|
| WebShare — e-mail, heslo | fulltextové hledání souborů, přímé odkazy z CDN, titulky. Heslo lze zadat i jako uložený salted hash. |
| Streamuj.tv — uživatel, heslo | streamy Sosáče (české tituly a dabing) |
| Luna — adresa, token | katalogy TMDB, metadata a streamy přes [Lunu](https://github.com/matata86/ha-addons); token lze vložit i jako celou instalační URL |

**Předvolby přehrávání** (jdou kdykoli změnit v *Nastavení → Zařízení a služby → Nokturno → Konfigurovat*):

| Pole | Výchozí | K čemu |
|---|---|---|
| Výchozí přehrávač | — | Kodi, na které se pouští, když se v kartě nevybere jiné |
| Preferovaný jazyk zvuku | CZ | takové streamy jdou v seznamu nahoru |
| Preferovat prostorový zvuk | vypnuto | 5.1 a víc má přednost při shodné kvalitě |
| Skrýt SD streamy | vypnuto | vyhodí kvalitu pod 720p |
| Max. velikost streamu (GB) | 0 | 0 = bez omezení |
| Řazení streamů | quality | `quality`, `size_desc`, `size_asc`, `source` |
| Složka pro stahování | `/media/nokturno` | musí být uvnitř `media_dirs`, ať je vidět v Médiích |
| Adresa mimo domácí síť | — | Tailscale/VPN adresa HA (např. `100.94.191.65`); použije se jen když addon Tailscale běží |
| Oznámení | — | notify služba telefonu (`notify.mobile_app_…`); prázdné = oznámení v HA |
| Trakt.tv — Client ID, Secret | — | volitelné; z [trakt.tv/oauth/applications](https://trakt.tv/oauth/applications). **Trakt od 7/2026 vydává API klíče jen s VIP** — bez nich funguje vlastní seznam k zhlédnutí. |

Po vyplnění Traktu spusť službu `nokturno.trakt_auth` — přijde oznámení s kódem, který zadáš na [trakt.tv/activate](https://trakt.tv/activate).

## Karta na dashboard

Přidej kartu **Nokturno** (`custom:nokturno-card`). Má vizuální editor, takže stačí vybrat přehrávače a mobil.

```yaml
type: custom:nokturno-card
title: Nokturno                  # nadpis karty
show_header: true                # false skryje nadpis i ikonu
player: media_player.coreelec    # výchozí přehrávač
players:                         # nabídka v detailu (víc Kodi, TV, Cast…)
  - media_player.coreelec
  - media_player.samsung_tv_q6
phone: notify.mobile_app_muj_telefon   # výchozí mobil pro odeslání odkazu
phones:                          # volitelně ruční seznam; jinak se doplní sám
  - notify.mobile_app_muj_telefon
downloads: sensor.nokturno_stahovani   # senzor s frontou stahování
```

Vše je volitelné: bez `player` se vezme první `media_player`, bez `phone` první telefon s aplikací HA, `downloads` má výchozí hodnotu.

| Pole v editoru | Odpovídá |
|---|---|
| Nadpis karty | `title` |
| Zobrazit nadpis a ikonu | `show_header` |
| Výchozí přehrávač | `player` |
| Přehrávače na výběr | `players` |
| Výchozí mobil | `phone` (nabídka se plní z telefonů, které integrace našla, i se jménem majitele) |
| Senzor stahování | `downloads` |

## Ovládací prvky karty

### Úvodní obrazovka

<img src="docs/01-uvod.png" width="420" alt="Úvodní obrazovka">

- **Pole pro hledání** a tlačítko **Hledat** (během dotazu se v něm točí kolečko); pod nimi přepínač **Filmy / Seriály**. Rok napsaný do dotazu se použije jako filtr — „Duna 2021" vrátí jen film z roku 2021.
- **Štítky** s posledními dotazy — klepnutím se hledání zopakuje, křížek historii smaže.
- **Pokračovat ve sledování** — rozkoukané tituly a další díly ze všech Kodi. U víc zařízení je na dlaždici jméno toho, kde je titul rozkoukaný. Klepnutí otevře **streamy titulu** (id se přečte z odkazu, který Kodi posílá), takže se dá pokračovat na libovolném přehrávači, stáhnout nebo poslat do mobilu.
- **Sledované seriály** — zelený štítek „nový díl" znamená, že další epizoda už má stream. Ikony: ✓ odškrtne nový díl, 📂 otevře seriál, 👁 přestane sledovat.
- **K zhlédnutí** — tituly, které sis uložil záložkou (a případně seznam z Traktu). Zelené „lze pustit" u těch, které už mají stream, „hlídám" u těch, které zatím nikde nejsou; klepnutí otevře streamy. Tlačítko **+** v nadpisu otevře hledání v databázi filmů, kde přidáš i film, který teprve vyjde.
- Dole **Stahování** (fronta s procenty) a **Stažené** — u každého souboru počet stažených titulků, velikost a tři akce: ▶ přehrát na vybraném přehrávači, 📱 poslat odkaz do mobilu, 🗑 smazat (i s titulky). V nadpisu je volné místo na disku.

### Výsledky hledání

<img src="docs/02-vysledky.png" width="420" alt="Výsledky hledání">

Mřížka plakátů s názvem a rokem. Po klepnutí se přes plakát položí kolečko a druhé se točí v tlačítku *Hledat*, dokud se detail nenačte. Vedle tlačítka **Úvod** je vždy **Hledat v databázi filmů** (IMDb/TMDB) — hodí se, když zdroje vrátí něco jiného, než jsi hledal, nebo film teprve vyjde; z těch výsledků klepnutím titul rovnou uložíš do seznamu k zhlédnutí a **Zpět k výsledkům ze zdrojů** tě vrátí. Když hledáš s rokem a zdroje nic z toho roku nemají, výsledek je prázdný — právě proto, aby ti nepodstrčily jiný film. Titul, který má jen Sosáč, dostane plakát z TMDB. Po klepnutí se přes plakát položí kolečko, dokud se streamy nenačtou. **Úvod** vlevo nahoře se vrátí zpět.

### Seriál a epizody

<img src="docs/04-epizody.png" width="420" alt="Epizody seriálu">

Nahoře fanart a popis (klepnutím se rozbalí celý), pod ním název s rokem, šipka zpět, **záložka** (přidá do seznamu k zhlédnutí) a u seriálu **oko** pro sledování nových dílů. Výběr sezóny je pod názvem, epizody se pak vypíšou jako seznam.

### Streamy

<img src="docs/03-streamy.png" width="420" alt="Streamy">

Každý řádek má **štítek zdroje** (WebShare modrý, Sosáč oranžový, Luna fialová) s 🌐 u odkazů, které hrají i mimo domácí síť, **nad** popisem `kvalita · název souboru · zvuk · titulky · velikost`, který jde přes celou šířku karty. Tlačítka jsou pod ním na vlastním řádku, takže nezkracují název. Po najetí myší se v bublině ukáže celý název souboru, titulky, bitrate a jestli hraje venku. Kvalita s vlnovkou (`~4K`) je odhad z velikosti souboru — zdroj ji v názvu neuvedl. Čtyři akce:

| Ikona | Co udělá |
|---|---|
| ▶ | pustí stream na vybraném přehrávači (Kodi přes doplněk, ostatní přímým odkazem) |
| 📱 | pošle odkaz do vybraného mobilu jako notifikaci; klepnutím se otevře ve VLC |
| ⬇ | stáhne do složky pro stahování (i s titulky) |
| 🔗 | zkopíruje přímý odkaz do schránky |

Nad seznamem jsou výběry **Přehrávač** a **Mobil** — platí pro všechny akce v seznamu.

## Entity

| Entita | Stav | Atributy |
|---|---|---|
| `sensor.nokturno_stahovani` | počet běžících stahování | `downloads` (fronta), `files` (hotové soubory), `free_gb`, `directory`, `search_history`, `notify_targets` |
| `sensor.nokturno_nove_dily` | kolik sledovaných seriálů má nový díl | `series` — u každého `latest` (odvysíláno), `available` (nejnovější se streamem), `new`, `checked` |
| `sensor.nokturno_k_zhlednuti` | kolik titulů ze seznamu k zhlédnutí už má stream | `total`, `items` (id, název, rok, počet streamů, nejlepší stream) |

## Služby

Služby označené **↩** vracejí data — volej je s `response_variable`.

### `nokturno.search` ↩
Hledání. `query` (povinné), `type` = `movie` (výchozí) / `series` / `webshare` (soubory přímo z WebShare) / `catalog` / `catalog_series` (databáze filmů — najde i tituly, které zatím nikde nejsou), `limit` (1–60, výchozí 20). Rok v `query` se použije jako filtr roku vydání (u `webshare` zůstává součástí fulltextu).
Vrací `results`: `id`, `type`, `title`, `year`, `poster`, `background`, `description`, `alt` (id téhož titulu v druhém zdroji), `source`.

### `nokturno.streams` ↩
Streamy titulu. `id` nebo `query`, `type`, volitelně `alt`, `series`, `season`, `episode`.
Vrací `streams`: `index`, `label`, `source`, `quality`, `size_gb`, `bitrate`, `langs`, `channels`, `subs`, `direct` (hraje i mimo síť), `url`, `ws_url`, `subtitles`.

### `nokturno.detail` ↩
Detail titulu z databáze filmů podle IMDb id (`id`, `type` = `movie` / `series`): název, rok, plakát, pozadí, popis, hodnocení, žánry, režie a obsazení. Popis se bere z TMDB (česky) a z Cinemety; když ho nemá ani jedna, složí se věta ze žánru, země, režie a hlavních rolí.

### `nokturno.episodes` ↩
Sezóny a epizody seriálu. `id` (povinné), volitelně `season`.

### `nokturno.resolve` ↩
Přímé HTTP URL streamu pro cizí přehrávač. Stejné parametry jako `streams` + `stream` (index) nebo `url`.

### `nokturno.play`
Přehraje. `id` nebo `query`, volitelně `entity_id` (přehrávač), `stream` (index; bez něj nejlepší podle předvoleb), `season`, `episode`, `alt`, `direct: true` (i pro Kodi přímé URL místo doplňku).

### `nokturno.download`
Stáhne do složky pro stahování. Parametry jako `resolve` + `name`. Odmítne soubor, který by se nevešel.

### `nokturno.send_link`
Pošle odkaz do mobilu. `notify_service` (povinné, `notify.mobile_app_…`), dál jako `resolve` + `name`, `title`.

### `nokturno.cancel_download` / `nokturno.delete_file`
Zruší stahování (`download_id`) / smaže stažený soubor i s jeho titulky (`path`, musí být ve složce pro stahování).

### `nokturno.share_file` ↩
Vytvoří dočasný podepsaný odkaz na stažený soubor přes **veřejnou adresu HA** (Nabu Casa, když je k dispozici) a volitelně ho pošle do mobilu. `path` (povinné), `notify_service` (prázdné = cíl z nastavení), `hours` (platnost, výchozí 24).

### `nokturno.continue_watching` ↩
Rozkoukané tituly ze všech Kodi (nebo z jednoho přes `entity_id`). U každé položky `entity_id` zdrojového Kodi a `file` (plugin odkaz, který pokračuje od uložené pozice).

### `nokturno.watch_series` ↩ / `nokturno.check_series` ↩ / `nokturno.mark_seen` ↩
Sledování seriálů: přidat (`id`, `title`, `alt`, `poster`) nebo odebrat (`remove: true`); ruční kontrola nových dílů; zhasnutí označení nového dílu (bez `id` u všech).

### `nokturno.want_to_watch` ↩
Přidá titul do seznamu k zhlédnutí (`id` z hledání nebo z databáze filmů, `type`, `title`, `year`, `alt`, `poster`) nebo ho odebere (`remove: true`). Místo `id` stačí `query` — pak se hlídá název, dokud se titul někde neobjeví. Seznam se kontroluje jednou denně a hned po přidání.

### `nokturno.trakt_auth` ↩ / `nokturno.trakt_watched` ↩ / `nokturno.trakt_watchlist` ↩
Propojení účtu kódem, zápis filmu nebo epizody do historie (`id`, `season`, `episode`, `remove`), načtení seznamu „k zhlédnutí" s kontrolou dostupnosti.

### `nokturno.clear_history`
Smaže historii hledání zobrazenou v kartě.

## Události

| Událost | Kdy | Data |
|---|---|---|
| `nokturno_download_done` | po dostažení | `name`, `path`, `size` |
| `nokturno_new_episode` | nový díl sledovaného seriálu má stream | `id`, `title`, `season`, `episode`, `released` |
| `nokturno_trakt_available` | titul z Traktu nově má stream | `id`, `title`, `type`, `streams` |

## Příklady automatizací

Hlasovka „pusť Matrix na televizi":

```yaml
sequence:
  - action: nokturno.play
    data:
      query: "{{ nazev }}"
      type: movie
      entity_id: media_player.coreelec
```

Jemnější řízení — najdi titul, vyber první stream použitelný i mimo domácí síť a pusť ho:

```yaml
sequence:
  - action: nokturno.search
    data:
      query: "{{ nazev }}"
      type: movie
      limit: 1
    response_variable: nalezeno
  - action: nokturno.streams
    data:
      id: "{{ nalezeno.results[0].id }}"
      alt: "{{ nalezeno.results[0].alt }}"
      type: movie
    response_variable: seznam
  - action: nokturno.play
    data:
      id: "{{ nalezeno.results[0].id }}"
      alt: "{{ nalezeno.results[0].alt }}"
      type: movie
      stream: "{{ (seznam.streams | selectattr('direct') | first).index }}"
      entity_id: media_player.coreelec
```

Když se objeví film ze seznamu Traktu, stáhni ho:

```yaml
triggers:
  - trigger: event
    event_type: nokturno_trakt_available
actions:
  - action: nokturno.download
    data:
      id: "{{ trigger.event.data.id }}"
      type: "{{ trigger.event.data.type }}"
```

## Jak to funguje uvnitř

- **Zdroje jsou rovnocenné** a žádný není povinný. Luna přidává katalogy a metadata, Sosáč české tituly, WebShare fulltext a přímé odkazy.
- **Slučování titulů**: shoda názvu (i originálu) a roku ±1; id protějšku putuje dál jako `alt`, takže se u titulu nabídnou streamy z obou zdrojů.
- **Odkazy mimo síť**: streamy z Luny míří na její adresu v LAN, proto se páruje s fulltextem WebShare podle velikosti (±0,25 GB) a kvality a k položce se přibalí přímý odkaz z CDN. Hledá se pod českým i originálním názvem (z Sosáče nebo z Cinemety). Zbytek se přepíše na `external_host`, pokud addon Tailscale běží.
- **Náhledy Sosáče** jsou od září 2026 mrtvé (404), plakáty se dotahují z TMDB — podle IMDb id, a když chybí, podle názvu a roku.
- **Nový díl seriálu** se hlásí až podle dostupnosti streamu; při zařazení se najde nejnovější sezóna se streamy, dál se sleduje jen posun dopředu.
- Knihovny v `custom_components/nokturno/lib/` jsou kopie z Kodi doplňku, aby se obě aplikace chovaly stejně.

## Řešení potíží

| Problém | Co s tím |
|---|---|
| Karta hlásí „Custom element doesn't exist" / chybu nastavení | aktualizuj na 1.8.5+ (karta se registruje přes zdroje Lovelace, ne přes `extra_module_url` — ten se vyhodnotí dřív, než si frontend nasadí vlastní registr prvků) a stránku načti znovu |
| Karta hlásí chybu nastavení, na desktopu je v pořádku | mobilní aplikaci úplně zavři a otevři znovu (drží si stránku v cache) |
| Karta se načte dvakrát / „already used" | odeber ruční záznam `/local/nokturno/…` ze zdrojů Lovelace |
| Změny v integraci se neprojeví | po zásahu do Pythonu je nutný restart HA Core, reload integrace nestačí |
| U titulu chybí plakát | Sosáč obrázky nemá; pokud nejde dohledat ani přes TMDB, zůstane podklad s ikonou |
| Stream nejde pustit venku | vyber řádek s 🌐, nebo vyplň adresu Tailscale a zkontroluj, že addon běží |
| Trakt hlásí „nepřihlášeno" | spusť `nokturno.trakt_auth` a zadej kód na trakt.tv/activate |
| Odebraný titul zůstal v seznamu k zhlédnutí | opraveno v 1.8.8 — karta čte poslední kontrolu, ta se teď maže spolu s položkou |

## Související projekty

| Projekt | K čemu |
|---|---|
| [plugin.video.nokturno](https://github.com/matata86/plugin.video.nokturno) | klient pro Kodi — stejné zdroje, přes něj se pouští na TV |
| [ha-addons](https://github.com/matata86/ha-addons) | addony pro HA: server Luna a proxy Sosáče pro Nuvio |
| [fns-ha-tweaks](https://github.com/matata86/fns-ha-tweaks) | sdílený vzhled a karty pro Home Assistant |

## Licence

MIT

---

Líbí se ti to? ☕ [Podpoř autora na Ko-fi](https://ko-fi.com/matata86)
