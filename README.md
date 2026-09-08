# Nokturno pro Home Assistant

[![Podpoř autora na Ko-fi](https://img.shields.io/badge/Ko--fi-podpo%C5%99%20autora-ff5e5b?logo=ko-fi&logoColor=white)](https://ko-fi.com/matata86)

Hledání filmů a seriálů ve **WebShare**, **Sosáči** a **Luně** přímo z Home Assistantu — s přehráním v Kodi, stažením do HA nebo odesláním odkazu do mobilu. Doplňuje [Kodi doplněk Nokturno](https://github.com/matata86/plugin.video.nokturno), se kterým sdílí zdroje i účty.

![Karta Nokturno](https://raw.githubusercontent.com/matata86/nokturno-ha/main/docs/karta.png)

## Co to umí

- **Jedno hledání ve všech zdrojích** — stejný titul z Luny i Sosáče se sloučí do jedné položky, streamy se pak nabídnou ze všech zdrojů naráz.
- **Přehrání v Kodi přes doplněk Nokturno**, takže si Kodi vede „Pokračovat ve sledování" a pamatuje si pozici. Ostatní přehrávače (TV, Cast) dostanou přímé URL.
- **Odeslání do mobilu** — notifikace s odkazem, klepnutím se spustí ve VLC (posílá se jako Android intent s typem videa, jinak by telefon soubor jen stáhl).
- **Stahování do `/media/nokturno`** s frontou a průběhem; hotové soubory jsou vidět v kartě, dají se přehrát nebo smazat.
- **Odkazy použitelné mimo domácí síť** — pokud se ke streamu najde tentýž soubor přímo na WebShare, použije se odkaz z jejich CDN (v kartě ikona 🌐). Zbytek se přepíše na adresu z Tailscale/VPN, pokud ji vyplníš.

## Instalace

### HACS (doporučeno)

1. HACS → tři tečky vpravo nahoře → **Vlastní repozitáře**
2. URL `https://github.com/matata86/nokturno-ha`, typ **Integrace**
3. Najdi **Nokturno**, nainstaluj a restartuj Home Assistant
4. **Nastavení → Zařízení a služby → Přidat integraci → Nokturno**

Kartu do dashboardu integrace naservíruje sama, nemusíš nic přidávat do zdrojů Lovelace.

### Ručně

Zkopíruj složku `custom_components/nokturno` do své konfigurace a restartuj HA.

## Nastavení

Průvodce se ptá na účty (vyplň jen zdroje, které chceš) a na předvolby přehrávání:

| Pole | K čemu |
|---|---|
| WebShare — e-mail a heslo | fulltextové hledání souborů a přímé odkazy |
| Streamuj.tv — uživatel a heslo | streamy Sosáče |
| Luna — adresa a token | katalogy TMDB a streamy přes [Lunu](https://github.com/matata86/ha-addons) |
| Výchozí přehrávač | Kodi, na které se pouští |
| Preferovaný jazyk, prostorový zvuk, skrýt SD, max. velikost, řazení | stejné volby jako v Kodi doplňku |
| Složka pro stahování | výchozí `/media/nokturno` |
| Adresa mimo domácí síť | Tailscale/VPN adresa HA, aby odkazy fungovaly i venku |

## Karta

Přidej kartu **Nokturno** (`custom:nokturno-card`) — má vizuální editor, takže stačí vybrat přehrávače a mobil.

```yaml
type: custom:nokturno-card
player: media_player.coreelec
players:
  - media_player.coreelec
  - media_player.samsung_tv_q6
phone: notify.mobile_app_muj_telefon
downloads: sensor.nokturno_stahovani
```

## Služby

| Služba | Vrací data | K čemu |
|---|---|---|
| `nokturno.search` | ano | hledání (`movie`, `series`, `webshare`) |
| `nokturno.streams` | ano | streamy titulu, seřazené podle nastavení |
| `nokturno.episodes` | ano | sezóny a epizody seriálu |
| `nokturno.resolve` | ano | přímé URL streamu pro cizí přehrávač |
| `nokturno.play` | | přehrání na přehrávači |
| `nokturno.download` | | stažení do složky HA |
| `nokturno.send_link` | | odeslání odkazu do mobilu |
| `nokturno.cancel_download`, `nokturno.delete_file` | | správa stahování a souborů |

Služby s návratovou hodnotou se volají s `response_variable`, takže se dají použít ve skriptech i v hlasovém asistentovi:

```yaml
sequence:
  - action: nokturno.search
    data:
      query: "{{ nazev }}"
      type: movie
    response_variable: nalezeno
  - action: nokturno.play
    data:
      id: "{{ nalezeno.results[0].id }}"
      alt: "{{ nalezeno.results[0].alt }}"
      entity_id: media_player.coreelec
```

## Entita

`sensor.nokturno_stahovani` — počet běžících stahování; v atributech fronta, hotové soubory a seznam telefonů, na které jde poslat odkaz.

## Poznámky

- Zdroje jsou rovnocenné, žádný není povinný — s vyplněným jen WebShare účtem funguje hledání i přehrávání, Luna přidává katalogy a metadata, Sosáč české tituly.
- Knihovny v `custom_components/nokturno/lib/` jsou kopie z Kodi doplňku, aby se obě aplikace chovaly stejně.

---

Líbí se ti to? ☕ [Podpoř autora na Ko-fi](https://ko-fi.com/matata86)
