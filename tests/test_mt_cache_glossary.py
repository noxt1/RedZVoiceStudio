"""Глоссарий терминов и кэш переводов (ROADMAP 4.5–4.7)."""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (_ROOT, os.path.join(_ROOT, "tools"), os.path.join(_ROOT, "app")):
    if p not in sys.path:
        sys.path.insert(0, p)

import glossary
import live_translate


class AsrHotwordsTest(unittest.TestCase):
    """hotwords для Whisper: только имена, без строчных терминов."""

    def _engine(self, entries):
        eng = object.__new__(live_translate.Engine)
        live_translate.Engine._ensure_state(eng)
        eng.glossary = glossary.Glossary(entries) if entries is not None else False
        return eng

    def test_names_only(self) -> None:
        eng = self._engine([
            {"src": "Marshall", "ru": "Маршал"},
            {"src": "Arthur Morgan", "ru": "Артур Морган"},
            {"src": "burro", "ru": "осёл"},
        ])
        # глоссарий сортирует термины по длине: сначала «Arthur Morgan»
        self.assertEqual(eng._asr_hotwords(), "Arthur Morgan, Marshall")

    def test_no_glossary(self) -> None:
        self.assertIsNone(self._engine(None)._asr_hotwords())


class GlossaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.g = glossary.Glossary([
            {"src": "sheriff", "ru": "шериф", "es": "sheriff"},
            {"src": "Arthur Morgan", "ru": "Артур Морган", "es": "Arthur Morgan"},
        ])

    def test_long_term_wins(self) -> None:
        # «Arthur Morgan» должен матчиться целиком, а не по частям
        text, used = self.g.protect("Arthur Morgan rides to town")
        self.assertEqual(len(used), 1)
        self.assertNotIn("Arthur", text)

    def test_protect_restore_roundtrip(self) -> None:
        src = "The sheriff is looking for Arthur Morgan."
        protected, used = self.g.protect(src)
        self.assertNotIn("sheriff", protected.lower())
        self.assertNotIn("Arthur", protected)
        self.assertEqual(len(used), 2)
        # имитируем перевод: модель вернула метки как есть
        out = self.g.restore("Шериф ищет " + protected.split()[-1], used, "ru")
        self.assertNotIn("⟦", out)
        # каждая метка расшифровывается своим термином
        restored = self.g.restore(protected, used, "ru")
        self.assertIn("шериф", restored)
        self.assertIn("Артур Морган", restored)

    def test_unknown_target_keeps_source_form(self) -> None:
        protected, used = self.g.protect("sheriff")
        # для французского перевода термина нет — имя остаётся как в источнике
        # (в начале фразы термин получает заглавную — сравниваем без регистра)
        self.assertEqual(self.g.restore(protected, used, "fr").lower(), "sheriff")

    def test_no_terms_is_noop(self) -> None:
        text, used = self.g.protect("Просто фраза")
        self.assertEqual(text, "Просто фраза")
        self.assertEqual(used, [])

    def test_file_roundtrip(self) -> None:
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "glossary.json")
            glossary.ensure_file(path)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertTrue(data["entries"])
            loaded = glossary.Glossary.load(path)
            self.assertTrue(loaded.entries)


class EngineCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        try:
            import live_translate
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"движок не импортируется: {exc}")
        self.engine = live_translate.Engine()
        self.calls = 0

        def fake_chain(text, chain, beam=1, dst=""):
            self.calls += 1
            return "ПЕРЕВОД:" + text

        self.engine._mt_for = lambda code: []
        self.engine._mt_reverse = lambda src, dst="ru": []
        self.engine._run_chain = fake_chain
        self.engine.glossary = False

    def test_repeat_text_uses_cache(self) -> None:
        first = self.engine.translate_text("Привет, как дела?")
        second = self.engine.translate_text("Привет, как дела?")
        self.assertEqual(first, second)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.engine.cache_hits, 1)
        self.assertEqual(self.engine.cache_misses, 1)

    def test_cache_is_bounded(self) -> None:
        self.engine._text_cache_max = 3
        for i in range(10):
            self.engine.translate_text(f"фраза {i}")
        self.assertLessEqual(len(self.engine._text_cache), 3)

    def test_cache_key_includes_language(self) -> None:
        self.engine.translate_text("one")
        self.engine.lang = "en"
        self.engine.translate_text("one")
        self.assertEqual(self.calls, 2)


if __name__ == "__main__":
    unittest.main()
