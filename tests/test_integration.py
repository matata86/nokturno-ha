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
    KODI_PLUGIN, _continue_key, _encode_signed, _removed_by_user, _stats_title, android_play_intent,
    episode_target, kodi_image, kodi_url, skip_gap_candidates,
)
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
                self.assertIn("HU", validator.args[0].kwargs["options"])
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
        texty = json.dumps(strings, ensure_ascii=False).replace("Sosáč", "")   # vlastní jméno zdroje
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
            self.assertEqual(set(preklad["entity"]["sensor"]), {"downloads", "new_episodes", "trakt"})

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
        self.assertEqual(set(strings["config"]["error"]), {"ws_auth", "ws_network", "cz_pending", "cz_failed", "cz_network"})
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

    def test_kazdy_klic_nastaveni_ma_popisek(self):
        strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
        popisky = set(strings["config"]["step"]["user"]["data"])
        klice = set(config_flow.ACCOUNT_KEYS) | {m.schema for m in config_flow.preferences_schema({}).schema}
        self.assertEqual(klice - popisky, set(), "klíč nastavení bez popisku ve formuláři")

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
        self.assertIn("async def check_trakt(_now=None, only=None):", src)
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
