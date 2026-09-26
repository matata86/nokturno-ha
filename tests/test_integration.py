"""Kontrola integrace pro Home Assistant — bez Home Assistantu, bez sítě a bez účtů.

    python3 -m unittest discover -s tests -v

`homeassistant` a `voluptuous` nahrazuje `tests/ha_stubs.py` jen do té míry, aby
se dal modul naimportovat. Jádro (`lib/`, `engine.py`) má testy ve svém repu;
tady se ověřuje, co je vlastní integraci: odkazy pro Kodi a Android, klíče
položek Pokračovat ve sledování, pomocníky pro služby, a soulad souborů, které
Home Assistant a HACS čtou samy (manifest, services.yaml, překlady, karta).
"""
import json
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "nokturno"
CORE = ROOT.parent.parent / "nokturno-core"
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

import ha_stubs                                          # noqa: E402
ha_stubs.install()

from custom_components.nokturno import (                 # noqa: E402
    KODI_PLUGIN, SYNC_KEY_MIN_HEX, _continue_key, _encode_signed, _removed_by_user, _stats_title,
    _varovat_kratky_klic, aired_episodes, android_play_intent, episode_target, kodi_image, kodi_url,
    skip_gap_candidates, sync_circles,
)
from custom_components.nokturno import sensor as nokturno_sensor  # noqa: E402
from custom_components.nokturno import config_flow, const  # noqa: E402


class FakeStore:
    def __init__(self, watched=None, hidden=None):
        self._watched, self._hidden = watched or {}, hidden or {}

    def load(self, key, default=None):
        return self._watched if key == "watched" else default

    def next_hidden(self, series):
        return self._hidden.get(series)


class FakeApi:
    def __init__(self, episode=None, fail=False):
        self.episode, self.fail = episode, fail
        self.calls = []

    def episode_id(self, base, season, episode):
        self.calls.append((base, season, episode))
        if self.fail:
            raise RuntimeError("Luna: id je ve tvaru id:S:E")
        return self.episode


class FakeEngine:
    def __init__(self, api=None, meta=None, video=None):
        self._api, self._meta, self._video = api, meta or {}, video

    def api_for(self, item_id):
        return self._api

    def meta(self, ctype, item_id, series_id=None):
        return self._meta, self._video


class TestKnihovnaJeKopieJadra(unittest.TestCase):
    @unittest.skipUnless(CORE.is_dir(), "jádro není vedle integrace")
    def test_lib_a_engine_odpovidaji_jadru(self):
        out = subprocess.run([sys.executable, str(CORE / "tools" / "sync_core.py"), "--check", "ha"],
                             capture_output=True, text=True)
        self.assertIn("ke změně: 0 souborů", out.stdout, f"spusť `python3 tools/sync_core.py ha` v jádru\n{out.stdout}")


class TestOdvysilaneDily(unittest.TestCase):
    """Chybějící datum vydání znamená neodvysíláno (do 6.2.8 to bylo obráceně)."""

    def test_dil_bez_data_se_u_bezicoho_serialu_preskoci(self):
        # Cizinka: díly s daty, poslední tři se teprve natáčejí (TMDB u nich datum nemá)
        epizody = [{"season": 2, "episode": n, "released": "2026-09-%02d" % n} for n in range(1, 7)]
        epizody += [{"season": 2, "episode": 7, "released": "2026-10-30"}]          # ještě nevysíláno
        epizody += [{"season": 2, "episode": n} for n in (8, 9, 10)]                 # bez data
        aired = aired_episodes(epizody, "2026-09-20")
        self.assertEqual([e["episode"] for e in aired], [1, 2, 3, 4, 5, 6])

    def test_serial_bez_jedineho_data_projde_cely(self):
        # TMDB u některých seriálů data nedává vůbec — tam se chová jako dřív
        epizody = [{"season": 1, "episode": 2}, {"season": 1, "episode": 1}, {"season": 2, "episode": 1}]
        aired = aired_episodes(epizody, "2026-09-20")
        self.assertEqual([(e["season"], e["episode"]) for e in aired], [(1, 1), (1, 2), (2, 1)])

    def test_specialy_a_prazdny_seznam(self):
        self.assertEqual(aired_episodes([{"season": 0, "episode": 1, "released": "2020-01-01"}], "2026-09-20"), [])
        self.assertEqual(aired_episodes([], "2026-09-20"), [])

    def test_mezera_ve_zdrojich_zustava_pruchozi(self):
        # díl, který chybí ve zdrojích, není totéž co díl, který se nevysílal:
        # S02E10–13 datum mají (odvysílané, jen nikde ke stažení), S03E03 se teprve natáčí
        epizody = [{"season": 2, "episode": n, "released": "2026-05-%02d" % n} for n in (9, 10, 13)]
        epizody += [{"season": 3, "episode": n, "released": "2026-09-%02d" % n} for n in (1, 2)]
        epizody += [{"season": 3, "episode": 3}]
        aired = aired_episodes(epizody, "2026-09-20")
        self.assertEqual([(e["season"], e["episode"]) for e in aired],
                         [(2, 9), (2, 10), (2, 13), (3, 1), (3, 2)])
        self.assertEqual([(e["season"], e["episode"]) for e in skip_gap_candidates(aired, (2, 10))],
                         [(3, 2), (3, 1)])


class TestOdkazy(unittest.TestCase):
    def test_kontrola_dilu_preskoci_mezeru(self):
        # Zrádci: S02E09 dostupný, S02E10–13 nikde, S03E01–02 odvysílané
        aired = [{"season": s, "episode": e} for s, e in ((2, 9), (2, 10), (2, 13), (3, 1), (3, 2))]
        self.assertEqual([(e["season"], e["episode"]) for e in skip_gap_candidates(aired, (2, 10))], [(3, 2), (3, 1)])
        # mezera v nejnovější sezóně: chybějící díl ani starší se znovu nezkouší
        self.assertEqual([(e["season"], e["episode"]) for e in skip_gap_candidates(aired, (3, 1))], [(3, 2)])
        self.assertEqual(skip_gap_candidates([], (0, 0)), [])

    def test_kodi_url_nese_jen_potrebne(self):
        url = kodi_url("movie", "tt1", None, None, {"url": "ws:abc"})
        self.assertEqual(url, KODI_PLUGIN + "?action=play&type=movie&id=tt1&url=ws%3Aabc")

    def test_kodi_url_serial_s_titulky(self):
        url = kodi_url("series", "tt1:1:2", "tt1", "sosacd_5", {"url": "hs:1:h", "subtitles": ["ws:s1", "ws:s2"]})
        self.assertIn("series=tt1", url)
        self.assertIn("alt=sosacd_5", url)
        self.assertIn("subs=ws%3As1%7Cws%3As2", url)

    def test_android_intent_zakoduje_mezery_jen_jednou(self):
        raw = "http://ha.lan:8123/api/nokturno/files/Pět švestek.mkv?authSig=abc"
        intent = android_play_intent(raw)
        self.assertTrue(intent.startswith("intent://ha.lan:8123/api/nokturno/files/P%C4%9Bt%20%C5%A1vestek.mkv?authSig=abc#Intent;"))
        self.assertIn("scheme=http;", intent)
        self.assertIn("type=video/*;", intent)
        self.assertIn("S.browser_fallback_url=http%3A%2F%2Fha.lan%3A8123%2Fapi%2Fnokturno%2Ffiles%2FP%C4%9Bt%20%C5%A1vestek.mkv%3FauthSig%3Dabc;end", intent)
        # už zakódovaný odkaz projde stejně — nesmí vzniknout %2520
        self.assertEqual(android_play_intent(raw.replace(" ", "%20")), intent)

    def test_encode_signed_necha_query(self):
        self.assertEqual(_encode_signed("/api/nokturno/files/a b.mkv?authSig=x=y"),
                         "/api/nokturno/files/a%20b.mkv?authSig=x=y")

    def test_kodi_image(self):
        self.assertEqual(kodi_image("image://https%3a%2f%2fimage.tmdb.org%2fa.jpg/"), "https://image.tmdb.org/a.jpg")
        self.assertEqual(kodi_image("https://x/y.jpg"), "https://x/y.jpg")
        self.assertEqual(kodi_image("image://https%3a%2f%2fmovies.sosac.tv%2fa.jpg/"), "")
        self.assertEqual(kodi_image("special://home/x.png"), "")
        self.assertEqual(kodi_image(""), "")


