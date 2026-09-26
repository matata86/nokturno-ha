"""Kontroly nad zdrojákem integrace, které nepotřebují Home Assistant ani síť."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BALIK = ROOT / "custom_components" / "nokturno"


class TestNedosazitelnyKod(unittest.TestCase):
    def test_za_return_nic_neni(self):
        """Proxy souborů (`_proxy_file`) v 5.0.0b1 měla celé posílání dat odsazené pod
        `return` u větve 401/403 — funkce pak vracela None a HA posílal prázdnou 200.
        Testy HA view nespouštějí, tak aspoň tohle: za return/raise v bloku nesmí nic být."""
        for path in sorted(BALIK.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                for pole in ("body", "orelse", "finalbody"):
                    blok = getattr(node, pole, None)
                    if not isinstance(blok, list):
                        continue
                    for i, stmt in enumerate(blok[:-1]):
                        if isinstance(stmt, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                            self.fail(f"{path.name}:{blok[i + 1].lineno} kód za {type(stmt).__name__.lower()} se nikdy neprovede")

    def test_proxy_posila_data(self):
        tree = ast.parse((BALIK / "__init__.py").read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_proxy_file")
        self.assertIn("StreamResponse", ast.unparse(fn))
        self.assertIsInstance(fn.body[-1], ast.AsyncWith, "posílání dat patří do `async with upstream`, ne pod return")


class TestTitulkyNepovinne(unittest.TestCase):
    def test_titulky_nezastavi_prehrani_ani_stazeni(self):
        """WebShare občas nevydá soubor s titulky („File temporarily unavailable“) —
        výjimka z jejich rozklíčování dřív shodila celé nokturno.play i stažení."""
        tree = ast.parse((BALIK / "__init__.py").read_text(encoding="utf-8"))
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}
        pomocna = fns["_subtitle_links"]
        self.assertTrue(any(isinstance(n, ast.Try) for n in ast.walk(pomocna)))
        for jmeno in ("handle_play", "handle_download"):
            kod = ast.unparse(fns[jmeno])
            self.assertIn("_subtitle_links(stream)", kod)
            self.assertNotIn("for u in stream.get('subtitles')", kod)


if __name__ == "__main__":
    unittest.main()
