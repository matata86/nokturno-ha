# Nokturno pro Home Assistant

[![Ko-fi](https://img.shields.io/badge/Ko--fi-podpo%C5%99%20autora-ff5e5b?logo=ko-fi&logoColor=white)](https://ko-fi.com/matata86) [![PayPal](https://img.shields.io/badge/PayPal-paypal.me%2Fmatata86-00457C?logo=paypal&logoColor=white)](https://paypal.me/matata86) [![Bitcoin](https://img.shields.io/badge/Bitcoin-BTC-f7931a?logo=bitcoin&logoColor=white)](#podpora)

[![HACS: vlastní repozitář](https://img.shields.io/badge/HACS-vlastn%C3%AD%20repozit%C3%A1%C5%99-41BDF5.svg)](https://hacs.xyz/)

[![Otevřít repozitář v HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=matata86&repository=nokturno-ha&category=integration)
[![Přidat integraci](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=nokturno)

První tlačítko otevře repozitář rovnou v HACS tvojí instance, druhé spustí průvodce nastavením integrace.

Přehrávač **vlastního úložiště** (WebDAV – NAS, Nextcloud, server) přímo z Home Assistantu – s přehráním v Kodi, stažením do HA nebo odesláním odkazu do mobilu. Jako volitelnou doplňkovou službu si zapneš i vyhledávače třetích stran **WebShare**, **Sosáč**, **HellSpy**, **Sledujteto**, **FastShare**, **Přehraj.to**, **CZtor** a **Luna**. Nokturno samo žádný obsah nehostuje ani nešíří.

> **Patří k sobě:** Nokturno je i jako [**doplněk pro Kodi**](https://github.com/matata86/plugin.video.nokturno) (tahle integrace přehrává právě přes něj, takže si Kodi drží „Pokračovat ve sledování“) a jako [**doplněk pro Stremio**](https://github.com/matata86/nokturno-stremio) (i Nuvio, bez Luny). Všechny tři stojí na společném jádru [nokturno-core](https://github.com/matata86/nokturno-core). Server Luna běží jako [addon HA](https://github.com/matata86/ha-addons), jako APK přímo na Android TV boxu nebo jako program pro Windows, Linux, macOS či NAS; vždy potřebuje WebShare VIP.

<img src="https://raw.githubusercontent.com/matata86/nokturno-ha/main/docs/01-domu.jpg" alt="Karta – záložka Domů" width="352"> <img src="https://raw.githubusercontent.com/matata86/nokturno-ha/main/docs/04-streamy.jpg" alt="Karta – streamy titulu" width="352">

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
- [Pomoc](#pomoc)

## Co to umí

- **Vlastní úložiště** – až tři WebDAV složky (NAS, Nextcloud, server), soubory jsou v kartě mezi streamy vždy první
- **Volitelně osm vyhledávačů třetích stran** (WebShare, Sosáč, HellSpy, Sledujteto, FastShare, Přehraj.to, CZtor, Luna) v jednom hledání; stejný titul i soubor se sloučí do jednoho řádku
- **Karta na dashboard** se záložkami Domů, Knihovna a Stažené – hledání, výběr streamu, detail titulu, Pokračovat ve sledování, Hlídané, Můj seznam, sledované seriály, stažené soubory
- **Přehrání v Kodi** přes doplněk Nokturno (Kodi si drží „Pokračovat ve sledování"), stažení do HA nebo odkaz do mobilu
- **Hlídané** – nový díl sledovaného seriálu se ohlásí, až když se dá pustit; hlídat jde i titul, který zatím žádný zdroj nemá (chystaný film), a s příznakem *kontrolovat dál* i díl, u kterého čekáš na vhodnější stream
- **Synchronizace s Kodi** – zhlédnuté, rozkoukané, Můj seznam, historie hledání a Hlídané pro Kodi v domácí síti i mimo ni (kód skupiny)
- **Stav zdrojů** jako senzor (`sensor.nokturno_stav_zdroju`) – vhodný pro automatizace
- **Česky, slovensky i anglicky**, hlasové ovládání jedním krokem

<details>
<summary><b>Všechny funkce podrobně</b></summary>

- **Vlastní úložiště** (od 3.1.1) – až tři WebDAV složky (NAS, Nextcloud, server) v nastavení integrace. Soubory, které k titulu patří, jsou v kartě mezi streamy první se zeleným štítkem. Kodi je přehraje rovnou s heslem v hlavičce, ostatní přehrávače, odkazy do mobilu i stahování jdou přes Home Assistant (podepsaný odkaz na `/api/nokturno/storage/…`, přetáčení funguje, heslo z HA neodejde). Podrobně ve [wiki](https://github.com/matata86/nokturno-ha/wiki/Nastaveni#vlastní-úložiště).
- **Jedno hledání ve všech zapnutých zdrojích** – stejný titul z Luny i Sosáče se sloučí do jedné položky, streamy se pak nabídnou ze všech zdrojů naráz (vlastní úložiště, WebShare, Sosáč, HellSpy, Sledujteto, FastShare, Přehraj.to, CZtor, Luna). Stejný soubor nalezený víc cestami se ukáže jednou. U každého streamu je zdroj, kvalita, název souboru, jazyky zvuku i titulků a velikost.
- **CZtor jako sedmý volitelný zdroj** (od 6.0.0) – placený katalog cztor.com. Zapneš přepínačem v nastavení integrace a spáruješ ho PINem z `cztor.com/activate`; heslo integrace nevidí.
- **Přehraj.to jako osmý volitelný zdroj** (od 7.1.0) – zapnuté ve výchozím stavu, **funguje i bez účtu** (první strana výsledků a překódovaný soubor v 1080p). Nepovinný Premium účet (pole v nastavení integrace) přidá stránkování a původní soubor včetně 4K.
- **Stav zdrojů** (od 6.3.2) – `sensor.nokturno_stav_zdroju` počítá zdroje, které potřebují zásah (vypršelé předplatné, nespárovaný CZtor, Luna, která neběží…); `0` = vše v pořádku.
- **Přehrání v Kodi přes doplněk Nokturno**, takže si Kodi vede „Pokračovat ve sledování" a pamatuje si pozici. Ostatní přehrávače (TV, Cast) dostanou přímé URL.
- **Odeslání do mobilu** – notifikace s odkazem, klepnutím se spustí ve VLC (posílá se jako Android intent s typem videa, jinak by telefon soubor jen stáhl).
- **Stahování do `/media/nokturno`** s frontou, průběhem, rychlostí a odhadem času; přerušené stahování (restart HA, výpadek) se po startu samo dokončí od místa, kde skončilo; hotové soubory jsou vidět v kartě **na úvodní obrazovce**, dají se přehrát, smazat nebo poslat do mobilu odkazem přes Nabu Casa. Titulky se stáhnou vedle videa a mažou se spolu s ním.
- **Odkazy použitelné mimo domácí síť** (ikona 🌐) – přímo z CDN WebShare nebo ze Sosáče; ostatní se přepíšou na adresu z Tailscale/VPN, když ji vyplníš a addon Tailscale běží.
- **Pokračovat ve sledování** ze všech Kodi v domácnosti; klepnutí otevře streamy titulu, takže si vybereš, kde a jak pokračovat. Když zrovna neodpoví ani jedno Kodi (vypnutá), ukáže se naposledy známý stav místo prázdné sekce – přehrání samotné logicky počká, až Kodi zapneš.
- **Synchronizace s Kodi** – zhlédnuté, rozkoukané (i pozice), Můj seznam, historie hledání a Hlídané se sdílí mezi Home Assistantem a všemi Kodi s doplňkem Nokturno. Kodi v domácí síti se připojí **klíčem** z nastavení integrace (v Kodi *Nastavení → Synchronizace → Home Assistant*). Kodi mimo domácí síť (chata, telefon) chodí přes **kód skupiny** `NKT-XXXX-XXXX-XXXX-XXXX`: založí ho první Kodi (*Synchronizace → Založit skupinu / otevřít připojení*) a opíšeš ho i do nastavení integrace. Co se sdílí, zapneš v sekci *Synchronizace s Kodi*. Film rozkoukaný v obýváku pak pokračuje v pracovně na stejném místě.
- **Sledované seriály** – nový díl se hlásí, až když se dá pustit, ne když ho jen eviduje TMDB. Když stream není a máš nastavený Prowlarr, kontrola sáhne i na trackery. Kontrolu stačí udělat na jednom zařízení, výsledek se synchronizuje.
- **Hlídané tituly** – u titulu klepneš na zvonek a integrace jednou denně kontroluje, jestli už má stream; jakmile se objeví, přijde oznámení. Přidat jde i titul, který **zatím žádný zdroj nemá** (chystaný film) – hledá se v databázi filmů (IMDb/TMDB přes Cinemetu). Funguje samostatně, **Trakt k tomu není potřeba**.
- **Trakt.tv** (volitelně) – propojení účtu, hlášení přehrávání, zápis do historie a načtení seznamu k zhlédnutí z Traktu. Vlastní aplikaci na Traktu nepotřebuješ: spusť službu `nokturno.trakt_auth` a kód zadej na webu Traktu. Jde to i s free účtem (ten má nejvýš dvě připojené aplikace naráz).
- **Rok v dotazu je filtr** – „Pět švestek 2026" najde jen film z roku 2026, ne stejnojmenný o čtyřicet let starší. Číslo, které je součástí názvu („2012", „Blade Runner 2049"), se jako rok nebere. Rok se hlídá i u souborů z fulltextu WebShare, takže se k titulu nepřimíchá stejnojmenný film z jiného roku.
- **Jedno hledání pro filmy i seriály** – přepínač *Filmy / Seriály* se objeví, jen když dotaz sedí na obojí; jinak karta rovnou ukáže to, co našla. Stejně to funguje i v doplňku do Kodi.
- **Databáze filmů po ruce vždycky** – tlačítko *Hledat v databázi filmů* je u každých výsledků, ne jen když zdroje nic nenajdou. Klepnutím na titul se otevře jeho detail s plakátem a popisem (u chystaných filmů, které popis nikde nemají, aspoň žánr, režie a obsazení) a záložkou v něm si ho uložíš do seznamu k zhlédnutí. Dokud jsi v databázi, hledá tam i tlačítko *Hledat*.
- **Torrenty jako poslední možnost** – když na titul nikde stream není, tlačítko *Hledat torrenty* pod seznamem prohledá trackery přes [Prowlarr](https://prowlarr.com/) a nalezené torrenty předá qBittorrentu. Hledá se **až na vyžádání**, protože trackery odpovídají v řádu sekund a otevření detailu by to zdržovalo. Vypnuté, dokud Prowlarr nevyplníš.
- **Hlasovka jedním krokem** – službám stačí `query` místo ID.
- **Česky, slovensky i anglicky** – formulář nastavení, popisy všech služeb (*Vývojářské nástroje → Akce*) i názvy senzorů podle jazyka Home Assistantu. Instalace z doby před 4.0 si ponechají původní `entity_id` senzorů (`sensor.nokturno_stahovani`…); karta si senzor stahování najde i pod jiným jménem.
- **Oprava přihlášení k WebShare** – když WebShare odmítne heslo, integrace se přepne do stavu *vyžaduje opravu* a nabídne zadání údajů znovu (heslo se před uložením ověří). Výpadek sítě tohle nespouští.
- **Diagnostika bez tajemství** – *Stáhnout diagnostiku* u integrace vynechá hesla, účty i klíče; hesla se ve formuláři zadávají skrytě.

</details>

## Instalace

### HACS (doporučeno)

1. HACS → tři tečky vpravo nahoře → **Vlastní repozitáře** (nebo [![Otevřít repozitář v HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=matata86&repository=nokturno-ha&category=integration))
2. URL `https://github.com/matata86/nokturno-ha`, typ **Integrace**
3. Najdi **Nokturno**, nainstaluj a restartuj Home Assistant
4. **Nastavení → Zařízení a služby → Přidat integraci → Nokturno** (nebo [![Přidat integraci](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=nokturno))

Kartu integrace naservíruje sama a sama si ji zapíše do zdrojů Lovelace (`/nokturno/nokturno-card.js?v=…`) – nic nepřidávej ručně. Pokud jsi ji tam dřív přidal z `/local/…`, ten záznam odeber.

### Ručně

Zkopíruj složku `custom_components/nokturno` do své konfigurace a restartuj HA.

> **HACS neukazuje novou verzi?** Data ručně přidaných repozitářů obnovuje jen jednou za 48 hodin – vynuť to v HACS → Nokturno → tři tečky → **Update information**.

> **Po aktualizaci** mobilní aplikaci úplně zavři a otevři znovu, ať si stáhne novou verzi karty.

## Nastavení integrace

Vlastní úložiště (WebDAV) nastavíš přímo v tomhle formuláři – nic dalšího není potřeba. Formulář má sbalitelné sekce **Přehrávání**, **Zdroje a účty**, **Vlastní úložiště**, **Torrenty**, **Stahování a odkazy**, **Synchronizace s Kodi** a **Ostatní**; vyplň jen to, co chceš používat. Hesla se zadávají skrytě a ukládají se odděleně od předvoleb.

<img src="https://raw.githubusercontent.com/matata86/nokturno-ha/main/docs/05-nastaveni.jpg" alt="Nastavení integrace – sekce Přehrávání" width="400">

Volitelné vyhledávače (sekce *Zdroje a účty*):

| Pole | Bez čeho to nejde | Co tím získáš |
|---|---|---|
| WebShare – e-mail, heslo | placený účet WebShare | fulltextové hledání souborů, streamy u titulů z Luny, přímé odkazy z CDN (hrají i mimo domácí síť), titulky. Heslo lze zadat i jako uložený salted hash z Kodi doplňku. |
| Streamuj.tv – uživatel, heslo | účet Streamuj.tv (přehrávač Sosáče) | streamy Sosáče, tedy české tituly a dabing. Katalogy a hledání jdou z veřejných exportů, přihlášení je potřeba až na přehrání. |
| HellSpy – jen přepínač | nic, rozhraní je veřejné | další soubory k titulu z hellspy.to. Nabízí se původní soubor, ne překódování, takže velikost i kvalita v seznamu odpovídají tomu, co se přehraje. Rychlost bez účtu kolísá, naměřeno 37 až 400 Mb/s. |
| Sledujteto – e-mail a heslo (od 3.0.0) | účet Sledujteto, k přehrání **Premium** | další soubory k titulu ze sledujteto.cz; rozlišení, kanály a kodek zvuku posílá přímo jejich API, soubor se nečte |
| FastShare / Sdilej.cz – uživatel, heslo a *účet z* (od 5.1.0) | účet FastShare nebo Sdilej.cz (volba *účet z*, od 8.4.0), přehrání z **kreditu** nebo neomezeného tarifu | další soubory k titulu z fastshare.cz; hledá se i bez účtu, zvuk se dočte z hlavičky souboru (pár set kB z kreditu, jednou za 30 dní). Mimo Kodi jde soubor přes HA – přehrávač cookie z přihlášení neumí poslat |
| Přehraj.to – přepínač, e-mail a heslo (od 7.1.0) | nic, zapnuté ve výchozím stavu | další soubory k titulu z prehraj.to. Bez účtu první strana výsledků a překódovaný soubor v 1080p, s Premium účtem stránkování a původní soubor včetně 4K. |
| CZtor – přepínač a PIN (od 6.0.0) | placený účet cztor.com | další soubory k titulu; po zapnutí se otevře krok s PINem z `cztor.com/activate`, tokeny se ukládají do `.storage/nokturno/`, heslo ne |
| Luna – adresa, token | běžící server [Luna](https://github.com/matata86/ha-addons) v síti: addon HA, APK na Android TV boxu nebo program pro Windows/Linux/macOS/NAS; vždy s WebShare VIP | katalogy a metadata z TMDB (české názvy, popisy, plakáty) a streamy z WebShare přes Lunu. Token lze vložit i jako celou instalační URL, adresa se z ní vytáhne sama. |
| TMDB – API klíč | zdarma klíč z [themoviedb.org](https://www.themoviedb.org/signup) (ikona profilu → *Nastavení* → *API* → *Request an API Key* → *Developer* → zkopírovat **API Key (v3 auth)**) | vlastní databáze filmů a seriálů – jakmile je klíč vyplněný, katalog i hledání jedou přes TMDB **přednostně i před Lunou** (umí i český popis a obsazení, ne jen název); Luna zůstává zdrojem streamů. Bez klíče je primární Luna (je-li dostupná), jinak zdarma veřejný katalog Sosáče a nakonec Cinemeta (obojí bez popisu, nebo jen anglicky). |

Stačí jeden zdroj – integrace se přizpůsobí tomu, co je vyplněné. Katalog i hledání titulů fungují dokonce i úplně bez jediného vyplněného zdroje (viz [Vlastní databáze filmů a seriálů](#vlastní-databáze-filmů-a-seriálů) níž). HellSpy a Přehraj.to jsou zapnuté a vypínají se v sekci *Zdroje a účty*.

### Vlastní databáze filmů a seriálů

Katalog a hledání titulů nepotřebují žádný zdroj. Použije se řetězec zdrojů metadat v tomhle pořadí (každý se zkusí, jen když předchozí nic nevrátil):

1. **TMDB** – s vlastním zdarma klíčem (viz tabulka výš, sekce *Ostatní*) má přednost **i před Lunou** – umí česky i to, co Luna neřekne (popis, obsazení). Luna zůstává zdrojem streamů, ne metadat.
2. **Luna** – bez klíče TMDB, když je dostupná
3. **Veřejný katalog Sosáče** – bez TMDB i Luny, bez účtu, české tituly a žánry, ale bez popisu
4. **Cinemeta** – poslední záchrana, funguje vždy, ale jen anglicky

Streamy samotné (úložiště, WebShare, Sosáč, HellSpy, Sledujteto, FastShare, Přehraj.to, CZtor, Luna) se hledají zvlášť – vlastní databáze řeší jen „co je to za titul", ne odkud stream stáhnout. Tlačítko **Hledat v databázi filmů** (viz [Databáze filmů](#databáze-filmů) níž) běží nezávisle na tomhle pořadí – vždy přes Cinemetu, protože slouží k dohledání titulů, které žádný zdroj (ani vlastní databáze) ještě nezná.

**Ostatní volby** (jdou kdykoli změnit v *Nastavení → Zařízení a služby → Nokturno → Konfigurovat*):

| Pole | Hodnoty | Výchozí | Co dělá |
|---|---|---|---|
| Výchozí přehrávače (Kodi) | seznam entit `media_player` | – | přehrávače, ze kterých karta nabízí výběr. Kodi se pozná z registru entit, takže se do něj pouští přes doplněk Nokturno a titul si drží pozici; ostatní přehrávače dostanou přímý odkaz. Volání služby `nokturno.play` bez `entity_id` spustí přehrávání na všech. |
| Přehrávání při více přehrávačích | zeptat se / první v seznamu | zeptat se | *Zeptat se* ukáže po klepnutí na Přehrát okno s výběrem přehrávače. *První v seznamu* spustí rovnou na prvním a výběr vyvolá dlouhý stisk tlačítka. S jediným přehrávačem se karta neptá. |
| Preferovaný jazyk zvuku | CZ, SK, EN, … | CZ | streamy s tímhle zvukem jdou v seznamu nahoru. Neodfiltrují se ostatní, jen se seřadí. |
| Preferovat prostorový zvuk | ano / ne | ne | při shodné kvalitě jde nahoru 5.1 a víc. |
| Skrýt SD streamy | ano / ne | ne | vyhodí ze seznamu všechno pod 720p. |
| Max. datový tok (Mb/s) | číslo, 0 = bez omezení | 0 | přepočítá se na GB podle stopáže právě otevřeného titulu – pevné GB nedávaly smysl, devadesátiminutová pohádka a tříhodinový epos se stejnou rychlostí vyjdou na jinou velikost. |
| Řazení streamů | `quality`, `size_desc`, `size_asc`, `source` | `size_desc` | `size_desc` dá nahoru největší soubory, `quality` řadí podle rozlišení (odhad z velikosti u souborů bez kvality v názvu se pozná podle vlnovky), `source` seskupí podle zdroje. |
| Složka pro stahování | cesta | `/media/nokturno` | musí být uvnitř `media_dirs`, jinak stažené soubory neuvidíš v Médiích. Titulky se ukládají vedle videa se stejným názvem. |
| Adresa mimo domácí síť | IP nebo doména | – | Tailscale/VPN adresa HA (např. `100.x.y.z`). Použije se při odesílání odkazu a při `resolve`, a jen tehdy, když addon Tailscale skutečně běží – integrace si to ověřuje přes Supervisor. |
| Oznámení | notify služba | – | kam chodí hlášky o dokončeném stahování, novém dílu a nově dostupném titulu (`notify.mobile_app_…`). Prázdné = trvalé oznámení v HA. |
| Trakt.tv – vlastní Client ID, Secret | z [developer.trakt.tv](https://developer.trakt.tv/apps/new) | prázdné | nepovinné. Prázdné = použije se aplikace Nokturna a stačí služba `nokturno.trakt_auth`. Vyplň jen, když máš vlastní aplikaci. |
| Prowlarr – adresa, API klíč | `http://IP:9696` a klíč ze *Settings → General* | – | hledání na torrentových trackerech. **Dokud není vyplněné obojí, torrenty se v kartě vůbec nenabídnou.** Prowlarr drží přihlášení k trackerům za tebe, takže integrace nemusí řešit HTML jednotlivých stránek. |
| qBittorrent – adresa, jméno, heslo | `http://IP:9091` | – | kam se předávají nalezené torrenty. Jméno a heslo nech prázdné, když má web UI povolenou místní síť bez přihlášení. Stažené video skončí ve složce pro stahování. |
| Klíč pro Kodi v domácí síti | text | vygeneruje se | opiš ho do Kodi doplňku (*Nastavení → Synchronizace → Home Assistant*) – Kodi v domácí síti se pak synchronizuje přímo přes tuhle integraci (`POST /api/nokturno/sync`). Klíč jde kdykoli změnit, pak ho přepiš i v Kodi. |
| Kód skupiny | `NKT-XXXX-XXXX-XXXX-XXXX` | prázdné | kód skupiny, kterou založilo první Kodi (*Synchronizace → Založit skupinu / otevřít připojení*). Home Assistant se tím stane členem skupiny a synchronizuje se i s Kodi mimo domácí síť. Prázdné = jen Kodi v domácí síti. |
| Synchronizovat … | ano / ne | ano | co se sdílí: zhlédnuto a rozkoukanost, Můj seznam, historie hledání, Hlídané (sledované seriály a hlídané tituly i s příznakem *kontrolovat dál*). |
| Upozornit na konec předplatného (dny) | 0–14, 0 = vypnuto | 5 | kolik dní předem hlásit blížící se konec VIP na WebShare. Kontroluje se dvanáctkrát denně, upozornění (přes stejnou `notify` službu jako stahování) chodí nejvýš jednou za den – po vypršení dál, dokud předplatné neprodloužíš. Stejná logika běží i v Kodi doplňku. |
| Anonymní statistiky | ano / ne | ano | posílá jednou za šest hodin náhodný identifikátor, verzi, platformu, jazyk, zapnuté zdroje (jen přepínače) a počet zobrazení streamů podle titulu. Přihlašovací údaje, adresy ani obsah hledání neodcházejí. Po vypnutí se dál posílá jen náhodný identifikátor a verze integrace, aby bylo vidět, že instalace žije. |

Po vyplnění Traktu spusť službu `nokturno.trakt_auth` – přijde oznámení s kódem, který zadáš na [trakt.tv/activate](https://trakt.tv/activate).

Dny do konce předplatného WebShare (a datum, kdy končí) jsou taky v atributu `subscription` senzoru *Stahování* (`sensor.nokturno_stahovani`) – pro vlastní kartu nebo automatizaci.

## Karta na dashboard

Přidej kartu **Nokturno** (`custom:nokturno-card`). Má vizuální editor, takže stačí vybrat přehrávače a mobil.

```yaml
type: custom:nokturno-card
title: Nokturno                  # nadpis karty
show_header: true                # false skryje nadpis i ikonu
players:                         # nabídka v detailu (víc Kodi, TV, Cast…)
  - media_player.coreelec
  - media_player.samsung_tv_q6
phone: notify.mobile_app_muj_telefon   # výchozí mobil pro odeslání odkazu
phones:                          # volitelně ruční seznam; jinak se doplní sám
  - notify.mobile_app_muj_telefon
downloads: sensor.nokturno_stahovani   # senzor s frontou stahování
```

Vše je volitelné: bez `players` se nabídnou přehrávače z nastavení integrace (a když tam žádné nejsou, všechny `media_player`), bez `phone` první telefon s aplikací HA, `downloads` má výchozí hodnotu.

| Pole v editoru | Odpovídá |
|---|---|
| Nadpis karty | `title` |
| Zobrazit nadpis a ikonu | `show_header` |
| Přehrávače na výběr | `players` |
| Výchozí mobil | `phone` (nabídka se plní z telefonů, které integrace našla, i se jménem majitele) |
| Senzor stahování | `downloads` |

## Ovládací prvky karty

### Úvodní obrazovka

<img src="https://raw.githubusercontent.com/matata86/nokturno-ha/main/docs/01-domu.jpg" alt="Karta – záložka Domů" width="352"> <img src="https://raw.githubusercontent.com/matata86/nokturno-ha/main/docs/02-knihovna.jpg" alt="Karta – záložka Knihovna" width="352">

Nahoře **pole pro hledání**, pod ním záložky **Domů**, **Knihovna** a **Stažené**.

- **Pole pro hledání** a tlačítko **Hledat** (během dotazu se v něm točí kolečko). Přepínač **Filmy / Seriály** se ukáže až u výsledků, a jen když dotaz našel obojí. Rok napsaný do dotazu se použije jako filtr – „Duna 2021" vrátí jen film z roku 2021.
- **Štítky** s posledními dotazy (nejvýš 10, sdíleno s doplňkem pro Kodi) – klepnutím se hledání zopakuje, křížek historii smaže.
- **Pokračovat ve sledování** (záložka *Domů*) – rozkoukané tituly a další díly ze všech Kodi. U víc zařízení je na dlaždici jméno toho, kde je titul rozkoukaný. Klepnutí otevře **streamy titulu** (id se přečte z odkazu, který Kodi posílá), takže se dá pokračovat na libovolném přehrávači, stáhnout nebo poslat do mobilu.
- **Hlídané** (záložka *Domů*) – tituly, které sis uložil zvonkem (a případně seznam z Traktu). Zvonek v detailu **dílu** uloží ten díl, ne celý seriál; v seznamu je pak i s číslem („Okresní přebor · 1x01“) a klepnutí otevře rovnou jeho streamy. Zelené „lze pustit“ u těch, které už mají stream, „jen torrent“ u těch, které leží jen na trackerech, „hlídám“ u těch, které zatím nikde nejsou. Titul, který teprve vyjde, přidáš přes **Hledat v databázi filmů** u výsledků hledání.
- **Můj seznam** a **sledované seriály** (záložka *Knihovna*) – zelený štítek „nový díl“ znamená, že další epizoda už má stream. Díl, který je zatím jen na trackeru, je označený „(jen torrent)“ – pustit ho znamená napřed ho stáhnout.
- Záložka **Stažené** – u běžícího souboru procenta, rychlost, odhad zbývajícího času, kolik už je staženo z celku a křížek, kterým se stahování zruší. Pod tím hotové soubory – u každého počet stažených titulků, velikost a tři akce: ▶ přehrát na vybraném přehrávači, 📱 poslat odkaz do mobilu, 🗑 smazat (i s titulky). V nadpisu je volné místo na disku.

### Výsledky hledání

Mřížka plakátů s názvem a rokem. Po klepnutí se přes plakát položí kolečko a druhé se točí v tlačítku *Hledat*, dokud se detail nenačte. Vedle tlačítka **Úvod** je vždy **Hledat v databázi filmů** (IMDb/TMDB) – hodí se, když zdroje vrátí něco jiného, než jsi hledal, nebo film teprve vyjde; z těch výsledků klepnutím titul rovnou uložíš do seznamu k zhlédnutí a **Zpět k výsledkům ze zdrojů** tě vrátí. Když hledáš s rokem a zdroje nic z toho roku nemají, výsledek je prázdný – právě proto, aby ti nepodstrčily jiný film. Titul, který má jen Sosáč, dostane plakát z TMDB. **Úvod** vlevo nahoře se vrátí zpět.

### Jak se hledá

| Situace | Co karta udělá |
|---|---|
| Napíšeš název | zeptá se Luny i Sosáče naráz a stejný titul z obou spojí do jedné dlaždice |
| Napíšeš rok („Duna 2021") | rok odřízne z dotazu a použije ho jako filtr; projdou tituly z toho roku a ty, u kterých zdroj rok neuvádí |
| Číslo patří k názvu („Blade Runner 2049", „2012") | rok v budoucnosti se nebere jako filtr, hledá se celý název |
| Dotaz sedí jen na seriál (nebo jen na film) | výsledky se ukážou rovnou, přepínač *Filmy / Seriály* zůstane skrytý |
| Dotaz sedí na filmy i seriály („Matrix") | nad výsledky se objeví přepínač; přepnutí jen přepne seznam, nehledá se znovu |
| Zdroje nenajdou nic | tlačítko **Hledat v databázi filmů** je hned vedle **Úvod**; databáze zná i chystané tituly |
| Jsi v databázi filmů | další hledání zůstane v ní, dokud se nevrátíš tlačítkem **Zpět k výsledkům ze zdrojů** nebo na **Úvod** |
| Klepneš na titul z databáze | otevře se detail s plakátem a popisem; streamy tam většinou nejsou, proto je nahoře záložka pro uložení do seznamu k zhlédnutí |
| Otevřeš titul ze seznamu k zhlédnutí | plakát a popis se dotáhnou z databáze filmů, i když je zdroje neznají |

### Databáze filmů

Tlačítko **Hledat v databázi filmů** se ptá Cinemety (IMDb/TMDB), takže najde i tituly, které zdroje vůbec nemají – třeba film, který teprve vyjde. Klepnutí na výsledek otevře detail:

- **plakát a popis** – popis se bere z TMDB (česky), a když ho nemá ani TMDB ani IMDb, složí se věta ze žánru, země, režie a hlavních rolí;
- **streamy**, pokud už nějaké existují, jinak hláška, že žádný není;
- **záložka** vpravo nahoře uloží titul do seznamu k zhlédnutí – pak se jednou denně kontroluje a jakmile se stream objeví, přijde oznámení.

Názvy jsou v databázi vedené mezinárodním přepisem („Sunday League - Pepik Hnatek's Final Match"). Podle IMDb id se k nim dohledá český název z TMDB a pod ním se pak hledají streamy – jinak by u českých filmů z databáze žádné nebyly. U úplně čerstvých titulů, které TMDB ještě nezná, zůstane přepis.

### Seriál a epizody

<img src="https://raw.githubusercontent.com/matata86/nokturno-ha/main/docs/03-epizody.jpg" alt="Epizody seriálu" width="352">

Nahoře fanart a popis (klepnutím se rozbalí celý), pod ním název s rokem, šipka zpět, **záložka** (přidá do seznamu k zhlédnutí) a u seriálu **oko** pro sledování nových dílů. Výběr sezóny je pod názvem, epizody se pak vypíšou jako seznam.

### Streamy

<img src="https://raw.githubusercontent.com/matata86/nokturno-ha/main/docs/04-streamy.jpg" alt="Streamy" width="352">

Každý řádek má **štítek zdroje** (WebShare modrý, Sosáč oranžový, Luna fialová, HellSpy červený, Sledujteto tyrkysový, FastShare zlatý, Přehraj.to růžový; vlastní úložiště zelený se svým názvem) s 🌐 u odkazů, které hrají i mimo domácí síť, **nad** popisem `kvalita · název souboru · zvuk · titulky · velikost`, který jde přes celou šířku karty. Tlačítka jsou pod ním na vlastním řádku, takže nezkracují název. Po najetí myší se v bublině ukáže celý název souboru, titulky, bitrate a jestli hraje venku. Kvalita s vlnovkou (`~4K`) je odhad z velikosti souboru – zdroj ji v názvu neuvedl. Čtyři akce:

| Ikona | Co udělá |
|---|---|
| ▶ | pustí stream na vybraném přehrávači (Kodi přes doplněk, ostatní přímým odkazem) |
| 📱 | pošle odkaz do vybraného mobilu jako notifikaci; klepnutím se otevře ve VLC |
| ⬇ | stáhne do složky pro stahování (i s titulky); průběh je vidět dole v kartě i s rychlostí a odhadem času |
| 🔗 | zkopíruje přímý odkaz do schránky (na `http` schránka přes prohlížeč nejde, tak se odkaz nabídne v okně k ručnímu zkopírování) |

Kam se pouští nebo posílá se vybírá **až u akce**: klepnutí na ▶ nebo 📱 otevře uprostřed karty malý výběr přehrávačů, respektive mobilů. Zavře se křížkem, klávesou Esc nebo klepnutím vedle. Stejným způsobem se potvrzuje mazání staženého souboru. Když je k dispozici jediný cíl, karta se neptá a rovnou ho použije. Volba si pamatuje, co jsi vybral naposledy, a stejný výběr se používá i u stažených souborů.

Nad seznamem je štítek **Hledat torrenty**. Objeví se, jen když je nastavený Prowlarr, a klepnutím se prohledají trackery; během hledání se točí kolečko přes fotku i v samotném štítku. Nalezené torrenty se zařadí **nad streamy** se zeleným štítkem *Torrent* a mají jedinou akci, **Stáhnout torrent** – předá se qBittorrentu a video se objeví mezi staženými, až se stáhne. Přehrát ani poslat do mobilu je nelze, torrent není odkaz na video. V bublině je tracker a kolik lidí soubor sdílí.

Interpunkci z názvu titulu dotaz na tracker neunese („Okresní přebor **–** Poslední zápas…" nenajde nic), takže se před odesláním odstraní. Když ani pak tracker nic nevrátí, zkusí se ještě kratší dotaz z prvních slov názvu a roku, a nakonec původní název titulu – české trackery pojmenovávají soubory obojím.

U seriálu jde do dotazu **jen název**: značka „S02E01" fulltext trackerů spolehlivě vynuluje. Sezóna a díl se proto vybírají až z výsledků – nabídne se konkrétní díl, a když není, balík celé sezóny. Torrent jiné sezóny se zahodí, takže na díl 2×01 nevyskočí první série.

Rozdělané torrenty jsou vidět v **Stahování** spolu s vlastním stahováním, včetně procent, rychlosti a odhadu času; křížkem se torrent zruší i s rozdělanými daty. Dokud se stahuje, mezi staženými soubory se neukáže, i když už jeho soubor ve složce leží. Smazání staženého filmu odebere i jeho torrent z qBittorrentu – jinak by dál seedoval a hlásil chybějící data.

### Bubliny u tlačítek

Každé tlačítko v kartě má bublinu, která říká, co udělá – od štítků s historií (*Zopakovat hledání …*) přes tlačítka u streamu až po ikony u sledovaných seriálů. U streamu je v bublině navíc celý název souboru, titulky, bitrate a jestli hraje i mimo domácí síť.

## Entity

| Entita | Stav | Atributy |
|---|---|---|
| `sensor.nokturno_stahovani` | počet běžících stahování | `downloads` (fronta), `files` (hotové soubory), `free_gb`, `directory`, `search_history`, `notify_targets` |
| `sensor.nokturno_nove_dily` | kolik sledovaných seriálů má nový díl | `series` – u každého `latest` (odvysíláno), `available` (nejnovější se streamem), `new`, `checked` |
| `sensor.nokturno_hlidane` (u starších instalací `sensor.nokturno_k_zhlednuti`) | kolik hlídaných titulů už má stream | `total`, `items` (id, název, rok, počet streamů, nejlepší stream) |
| `sensor.nokturno_stav_zdroju` | počet zdrojů, které potřebují zásah (`0` = vše v pořádku) | `sources` (u každého `level`, `code`, `detail`), `problems` |

## Služby

Služby označené **↩** vracejí data – volej je s `response_variable`.

### `nokturno.search` ↩
Hledání. `query` (povinné), `type` = `movie` (výchozí) / `series` / `webshare` (soubory přímo z WebShare) / `catalog` / `catalog_series` (databáze filmů – najde i tituly, které zatím nikde nejsou), `limit` (1–60, výchozí 20). Rok v `query` se použije jako filtr roku vydání (u `webshare` zůstává součástí fulltextu).
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

*`delete_file` i `share_file` smí spustit jen správce HA (volání z automatizace bez uživatele projde).*

### `nokturno.continue_watching` ↩
Rozkoukané tituly ze všech Kodi (nebo z jednoho přes `entity_id`). U každé položky `entity_id` zdrojového Kodi a `file` (plugin odkaz, který pokračuje od uložené pozice).

### `nokturno.watch_series` ↩ / `nokturno.check_series` ↩ / `nokturno.mark_seen` ↩
Sledování seriálů: přidat (`id`, `title`, `alt`, `poster`) nebo odebrat (`remove: true`); ruční kontrola nových dílů; zhasnutí označení nového dílu (bez `id` u všech).

### `nokturno.want_to_watch` ↩
Přidá titul do seznamu k zhlédnutí (`id` z hledání nebo z databáze filmů, `type`, `title`, `year`, `alt`, `poster`) nebo ho odebere (`remove: true`). Místo `id` stačí `query` – pak se hlídá název, dokud se titul někde neobjeví. Seznam se kontroluje jednou denně a hned po přidání.

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

Jemnější řízení – najdi titul, vyber první stream použitelný i mimo domácí síť a pusť ho:

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

- **Zdroje jsou rovnocenné** a žádný není povinný. Luna přidává katalogy a metadata, Sosáč české tituly, WebShare fulltext a přímé odkazy, HellSpy další soubory bez nutnosti účtu.
- **Slučování titulů**: shoda názvu (i originálu) a roku ±1; u dlouhých názvů s podtitulem se zkouší i část před pomlčkou, protože fulltext Sosáče na celý název nic nenajde; id protějšku putuje dál jako `alt`, takže se u titulu nabídnou streamy z obou zdrojů.
- **Odkazy mimo síť**: streamy z Luny míří na její adresu v LAN, proto se páruje s fulltextem WebShare podle velikosti (±0,25 GB) a kvality a k položce se přibalí přímý odkaz z CDN. Hledá se pod českým i originálním názvem (z Sosáče nebo z Cinemety). Zbytek se přepíše na `external_host`, pokud addon Tailscale běží.
- **Jazyk zvuku** se bere z metadat zdroje a doplňuje z názvu souboru – Luna občas hlásí `EN` u souboru, který má v názvu `cz`. Značky pro titulky (`cz tit`, `cztit`) se do zvuku nepočítají.
- **Hlášky WebShare** se překládají do srozumitelné podoby: „File temporarily unavailable" se ukáže jako doporučení zkusit jiný stream.
- **Náhledy Sosáče** jsou od září 2026 mrtvé (404), plakáty se dotahují z TMDB – podle IMDb id, a když chybí, podle názvu a roku.
- **Přerušené stahování**: fronta se ukládá do `.storage/nokturno/downloads.json`, rozstahovaný soubor zůstává jako `.part`. Po startu se úloha zařadí zpátky, vyžádá se nový odkaz (ty z WebShare vyprší) a pokračuje se hlavičkou `Range` od posledního bajtu. Když server rozsah neumí, stahuje se znovu od začátku. Zrušení uživatelem `.part` smaže.
- **Nový díl seriálu** se hlásí až podle dostupnosti streamu; při zařazení se najde nejnovější sezóna se streamy, dál se sleduje jen posun dopředu.
- **Jedno hledání pro oba typy**: karta se ptá na filmy i seriály naráz a drží si obojí; přepínač se ukáže, jen když obojí něco našlo, a přepnutí pak jen prohodí už načtený seznam.
- **Rok jako filtr**: z dotazu se odřízne čtyřciferný rok a použije se na výsledky i na názvy souborů z fulltextu WebShare (tolerance ±1, soubor bez roku projde). Rok v budoucnosti se bere jako součást názvu.
- **Detail z databáze filmů**: Cinemeta `meta` + TMDB přes Lunu, výsledek se drží den v cache. Karta si ho vyžádá u každého titulu s IMDb id, kterému chybí popis nebo plakát.
- **Karta se registruje přes zdroje Lovelace**, ne přes `extra_module_url` – ten se vyhodnotí dřív, než si frontend nasadí vlastní registr prvků, a karta by pro HA „neexistovala". Pro jistotu si registraci po načtení stránky ještě několikrát zopakuje.
- Knihovny v `custom_components/nokturno/lib/` a `engine.py` jsou vysypaná kopie sdíleného jádra [nokturno-core](https://github.com/matata86/nokturno-core) (od 2026-09-12) – stejné jádro má i doplněk pro Kodi a Stremio.

## Řešení potíží

| Problém | Co s tím |
|---|---|
| Karta hlásí chybu nastavení, na desktopu je v pořádku | mobilní aplikaci úplně zavři a otevři znovu (drží si stránku v cache) |
| Karta se načte dvakrát / „already used" | odeber ruční záznam `/local/nokturno/…` ze zdrojů Lovelace |
| Změny v integraci se neprojeví | po zásahu do Pythonu je nutný restart HA Core, reload integrace nestačí |
| U titulu chybí plakát | Sosáč obrázky nemá; pokud nejde dohledat ani přes TMDB, zůstane podklad s ikonou |
| Stream nejde pustit venku | vyber řádek s 🌐, nebo vyplň adresu Tailscale a zkontroluj, že addon běží |
| Trakt hlásí „nepřihlášeno" | spusť `nokturno.trakt_auth` a zadej kód na trakt.tv/activate |
| Integrace hlásí *vyžaduje opravu* | WebShare odmítl přihlášení – klikni na *Opravit* a zadej e-mail a heslo znovu; heslo se před uložením ověří |
| Senzory se jmenují jinak než v návodu | od 4.0 se názvy senzorů překládají podle jazyka HA – nová instalace v angličtině má třeba `sensor.nokturno_downloads`. Karta si senzor stahování najde sama, v automatizacích použij skutečné `entity_id` |
| Potřebuju poslat podklady k chybě | u integrace *Stáhnout diagnostiku* – hesla, účty a klíče se do souboru nedostanou |

## Související projekty

| Projekt | K čemu |
|---|---|
| [plugin.video.nokturno](https://github.com/matata86/plugin.video.nokturno) | klient pro Kodi – stejné zdroje, přes něj se pouští na TV |
| [ha-addons](https://github.com/matata86/ha-addons) | addony pro HA: server Luna a proxy Sosáče pro Nuvio |
| [fns-ha-tweaks](https://github.com/matata86/fns-ha-tweaks) | sdílený vzhled a karty pro Home Assistant |

## Pomoc

- **Dotazy, rady a novinky:** [facebooková skupina Nokturno](https://www.facebook.com/groups/nokturno). Odpovídáme tam my i ostatní uživatelé.
- **Řešení častých potíží:** [nápověda Nokturna](https://matata86.github.io/nokturno-napoveda/). Podrobné návody k nastavení jsou ve [wiki](https://github.com/matata86/nokturno-ha/wiki).
- **Chyba v kódu** (pád nebo chování, které jde zopakovat): [GitHub Issues](https://github.com/matata86/nokturno-ha/issues). Napiš verzi integrace a Home Assistantu a přilož diagnostiku (u integrace *Stáhnout diagnostiku*).

## Právní upozornění

Nokturno je především přehrávač a správce **vlastního úložiště** – obsah, který
si nahraješ a zpřístupníš (např. přes WebDAV), přehrává napřímo. Jako doplňkovou
službu si můžeš volitelně napojit i některé veřejně dostupné vyhledávače třetích
stran (WebShare, Sosáč, HellSpy, Sledujteto, FastShare, Přehraj.to, CZtor, Luna,
OpenSubtitles) – v tom případě je Nokturno jen technické rozhraní, samo žádný
obsah nehostuje, neukládá ani neposkytuje.

Nokturno smíš používat jen k obsahu, ke kterému máš zákonné oprávnění, licenci
nebo jiný právní titul. Vyhledávání, zpřístupňování nebo přehrávání autorsky
chráněného obsahu bez souhlasu nositelů práv je zakázáno.

Nokturno je poskytováno „tak, jak je“, bez záruky funkčnosti, dostupnosti ani
legálnosti zdrojů třetích stran. Za způsob použití odpovídáš výhradně ty.
Provozovatel si vyhrazuje právo kdykoli omezit nebo ukončit přístup.

Při přidávání integrace je právní upozornění první krok, bez odsouhlasení se
instalace nedokončí. Plný text a kontakty pro nahlášení nelegálního obsahu
u jednotlivých zdrojů: <https://nokturno.stream/terms>

## Licence

Všechna práva vyhrazena (All rights reserved), viz [LICENSE](LICENSE).

---

## Podpora

[![Podpoř Nokturno – Ko-fi, PayPal, Bitcoin](https://raw.githubusercontent.com/matata86/plugin.video.nokturno/main/.github/podpora.png)](https://ko-fi.com/matata86)

- **Ko-fi:** https://ko-fi.com/matata86
- **PayPal:** https://paypal.me/matata86
- **Bitcoin:** `bc1qhjwt8xxmuym0xsd50yfpvjph00386uz73gqwlc`