class TestPokracovatVeSledovani(unittest.TestCase):
    def test_klic_z_plugin_odkazu(self):
        self.assertEqual(_continue_key(KODI_PLUGIN + "?action=play&type=series&id=tt1%3A1%3A2&series=tt1&url=x"),
                         ("tt1:1:2", "tt1"))
        self.assertEqual(_continue_key(KODI_PLUGIN + "?action=play_ws&ident=abc&name=x"), ("ws:abc", ""))
        self.assertEqual(_continue_key(KODI_PLUGIN + "?action=play_hs&id=12&hash=ab&name=x"), ("hs:12:ab", ""))
        self.assertEqual(_continue_key(""), ("", ""))

    def test_odebrany_dalsi_dil(self):
        store = FakeStore(hidden={"tt1": "tt1:1:3"})
        self.assertTrue(_removed_by_user(store, {"file": KODI_PLUGIN + "?action=play&id=tt1:1:3&series=tt1"}))
        self.assertFalse(_removed_by_user(store, {"file": KODI_PLUGIN + "?action=play&id=tt1:1:4&series=tt1"}))

    def test_vynulovana_rozkoukanost_bez_zhlednuti(self):
        store = FakeStore(watched={"tt9": {"playcount": 0, "resume": 0, "total": 0}})
        self.assertTrue(_removed_by_user(store, {"file": KODI_PLUGIN + "?action=play&id=tt9"}))
        store = FakeStore(watched={"tt9": {"playcount": 0, "resume": 120.5, "total": 5000}})
        self.assertFalse(_removed_by_user(store, {"file": KODI_PLUGIN + "?action=play&id=tt9"}))
        store = FakeStore(watched={"tt9": {"playcount": 1, "resume": 0, "total": 0}})
        self.assertFalse(_removed_by_user(store, {"file": KODI_PLUGIN + "?action=play&id=tt9"}))
        self.assertFalse(_removed_by_user(FakeStore(), {"file": KODI_PLUGIN + "?action=play&id=tt9"}))


class TestSluzby(unittest.TestCase):
    def test_episode_target_film(self):
        self.assertEqual(episode_target(FakeEngine(), {"id": "tt1"}), ("movie", "tt1", None, None))

    def test_episode_target_dil_podle_sezony_a_epizody(self):
        api = FakeApi(episode="sosacd_5:2:3")
        engine = FakeEngine(api)
        self.assertEqual(episode_target(engine, {"id": "sosacd_5", "type": "series", "season": 2, "episode": "3"}),
                         ("series", "sosacd_5:2:3", "sosacd_5", None))
        self.assertEqual(api.calls, [("sosacd_5", 2, 3)])

    def test_episode_target_bez_episode_id_sklada_tvar_luny(self):
        engine = FakeEngine(FakeApi(fail=True))
        self.assertEqual(episode_target(engine, {"id": "tt1", "series": "tt1", "season": 1, "episode": 2, "alt": "s9"}),
                         ("series", "tt1:1:2", "tt1", "s9"))
        engine = FakeEngine(object())   # api bez episode_id
        self.assertEqual(episode_target(engine, {"id": "tt1", "season": 1, "episode": 2})[1], "tt1:1:2")

    def test_stats_title_bez_roku_v_nazvu(self):
        engine = FakeEngine(meta={"_title": "Matrix", "name": "Matrix (1999)", "year": "1999-03-31"})
        self.assertEqual(_stats_title(engine, "movie", "tt1", None), ("Matrix", 1999, "movie"))
        engine = FakeEngine(meta={"name": "Breaking Bad", "releaseInfo": "2008-"}, video={"season": 1})
        self.assertEqual(_stats_title(engine, "movie", "tt2:1:1", "tt2"), ("Breaking Bad", 2008, "series"))
        engine = FakeEngine(meta={"name": "Bez roku"})
        self.assertEqual(_stats_title(engine, "movie", "tt3", None), ("Bez roku", None, "movie"))


class TestNastaveni(unittest.TestCase):
    def test_ucty_a_hesla_patri_do_data_ne_do_options(self):
        tajne = {const.CONF_WS_PASS, const.CONF_STREAMUJ_PASS, const.CONF_ST_PASS, const.CONF_LUNA_TOKEN,
                 const.CONF_TMDB_KEY, const.CONF_SYNC_KEY, "dav1_password", "dav2_password", "dav3_password"}
        self.assertTrue(tajne <= set(config_flow.ACCOUNT_KEYS), tajne - set(config_flow.ACCOUNT_KEYS))
        predvolby = {m.schema for m in config_flow.preferences_schema({}).schema}
        self.assertEqual(predvolby & set(config_flow.ACCOUNT_KEYS), set())

    def test_predvolby_maji_stejne_klice_jako_jadro(self):
        predvolby = {m.schema for m in config_flow.preferences_schema({}).schema}
        for key in (const.CONF_PREF_LANG, const.CONF_SORT, const.CONF_HIDE_SD, const.CONF_MAX_BITRATE,
                    const.CONF_HS_ENABLED, const.CONF_STATS_ENABLED):
            self.assertIn(key, predvolby)

    def test_madarstina_mezi_volbami_jazyka(self):
        """`LANGS` (jádro) řídí volby přímo — bez `const.py` v souladu se sync_core.py by HU chybělo."""
        schema = config_flow.preferences_schema({})
        for marker in schema.schema:
            if marker.schema == const.CONF_PREF_LANG:
                validator = schema.schema[marker]
                volby = validator.args[0].kwargs["options"]
                self.assertIn("HU", [v["value"] for v in volby])
                break
        else:
            self.fail("pref_lang není ve schématu")


class TestSouboryProHomeAssistant(unittest.TestCase):
    """Co HA a HACS čtou samy — chyba se neprojeví v Pythonu, ale až u uživatele."""

    def setUp(self):
        self.manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))

    def test_manifest(self):
        self.assertEqual(self.manifest["domain"], const.DOMAIN)
        # beta jako PEP 440 („4.0.0b1“) — HACS i tag vX.Y.ZbN ji tak čtou
        self.assertRegex(self.manifest["version"], r"^\d+\.\d+\.\d+(b\d+)?$")
        self.assertTrue(self.manifest["config_flow"])
        self.assertEqual(self.manifest["requirements"], [], "jádro je bez závislostí, integrace má zůstat taky")
        for key in ("documentation", "issue_tracker", "codeowners", "iot_class"):
            self.assertIn(key, self.manifest)

    def test_hacs_json(self):
        hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
        self.assertEqual(hacs["name"], "Nokturno")
        self.assertFalse(hacs.get("content_in_root", False))
        self.assertRegex(hacs["homeassistant"], r"^\d{4}\.\d{1,2}\.\d+$")
        # StaticPathConfig je od 2024.7, OptionsFlow.config_entry bez __init__ od 2024.11
        self.assertGreaterEqual(tuple(int(x) for x in hacs["homeassistant"].split(".")), (2024, 11, 0))

    def test_atributy_senzoru_nejdou_do_recorderu(self):
        """Stav se během stahování přepisuje každé 2 s a nesl celý výpis složky."""
        from custom_components.nokturno import sensor

        class Downloader:
            jobs, torrents, directory, files, free_gb = {}, [], "/media", ["a.mkv"] * 300, 12.0

        class Store:
            def load(self, name, default):
                return default

        class Engine:
            sub_status = stream_progress = search_progress = {}
            store = Store()

            def history(self):
                return ["x"]

            def sources(self):
                return {"webshare": True}
        s = sensor.NokturnoDownloadsSensor(ha_stubs.ConfigEntry(), Downloader(), {}, Engine())
        s.hass = type("H", (), {"config_entries": type("C", (), {"async_entries": staticmethod(lambda d: [])})()})()
        velke = {k for k, v in s.extra_state_attributes.items() if isinstance(v, (list, dict))}
        self.assertTrue(velke <= s._unrecorded_attributes, velke - s._unrecorded_attributes)
        self.assertIn("items", sensor.NokturnoTraktSensor._unrecorded_attributes)
        self.assertIn("series", sensor.NokturnoEpisodesSensor._unrecorded_attributes)

    def test_unload_odregistruje_vsechny_sluzby(self):
        """Ručně opisovaný výčet v unload tři služby vynechal — teď se bere z registrace."""
        src = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('hass.data[DOMAIN][entry.entry_id]["services"] = [name for name, *_ in services]', src)
        self.assertIn('for name in data.get("services") or []:', src)
        self.assertNotIn("SERVICE_CLEAR_CACHE,\n                         SERVICE_SEEN", src)

    def test_episode_target_bezi_v_executoru(self):
        src = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
        import re
        prime = [m.start() for m in re.finditer(r"= episode_target\(engine", src)]
        self.assertEqual(prime, [], "episode_target sahá na síť (Sosáč) — jen přes async_add_executor_job")
        self.assertEqual(src.count("hass.async_add_executor_job(episode_target, engine, call_data)"), 3)

    def test_kazda_sluzba_je_v_services_yaml_a_naopak(self):
        v_kodu = {getattr(const, name) for name in dir(const) if name.startswith("SERVICE_")}
        v_yaml = set(re.findall(r"^([a-z_]+):", (COMPONENT / "services.yaml").read_text(encoding="utf-8"), re.M))
        self.assertEqual(v_kodu - v_yaml, set(), "služba bez popisu pro UI Home Assistantu")
        self.assertEqual(v_yaml - v_kodu, set(), "popis služby, kterou integrace neregistruje")

    def test_preklady_maji_stejnou_strukturu(self):
        def klice(d, prefix=""):
            out = set()
            for k, v in d.items():
                out.add(prefix + k)
                if isinstance(v, dict):
                    out |= klice(v, prefix + k + ".")
            return out

        strings = klice(json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8")))
        for lang in ("cs", "en", "sk"):
            preklad = klice(json.loads((COMPONENT / "translations" / f"{lang}.json").read_text(encoding="utf-8")))
            self.assertEqual(strings ^ preklad, set(), f"{lang}.json se liší od strings.json")

    def test_strings_json_je_anglicky_a_uplny(self):
        """Zdroj překladů je anglický (HA z něj generuje ostatní) — a nese i služby a senzory."""
        strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
        en = json.loads((COMPONENT / "translations" / "en.json").read_text(encoding="utf-8"))
        self.assertEqual(strings, en, "en.json musí být kopie strings.json")
        texty = json.dumps(strings, ensure_ascii=False).replace("Sosáč", "").replace("Přehraj.to", "")   # vlastní jména zdrojů
        self.assertNotRegex(texty, r"[ěščřžýáíéůúďťň]", "strings.json obsahuje češtinu")
        yaml = (COMPONENT / "services.yaml").read_text(encoding="utf-8")
        sluzby = set(re.findall(r"^([a-z_]+):", yaml, re.M))
        self.assertEqual(set(strings["services"]), sluzby, "služba bez překladu nebo překlad bez služby")
        self.assertNotRegex(yaml, r"^\s+(name|description):", "texty služeb patří do strings.json, ne do YAML")
        bloky = dict(re.findall(r"^([a-z_]+):.*\n((?:[ \t].*\n|\n)*)", yaml, re.M))
        for name, body in strings["services"].items():
            self.assertTrue(body.get("name") and body.get("description"), name)
            pole = set(re.findall(r"^    ([a-z_]+):", bloky[name], re.M))
            self.assertEqual(set(body.get("fields", {})), pole, f"pole služby {name} vs. YAML")
        for lang in ("cs", "sk"):
            preklad = json.loads((COMPONENT / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
            self.assertEqual(set(preklad["entity"]["sensor"]), {"downloads", "new_episodes", "trakt", "sources"})

    def test_senzory_maji_prekladove_klice(self):
        sensor = (COMPONENT / "sensor.py").read_text(encoding="utf-8")
        strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
        klice = set(re.findall(r'_attr_translation_key = "([a-z_]+)"', sensor))
        self.assertEqual(klice, set(strings["entity"]["sensor"]))
        self.assertNotIn("_attr_name", sensor, "název senzoru natvrdo místo překladu")
        card = (COMPONENT / "www" / "nokturno-card.js").read_text(encoding="utf-8")
        self.assertIn("downloadsSensorId(hass, this._config.downloads)", card, "karta bez fallbacku na přejmenovaný senzor")

    def test_reauth_flow(self):
        strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
        self.assertIn("reauth_confirm", strings["config"]["step"])
        self.assertIn("reauth_successful", strings["config"]["abort"])
        self.assertEqual(set(strings["config"]["error"]),
                         {"ws_auth", "ws_network", "cz_pending", "cz_failed", "cz_network", "sync_code", "terms_required"})
        self.assertTrue(hasattr(config_flow.NokturnoConfigFlow, "async_step_reauth"))
        self.assertTrue(hasattr(config_flow.NokturnoConfigFlow, "async_step_reauth_confirm"))
        init = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("async_start_reauth", init)
        self.assertIn("WebshareApiError", init.split("async_start_reauth")[0][-600:], "reauth jen na chybu API, ne výpadek sítě")

    def test_cztor_parovani_pinem_v_nastaveni(self):
        """Zapnutý CZtor bez spárování otevře krok s PINem; uloží se až po potvrzení."""
        import asyncio

        class Api:
            polls = [False, True]
            def paired(self):
                return False
            def start_pin(self):
                return {"pin": "434252", "poll_token": "P", "url": "https://cztor.com/activate"}
            def poll_pin(self, token):
                return self.polls.pop(0)

        class Hass:
            async def async_add_executor_job(self, fn, *args):
                return fn(*args)

        flow = config_flow.NokturnoOptionsFlow()
        flow.hass = Hass()
        flow._cztor = Api
        shown, created = [], []
        flow.async_show_form = lambda **kw: shown.append(kw) or ("form", kw["step_id"])
        flow.async_create_entry = lambda **kw: created.append(kw) or "entry"
        flow._cz_pending = {"cz_enabled": True, "hide_sd": False}
        self.assertEqual(asyncio.run(flow.async_step_cztor()), ("form", "cztor"))
        self.assertEqual(shown[-1]["description_placeholders"]["pin"], "434252")
        asyncio.run(flow.async_step_cztor({"pair": True}))
        self.assertEqual(shown[-1]["errors"], {"base": "cz_pending"})
        self.assertEqual(asyncio.run(flow.async_step_cztor({"pair": True})), "entry")
        self.assertTrue(created[-1]["data"]["cz_enabled"])
        # odškrtnutím se CZtor vypne a formulář uloží bez párování
        flow2 = config_flow.NokturnoOptionsFlow()
        flow2.hass, flow2._cztor = Hass(), Api
        flow2.async_create_entry = lambda **kw: created.append(kw) or "entry"
        flow2._cz_pending = {"cz_enabled": True}
        self.assertEqual(asyncio.run(flow2.async_step_cztor({"pair": False})), "entry")
        self.assertFalse(created[-1]["data"]["cz_enabled"])

    def test_terms_step_gatuje_instalaci(self):
        """Bez zaškrtnutého souhlasu se konfigurace nedokončí; se souhlasem jde dál
        na formulář s účty a souhlas se uloží do entry.data (verze textu s ním)."""
        import asyncio

        flow = config_flow.NokturnoConfigFlow()

        async def noop():
            return None

        flow.async_set_unique_id = lambda *a, **kw: noop()
        flow._abort_if_unique_id_configured = lambda: None
        shown = []
        flow.async_show_form = lambda **kw: shown.append(kw) or ("form", kw["step_id"])

        result = asyncio.run(flow.async_step_user())
        self.assertEqual(result, ("form", "user"))

        result = asyncio.run(flow.async_step_user({"terms_accepted": False}))
        self.assertEqual(result, ("form", "user"))
        self.assertEqual(shown[-1]["errors"], {"base": "terms_required"})

        result = asyncio.run(flow.async_step_user({"terms_accepted": True}))
        self.assertEqual(result, ("form", "account"))

        created = []
        flow.async_create_entry = lambda **kw: created.append(kw) or "entry"

        async def bez_parovani(user_input):
            return False

        flow._cztor_needs_pairing = bez_parovani
        self.assertEqual(asyncio.run(flow.async_step_account({})), "entry")
        self.assertTrue(created[-1]["data"]["terms_accepted"])
        self.assertEqual(created[-1]["data"]["terms_version"], config_flow.TERMS_VERSION)

    def test_terms_update_gatuje_options_flow(self):
        """Vyšší TERMS_VERSION (věcná změna textu) donutí existující instalaci
        souhlas potvrdit znovu v Options flow, dřív než se dostane k formuláři
        s předvolbami — na rozdíl od Kodi tu není revokovatelný přepínač, tohle
        je jediná cesta, jak se souhlas dostane z verze 1 na verzi 2 a výš."""
        import asyncio

        class Entry:
            data = {"terms_version": config_flow.TERMS_VERSION - 1}
            options = {}

        entry = Entry()
        flow = config_flow.NokturnoOptionsFlow()
        flow.config_entry = entry
        updated = []

        def zapsat(entry_, data):
            updated.append(data)
            entry_.data = data   # skutečné HA po async_update_entry entry.data přepíše

        flow.hass = type("H", (), {"config_entries": type("CE", (), {
            "async_update_entry": staticmethod(zapsat),
        })()})()
        shown = []
        flow.async_show_form = lambda **kw: shown.append(kw) or ("form", kw["step_id"])

        result = asyncio.run(flow.async_step_init())
        self.assertEqual(result, ("form", "terms_update"))

        result = asyncio.run(flow.async_step_init({"terms_accepted": False}))
        self.assertEqual(result, ("form", "terms_update"))
        self.assertEqual(shown[-1]["errors"], {"base": "terms_required"})

        # se souhlasem se zapíše nová verze a jde se rovnou dál na běžný formulář init
        result = asyncio.run(flow.async_step_init({"terms_accepted": True}))
        self.assertEqual(updated[-1]["terms_version"], config_flow.TERMS_VERSION)
        self.assertTrue(updated[-1]["terms_accepted"])
        self.assertEqual(result, ("form", "init"))

        strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
        self.assertIn("terms_update", strings["options"]["step"])
        self.assertIn("terms_required", strings["options"]["error"])

    def test_kazdy_klic_nastaveni_ma_popisek(self):
        # Formulář je rozdělený do sbalitelných sekcí, takže popisky polí leží
        # v `sections.<sekce>.data`, ne rovnou v `step.data`.
        strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
        klice = set(config_flow.ACCOUNT_KEYS) | {m.schema for m in config_flow.preferences_schema({}).schema}
        for blok, krok in (("config", "account"), ("options", "init")):
            sekce = strings[blok]["step"][krok]["sections"]
            popisky = {k for s in sekce.values() for k in s["data"]}
            self.assertEqual(klice - popisky, set(),
                             f"klíč nastavení bez popisku ve formuláři ({blok})")
            for jmeno, obsah in sekce.items():
                self.assertTrue(obsah.get("name"), f"sekce {jmeno} bez názvu")

    def test_kazde_pole_je_v_nejake_sekci(self):
        """Nové pole nesmí z formuláře vypadnout jen proto, že se zapomnělo v SEKCE."""
        schema = config_flow.formular({})
        v_sekcich = {k.schema for sekce in schema.schema.values() for k in sekce.schema.schema}
        klice = set(config_flow.ACCOUNT_KEYS) | {m.schema for m in config_flow.preferences_schema({}).schema}
        self.assertEqual(klice - v_sekcich, set(), "pole mimo všechny sekce")
        self.assertEqual({k.schema for k in schema.schema} - {j for j, _, _ in config_flow.SEKCE}, set())

    def test_zplosteni_vstupu_ze_sekci(self):
        """Uživatelův vstup přijde po sekcích, ukládá se ale naplocho jako dřív."""
        plocho = config_flow._zploskuj({"prehravani": {"pref_lang": "CZ"},
                                        "zdroje": {"ws_username": "a@b.cz"}})
        self.assertEqual(plocho, {"pref_lang": "CZ", "ws_username": "a@b.cz"})

    def test_karta_existuje_a_hlasi_verzi(self):
        card = (COMPONENT / "www" / "nokturno-card.js").read_text(encoding="utf-8")
        # HA bety mají tvar „5.2.6b6“ — dřívější regex bral jen X.Y.Z a od první bety padal.
        # Verze karty je jen banner v konzoli (cache-busting bere manifest), ale má sedět.
        m = re.search(r'const CARD_VERSION = "(\d+\.\d+\.\d+(?:b\d+)?)"', card)
        self.assertIsNotNone(m, "CARD_VERSION chybí nebo má neznámý tvar")
        manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m.group(1), manifest["version"], "CARD_VERSION neodpovídá manifest.json")
        self.assertIn("customElements.define(", card)
        self.assertIn("window.customCards", card)

    def test_verze_karty_v_cache_bustu_je_z_manifestu(self):
        # karta se servíruje s `?v=<verze integrace>`; kdyby se bral jiný zdroj, prohlížeč drží starou
        src = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
        self.assertRegex(src, r"CARD_URL\}\?v=\{[^}]*version")


class TestPrehrajto(unittest.TestCase):
    """Přehraj.to je v HA jako v Kodi — přepínač zapnutý ve výchozím stavu (funguje
    i bez účtu), účet nepovinný. E-mail a heslo jsou účty (entry.data), heslo skryté."""

    def test_pole_ve_formulari(self):
        prefs = {m.schema for m in config_flow.preferences_schema({}).schema}
        self.assertIn(const.CONF_PT_ENABLED, prefs)
        self.assertIn(const.CONF_PT_EMAIL, config_flow.ACCOUNT_KEYS)
        self.assertIn(const.CONF_PT_PASS, config_flow.ACCOUNT_KEYS)
        self.assertIn(const.CONF_PT_PASS, config_flow.SECRET_KEYS)
        self.assertNotIn(const.CONF_PT_EMAIL, config_flow.SECRET_KEYS)

    def test_zapnute_ve_vychozim_stavu(self):
        vychozi = {m.schema: m.default for m in config_flow.preferences_schema({}).schema}
        self.assertIs(vychozi[const.CONF_PT_ENABLED], True)
        # uložený vypnutý stav se respektuje
        u = {m.schema: m.default for m in config_flow.preferences_schema({const.CONF_PT_ENABLED: False}).schema}
        self.assertIs(u[const.CONF_PT_ENABLED], False)

    def test_karta_zna_barvu_prehrajto(self):
        card = (COMPONENT / "www" / "nokturno-card.js").read_text(encoding="utf-8")
        self.assertIn('"Přehraj.to":', card)


if __name__ == "__main__":
    unittest.main()


class TestBezpecnostNastaveni(unittest.TestCase):
    """Audit 2026-09-14: hesla skrytě, tajemství v entry.data, diagnostika bez hesel,
    klíč endpointů konstantně a s HA ban mechanismem."""

    def test_hesla_jsou_skryte_vstupy_a_ucty_v_data(self):
        self.assertTrue(config_flow.SECRET_KEYS <= set(config_flow.ACCOUNT_KEYS))
        for key in (const.CONF_TRAKT_SECRET, const.CONF_PROWLARR_KEY, const.CONF_QBIT_PASS, const.CONF_QBIT_USER,
                    const.CONF_TRAKT_ID, "dav1_password"):
            self.assertIn(key, config_flow.ACCOUNT_KEYS, key)
        schema = config_flow.accounts_schema({})
        for marker, typ in schema.items():
            if marker.schema in config_flow.SECRET_KEYS:
                self.assertIsInstance(typ, ha_stubs.TextSelector, marker.schema)
                self.assertEqual(typ.args[0].kwargs.get("type"), ha_stubs.TextSelectorType.PASSWORD, marker.schema)
            else:
                self.assertIs(typ, str, marker.schema)
        vychozi = {m.schema: m.default for m in schema}
        self.assertEqual(vychozi[const.CONF_PROWLARR_URL], const.DEFAULT_PROWLARR_URL)
        self.assertEqual(vychozi[const.CONF_LUNA_URL], const.DEFAULT_LUNA_URL)
        self.assertEqual(vychozi[const.CONF_WS_PASS], "")
        # předvyplnění z existujícího nastavení
        self.assertEqual({m.schema: m.default for m in config_flow.accounts_schema({"ws_username": "ja"})}["ws_username"], "ja")

    def test_sync_key_ma_128_bitu(self):
        src = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
        self.assertNotIn("token_hex(6)", src)
        self.assertEqual(src.count("token_hex(16)"), 2)

    def test_diagnostika_bez_hesel_a_uctu(self):
        import asyncio
        from custom_components.nokturno import diagnostics

        class Engine:
            sub_status = {"vip": True, "days": 12}

            def sources(self):
                return {"webshare": True, "hellspy": True}

        class Downloader:
            jobs, torrents, files = {"a": 1}, [], ["x"] * 3
        entry = ha_stubs.ConfigEntry(data={"ws_username": "ja@x.cz", "ws_password": "tajne", "sync_key": "abcd",
                                           "dav1_url": "http://nas/", "dav1_password": "p", "luna_token": "e1.t"},
                                     options={"pref_lang": "CZ", "qbit_password": "q"})
        hass = type("H", (), {"data": {const.DOMAIN: {"test": {"engine": Engine(), "downloader": Downloader(),
                                                              "services": ["search"]}}}})()
        out = asyncio.run(diagnostics.async_get_config_entry_diagnostics(hass, entry))
        text = json.dumps(out, ensure_ascii=False)
        for tajne in ("tajne", "abcd", "ja@x.cz", "e1.t", '"p"', '"q"'):
            self.assertNotIn(tajne, text, tajne)
        self.assertEqual(out["entry"]["dav1_url"], "http://nas/", "adresa úložiště k ladění zůstává")
        self.assertEqual(out["entry"]["pref_lang"], "CZ")
        self.assertEqual((out["sources"], out["downloads"], out["files"], out["sub_status"]["days"]),
                         ({"webshare": True, "hellspy": True}, 1, 3, 12))

    def test_klic_endpointu_konstantne_a_spatny_pokus_se_pocita(self):
        import asyncio
        from unittest import mock
        import custom_components.nokturno as modul

        class Request:
            def __init__(self, key):
                self.headers = {"X-Nokturno-Key": key} if key is not None else {}
        with mock.patch.object(modul, "process_wrong_login", side_effect=ha_stubs._async_noop) as spatne:
            self.assertTrue(asyncio.run(modul._klic_sedi(Request("k1"), "k1")))
            self.assertEqual(spatne.call_count, 0)
            self.assertFalse(asyncio.run(modul._klic_sedi(Request("k2"), "k1")))
            self.assertFalse(asyncio.run(modul._klic_sedi(Request(None), "k1")))
            self.assertFalse(asyncio.run(modul._klic_sedi(Request("k1"), "")), "bez klíče v nastavení nikdy")
            self.assertEqual(spatne.call_count, 3)
        src = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn('request.headers.get("X-Nokturno-Key") != key', src)
        self.assertEqual(src.count("await _klic_sedi(request"), 2, "/sync i /files")

    def test_polling_a_want_bez_plne_kontroly(self):
        src = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("check_trakt(only=wid)", src)
        self.assertIn("async def check_trakt(_now=None, only=None, force=False):", src)
        self.assertIn('torrent_stav["aktivni_do"] = time.time() + 300', src)
        self.assertIn("now - torrent_stav[\"posledni\"] < 60", src)


class TestKarta(unittest.TestCase):
    def test_render_streamu_nespadne_na_polozce_bez_labelu_a_escapuje_zdroj(self):
        """Položka z fulltextu má `label` undefined → `s.label.replace` shodil render streamů;
        `s.source` (název vlastního úložiště z nastavení) a `t.year` šly do HTML bez `_esc`."""
        card = (COMPONENT / "www" / "nokturno-card.js").read_text(encoding="utf-8")
        self.assertIn('this._esc(String(s.label || "").replace(', card)
        self.assertNotIn("this._esc(s.label.replace(", card)
        self.assertIn('this._esc(s.source || "?")', card)
        self.assertIn("(${this._esc(t.year)})", card)


class TestUdrzbaHA(unittest.TestCase):
    def test_cache_se_prorezava_a_readme_nelze(self):
        src = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("engine.store.prune_cache", src)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("kopie z Kodi doplňku", readme)
        self.assertIn("nokturno-core", readme)


class _FakeEntry:
    def __init__(self, data):
        self.data = data


class TestStahovaniTimeout(unittest.TestCase):
    """Nález 24 z auditu: bez `sock_read` zůstalo stahování z mlčícího zdroje
    ve stavu „stahuje se" navždy a frontu nikdo neposunul."""

    def test_mlcici_zdroj_stahovani_ukonci(self):
        from custom_components.nokturno import downloader
        src = (COMPONENT / "downloader.py").read_text(encoding="utf-8")
        self.assertNotIn("timeout=None", src, "stahování nesmí čekat na mlčící zdroj donekonečna")
        self.assertIn("timeout=STAHOVANI_TIMEOUT", src)
        self.assertIsNone(downloader.STAHOVANI_TIMEOUT.total, "na celé stahování strop být nesmí")
        self.assertEqual(downloader.STAHOVANI_TIMEOUT.sock_read, 120)
        self.assertEqual(downloader.STAHOVANI_TIMEOUT.sock_connect, 30)


class TestAudit615(unittest.TestCase):
    """Nálezy z auditu 2026-09-19 (`../AUDIT-2026-09-19.md`, § HA), opraveno ve 6.1.5."""

    def setUp(self):
        self.src = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
        self.card = (COMPONENT / "www" / "nokturno-card.js").read_text(encoding="utf-8")

    # 11. klíč pro /api/nokturno/sync jen 48 bitů u starších instalací
    def test_doplneny_sync_key_ma_128_bitu(self):
        self.assertIn("CONF_SYNC_KEY: secrets.token_hex(16)", self.src)
        self.assertNotIn("CONF_SYNC_KEY: secrets.token_hex(6)", self.src, "doplňovaný klíč musí mít 128 bitů")

    def test_kratky_sync_key_da_upozorneni_dlouhy_ne(self):
        from homeassistant.components import persistent_notification
        volani = []
        puvodni = persistent_notification.async_create
        persistent_notification.async_create = lambda *a, **kw: volani.append((a, kw))
        try:
            _varovat_kratky_klic(object(), _FakeEntry({const.CONF_SYNC_KEY: "a" * 12}))
            self.assertEqual(len(volani), 1, "48bitový klíč má uživatele upozornit")
            self.assertIn("notification_id", volani[0][1])
            _varovat_kratky_klic(object(), _FakeEntry({const.CONF_SYNC_KEY: "b" * SYNC_KEY_MIN_HEX}))
            self.assertEqual(len(volani), 1, "dost dlouhý klíč se nehlásí")
        finally:
            persistent_notification.async_create = puvodni

    def test_sync_key_se_nemeni_sam(self):
        """Klíč je zapsaný i v každém Kodi — tichá výměna by synchronizaci rozbila bez varování."""
        usek = self.src.split("async def async_setup_entry")[1].split("\nasync def")[0]
        self.assertEqual(usek.count("token_hex"), 1, "klíč se generuje jen tam, kde žádný není")
        pred, _po = usek.split("token_hex", 1)
        self.assertTrue(pred.rstrip().endswith(
            "hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_SYNC_KEY: secrets."),
            "generování musí zůstat pod `if not entry.data.get(CONF_SYNC_KEY)`")
        self.assertIn("if not entry.data.get(CONF_SYNC_KEY):", pred)

    # 23. senzor zapisoval průběh stahování do recorderu každé 2 s
    def test_prubeh_stahovani_neni_v_recorderu(self):
        neulozene = nokturno_sensor.NokturnoDownloadsSensor._unrecorded_attributes
        for key in ("current", "percent", "speed", "eta", "free_gb", "downloads", "continue_cache"):
            self.assertIn(key, neulozene, key)

    # continue_cache: open() + json.load v event loopu při prvním výpočtu po restartu
    def test_continue_cache_se_predcita_pri_startu(self):
        self.assertIn("engine.store.load, CONTINUE_CACHE_KEY", self.src)

    # accounts.json: open() v event loopu při add_entities senzoru stavu zdrojů
    def test_accounts_se_predcitaji_pri_startu(self):
        self.assertIn("engine.store.load, accounts_lib.STORE", self.src)

    # 22. přehrání podle indexu do znovu spočítaného seznamu
    def test_prehrani_bere_stream_podle_adresy(self):
        self.assertIn("posledni_streamy[url] = (ctype, item_id, series, alt, stream)", self.src)
        self.assertIn('zname = posledni_streamy.get(url)', self.src)
        self.assertIn('shoda = next((s for s in streams if str(s.get("url") or "") == url), None)', self.src)

    def test_karta_posila_adresu_streamu(self):
        usek = self.card.split("_target(stream) {")[1].split("\n  }")[0]
        self.assertIn("target.url = stream.url", usek)
        self.assertIn("target.stream = stream.index", usek, "pořadí zůstává jako záloha")

    # 21. souběžné check_series = dvojí dotazy a dvojí oznámení „nový díl"
    def test_kontrola_serialu_bezi_jen_jedna(self):
        self.assertIn("kontrola_zamek = asyncio.Lock()", self.src)
        usek = self.src.split("async def check_series(_now=None, force=False, only=None):")[1].split("async def _check_series")[0]
        self.assertIn("if kontrola_zamek.locked():", usek)
        self.assertIn("return watchlist()", usek, "tvar odpovědi musí zůstat stejný")
        self.assertIn("async with kontrola_zamek:", usek)

    # mazání a sdílení souborů mohl volat každý přihlášený uživatel HA
    def test_mazani_a_sdileni_jen_pro_spravce(self):
        for handler in ("handle_delete_file", "handle_share_file"):
            usek = self.src.split(f"async def {handler}(call: ServiceCall):")[1].split("async def")[0]
            self.assertIn("_jen_spravce(call", usek, handler)
        usek = self.src.split("async def _jen_spravce")[1].split("async def")[0]
        self.assertIn("user.is_admin", usek)
        self.assertIn("raise Unauthorized", usek)
        self.assertIn("if not user_id:", usek, "volání z automatizace nemá user_id a musí projít")


class TestSenzorStavuZdroju(unittest.TestCase):
    """Senzor se stavem účtů (nápad 17 z auditu 2026-09-19).

    Stejná data, jakými Kodi kreslí první položku menu — `lib/accounts.py`.
    Hlídá se hlavně to, že se čte jen uložený záznam: kdyby se senzor ptal
    zdrojů sám, dělal by to ve smyčce událostí HA.
    """

    class Engine:
        def __init__(self, saved, sources):
            self.store = self
            self._saved, self._sources = saved, sources

        def load(self, key, default=None):
            return self._saved if key == "accounts" else default

        def sources(self):
            return self._sources

        def refresh_accounts(self, **kw):
            raise AssertionError("senzor se nesmí ptát po síti")

    def _senzor(self, saved, sources):
        senzor = nokturno_sensor.NokturnoSourcesSensor.__new__(
            nokturno_sensor.NokturnoSourcesSensor)
        senzor._engine = self.Engine(saved, sources)
        return senzor

    def test_bez_problemu_je_hodnota_nula(self):
        import time
        saved = {"webshare": {"level": "ok", "code": "vip", "detail": {"days": 40}, "ts": time.time()}}
        senzor = self._senzor(saved, {"webshare": True})
        self.assertEqual(senzor.native_value, 0)

    def test_hodnota_je_pocet_zdroju_k_reseni(self):
        import time
        now = time.time()
        saved = {"webshare": {"level": "fail", "code": "expired", "detail": {}, "ts": now},
                 "hellspy": {"level": "warn", "code": "paused", "detail": {"minutes": 8}, "ts": now},
                 "luna": {"level": "ok", "code": "ok", "detail": {}, "ts": now}}
        senzor = self._senzor(saved, {"webshare": True, "hellspy": True, "luna": True})
        self.assertEqual(senzor.native_value, 2)
        self.assertEqual(senzor.extra_state_attributes["problems"], ["webshare", "hellspy"])

    def test_atributy_nesou_kod_i_cisla_ne_hotovou_vetu(self):
        """Text si skládá každá větev sama — Kodi ho potřebuje na jeden řádek."""
        import time
        saved = {"webshare": {"level": "warn", "code": "expires_soon",
                              "detail": {"days": 3, "until": "2026-09-23"}, "ts": time.time()}}
        radek = self._senzor(saved, {"webshare": True}).extra_state_attributes["sources"][0]
        self.assertEqual(radek["code"], "expires_soon")
        self.assertEqual(radek["detail"]["days"], 3)

    def test_vypnute_zdroje_v_atributech_nejsou(self):
        senzor = self._senzor({}, {"webshare": False, "hellspy": False})
        self.assertEqual(senzor.extra_state_attributes["sources"], [])

    def test_atributy_nejdou_do_recorderu(self):
        """Seznam zdrojů se mění každých 6 hodin a v historii k ničemu není."""
        self.assertIn("sources", nokturno_sensor.NokturnoSourcesSensor._unrecorded_attributes)

    def test_obnova_bezi_pod_platnosti_zaznamu(self):
        from custom_components.nokturno.lib import accounts as accounts_lib
        self.assertLess(const.ACCOUNTS_INTERVAL_HOURS * 3600, accounts_lib.TTL)


class TestSynchronizaceVNastaveni(unittest.TestCase):
    """Okruhy a víc přehrávačů — obojí z formuláře, obojí se čte i jinde než ve formuláři."""

    class _Entry:
        def __init__(self, data=None, options=None):
            self.data, self.options = data or {}, options or {}

    def test_okruhy_jsou_ve_formulari(self):
        predvolby = {m.schema for m in config_flow.preferences_schema({}).schema}
        for key in (const.CONF_SYNC_WATCHED, const.CONF_SYNC_FAVOURITES, const.CONF_SYNC_HISTORY,
                    const.CONF_SYNC_WATCHLIST):
            self.assertIn(key, predvolby)

    def test_okruhy_jsou_v_sekci_synchronizace(self):
        sekce = dict((jmeno, klice) for jmeno, klice, _ in config_flow.SEKCE)
        self.assertIn(const.CONF_SYNC_WATCHED, sekce["synchronizace"])
        self.assertIn(const.CONF_SYNC_CODE, sekce["synchronizace"])

    def test_vychozi_stav_je_vse_zapnute(self):
        self.assertEqual(sync_circles(self._Entry()), ("watched", "favourites", "history", "watchlist"))

    def test_vypnuty_okruh_vypadne(self):
        entry = self._Entry(options={const.CONF_SYNC_HISTORY: False})
        self.assertEqual(sync_circles(entry), ("watched", "favourites", "watchlist"))

    def test_vypnute_vse_neposila_nic(self):
        """Prázdná sada znamená „nic", ne „vše" — `filter_circles(None)` by bylo „vše"."""
        entry = self._Entry(options={const.CONF_SYNC_WATCHED: False,
                                     const.CONF_SYNC_FAVOURITES: False,
                                     const.CONF_SYNC_HISTORY: False,
                                     const.CONF_SYNC_WATCHLIST: False})
        self.assertEqual(sync_circles(entry), ())
        from custom_components.nokturno.lib.sync import filter_circles
        self.assertEqual(filter_circles({"watched": {"x": {}}}, sync_circles(entry)), {})

    def test_vic_prehravacu_naraz(self):
        """Služba `play` bez `entity_id` pustí titul na všech vybraných."""
        schema = config_flow.preferences_schema({})
        for marker, validator in schema.schema.items():
            if marker.schema == const.CONF_KODI_ENTITY:
                self.assertTrue(validator.args[0].kwargs["multiple"])
                self.assertEqual(marker.default, [])
                break
        else:
            self.fail("kodi_entity není ve schématu")

    def test_ulozena_jedna_entita_se_prevede_na_seznam(self):
        """Do 6.6.0 se ukládal jeden řetězec; `EntitySelector(multiple=True)` chce seznam."""
        schema = config_flow.preferences_schema({const.CONF_KODI_ENTITY: "media_player.kodi"})
        for marker in schema.schema:
            if marker.schema == const.CONF_KODI_ENTITY:
                self.assertEqual(marker.default, ["media_player.kodi"])
                break

    def test_kazde_pole_synchronizace_ma_napovedu(self):
        """Sekce je nejméně samozřejmá z celého formuláře — nápověda tam patří ke všemu."""
        preklady = json.loads((ROOT / "custom_components/nokturno/translations/cs.json").read_text("utf-8"))
        sekce = preklady["options"]["step"]["init"]["sections"]["synchronizace"]
        self.assertEqual(set(sekce["data"]), set(sekce["data_description"]))


class TestPrekladyProHassfest(unittest.TestCase):
    """Co hlídá `hassfest` v CI — ať to nespadne až po vydání (stalo se u 6.6.0b3)."""

    SOUBORY = ("strings.json", "translations/cs.json", "translations/sk.json", "translations/en.json")

    def test_zadna_napoveda_neobsahuje_adresu(self):
        """hassfest: „the string should not contain URLs". Píše se slovní popis místo adresy."""
        adresa = re.compile(r"https?://")
        for soubor in self.SOUBORY:
            d = json.loads((ROOT / "custom_components/nokturno" / soubor).read_text("utf-8"))
            for blok, krok in (("config", "account"), ("options", "init")):
                for jmeno, sekce in (d[blok]["step"][krok].get("sections") or {}).items():
                    for klic, text in (sekce.get("data_description") or {}).items():
                        self.assertIsNone(adresa.search(text),
                                          f"{soubor}: adresa v nápovědě {jmeno}.{klic}")

    def test_vsechny_jazyky_maji_stejnou_strukturu(self):
        """Rozejít se smí text, ne klíče — jinak část formuláře ztratí popisky."""
        vzor = None
        for soubor in self.SOUBORY:
            d = json.loads((ROOT / "custom_components/nokturno" / soubor).read_text("utf-8"))
            tvar = {
                f"{blok}.{sekce}.{druh}.{klic}"
                for blok, krok in (("config", "account"), ("options", "init"))
                for sekce, obsah in (d[blok]["step"][krok].get("sections") or {}).items()
                for druh in ("data", "data_description")
                for klic in (obsah.get(druh) or {})
            }
            if vzor is None:
                vzor, prvni = tvar, soubor
            else:
                self.assertEqual(tvar, vzor, f"{soubor} se liší od {prvni}")


class TestPreklyadHodnotSelectu(unittest.TestCase):
    """Hodnoty selectu se přeloží jen přes `translation_key` — jinak HA vypíše
    uloženou hodnotu tak, jak je („quality", „size_desc")."""

    def _klic(self, pole):
        schema = config_flow.preferences_schema({})
        for marker, validator in schema.schema.items():
            if marker.schema == pole:
                return validator.args[0].kwargs.get("translation_key")
        self.fail(f"{pole} není ve schématu")

    def test_razeni_ma_translation_key(self):
        self.assertEqual(self._klic(const.CONF_SORT), "sort_streams")

    def test_jazyky_nesou_popisek_primo(self):
        """`translation_key` na ně nejde: hassfest povoluje v klíči jen `[a-z0-9-_]+`,
        a hodnoty jsou „CZ" a „—". Popisek je endonym přímo ve schématu."""
        schema = config_flow.preferences_schema({})
        for marker, validator in schema.schema.items():
            if marker.schema == const.CONF_PREF_LANG:
                volby = validator.args[0].kwargs["options"]
                self.assertEqual([v["value"] for v in volby], [l or "—" for l in const.LANGS])
                self.assertEqual(volby[1]["label"], "Čeština")
                self.assertIsNone(validator.args[0].kwargs.get("translation_key"))
                break
        else:
            self.fail("pref_lang není ve schématu")

    def test_vicero_prehravacu_ma_translation_key(self):
        self.assertEqual(self._klic(const.CONF_MULTI_PLAY), "multi_play")

    def test_kazda_hodnota_ma_preklad(self):
        for soubor in ("strings.json", "translations/cs.json", "translations/sk.json",
                       "translations/en.json"):
            d = json.loads((ROOT / "custom_components/nokturno" / soubor).read_text("utf-8"))
            selektory = d.get("selector") or {}
            self.assertEqual(set(selektory.get("sort_streams", {}).get("options", {})),
                             set(const.SORT_ORDERS), soubor)
            self.assertEqual(set(selektory.get("multi_play", {}).get("options", {})),
                             set(const.MULTI_PLAY_OPTIONS), soubor)
            self.assertNotIn("pref_lang", selektory, soubor)

    def test_selecty_sluzeb_maji_preklad(self):
        """Volby selectů ve `services.yaml` (`movie`, `ws`, `catalog_series`…) by se
        v UI služeb ukázaly jako kódy. Každý select nese `translation_key` a každá
        jeho volba má popisek ve všech jazycích."""
        radky = (ROOT / "custom_components/nokturno/services.yaml").read_text("utf-8").splitlines()
        selecty = {}
        for i, radek in enumerate(radky):
            if radek.strip() != "select:":
                continue
            odsazeni = len(radek) - len(radek.lstrip()) + 2
            telo = []
            for dalsi in radky[i + 1:]:
                if len(dalsi) - len(dalsi.lstrip()) < odsazeni:
                    break
                telo.append(dalsi.strip())
            klic = next((t.split(":", 1)[1].strip() for t in telo if t.startswith("translation_key:")), None)
            self.assertIsNotNone(klic, f"services.yaml:{i + 1} select bez translation_key")
            selecty.setdefault(klic, set()).update(t[2:] for t in telo if t.startswith("- "))
        for soubor in ("strings.json", "translations/cs.json", "translations/sk.json",
                       "translations/en.json"):
            d = json.loads((ROOT / "custom_components/nokturno" / soubor).read_text("utf-8"))
            for klic, volby in selecty.items():
                self.assertEqual(set(d["selector"].get(klic, {}).get("options", {})), volby,
                                 f"{soubor}: selector.{klic}")


class TestVyberPrehravace(unittest.TestCase):
    """Volba „co dělá Přehrát s víc přehrávači" jde z nastavení přes atribut
    senzoru do karty. Kontroluje se, že se ta tři místa nerozejdou."""

    KARTA = (ROOT / "custom_components/nokturno/www/nokturno-card.js").read_text("utf-8")

    def test_volba_je_v_sekci_prehravani(self):
        klice = next(k for jmeno, k, _ in config_flow.SEKCE if jmeno == "prehravani")
        self.assertIn(const.CONF_MULTI_PLAY, klice)

    def test_senzor_vystavuje_prehravace_i_rezim(self):
        zdroj = (ROOT / "custom_components/nokturno/sensor.py").read_text("utf-8")
        self.assertIn('"players"', zdroj)
        self.assertIn(f'"{const.CONF_MULTI_PLAY}"', zdroj)

    def test_karta_cte_stejna_jmena(self):
        self.assertIn("attributes.players", self.KARTA)
        self.assertIn("attributes.multi_play", self.KARTA)
        self.assertIn(f'=== "{const.MULTI_PLAY_FIRST}"', self.KARTA)

    def test_karta_ma_dlouhy_stisk(self):
        self.assertIn("pointerdown", self.KARTA)
        self.assertIn("_longPress", self.KARTA)


class TestHlidaniZJadra(unittest.TestCase):
    """Hlídání seriálů a titulů je od 8.3.0 v jádru (`lib/watch.py`) a sdílí ho Kodi."""

    def setUp(self):
        self.src = (COMPONENT / "__init__.py").read_text(encoding="utf-8")

    def test_logika_je_v_jadru(self):
        from custom_components.nokturno.lib import watch
        self.assertIs(aired_episodes, watch.aired_episodes)
        self.assertIs(skip_gap_candidates, watch.skip_gap_candidates)
        self.assertIn("watch_lib.check_series, engine, engine.store", self.src)
        self.assertIn("watch_lib.check_wanted, engine, engine.store", self.src)

    def test_nalez_odjinud_se_oznami(self):
        """Nový díl, který našlo Kodi a přišel synchronizací, musí HA ohlásit taky —
        na `nokturno_new_episode` visí automatizace."""
        self.assertIn("watch_lib.pending_notices", self.src)
        pohled = self.src.split("class NokturnoSyncView")[1].split("\nclass ")[0]
        self.assertIn("SIGNAL_SYNCED", pohled)
        self.assertIn("async_dispatcher_connect(hass, SIGNAL_SYNCED, po_synchronizaci)", self.src)


class TestKontrolovatDalDil(unittest.TestCase):
    """Vlaječka u seriálu v kartě posílá `want_to_watch` s `flag` — služba ho musí znát
    (schéma, services.yaml i překlady), jinak volání spadne na validaci."""

    def test_karta_a_sluzba_se_shoduji(self):
        karta = (ROOT / "custom_components/nokturno/www/nokturno-card.js").read_text("utf-8")
        self.assertIn('data-wflag="${i}"', karta)
        self.assertIn('"wflag"', karta)
        self.assertIn("flag: true", karta)
        zdroj = (ROOT / "custom_components/nokturno/__init__.py").read_text("utf-8")
        self.assertIn('vol.Optional("flag", default=False)', zdroj)
        self.assertIn("    flag:\n", (ROOT / "custom_components/nokturno/services.yaml").read_text("utf-8"))
        for soubor in ("strings.json", "translations/cs.json", "translations/sk.json", "translations/en.json"):
            data = json.loads((ROOT / "custom_components/nokturno" / soubor).read_text("utf-8"))
            self.assertIn("flag", data["services"]["want_to_watch"]["fields"], soubor)
