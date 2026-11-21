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


class AsrNameFixTest(unittest.TestCase):
    """Ослышки имён правятся текстом, а не подсказкой Whisper.

    Замер (out/probe_hw_halluc.py): hotwords из глоссария на не-речи
    (белый шум, розовый шум, цифровая тишина) давали 3 из 3 «de Linde,
    Blackwater, Saint Denis, Valentine…» — тот самый бред из фона; без
    подсказки — 0 из 3. Подсказка убрана, «Mars al» правится точечно.
    """

    def test_mars_al(self) -> None:
        self.assertEqual(
            live_translate.fix_asr_names("Ayer vi a Mars al en la calle."),
            "Ayer vi a Marshall en la calle.")

    def test_marsal_case_and_punctuation(self) -> None:
        self.assertEqual(live_translate.fix_asr_names("MARSAL, ven aquí"),
                         "Marshall, ven aquí")

    def test_other_text_untouched(self) -> None:
        text = "No te preocupes, ya voy para allá en un minuto."
        self.assertEqual(live_translate.fix_asr_names(text), text)

    def test_no_hotwords_passed_to_asr(self) -> None:
        eng = object.__new__(live_translate.Engine)
        live_translate.Engine._ensure_state(eng)
        eng.glossary = glossary.Glossary([{"src": "Marshall", "ru": "Маршал"}])
        eng.peer_lang = "es"
        eng.peer_lang_confirmed = "es"
        eng._asr_skip = ""
        eng.beam_size = 1
        seen = {}

        class _Seg:
            text = "Hola, Mars al."
            no_speech_prob = 0.0
            avg_logprob = -0.2

        class _Info:
            language = "es"
            language_probability = 0.9

        class _Asr:
            def transcribe(self, audio, **kwargs):
                seen.update(kwargs)
                return [_Seg()], _Info()

        eng.asr = _Asr()
        text, lang = eng.transcribe_peer(self._pcm(), live_translate.SR_ASR)
        self.assertNotIn("hotwords", seen)
        self.assertEqual(lang, "es")
        self.assertEqual(text, "Hola, Marshall.")

    @staticmethod
    def _pcm(seconds: float = 2.0) -> bytes:
        import array
        import math
        n = int(seconds * live_translate.SR_ASR)
        block = max(1, int(live_translate.SR_ASR * 0.2))
        samples = array.array("h", (
            int((12000 if (i // block) % 2 else 800)
                * math.sin(2 * math.pi * 180 * i / live_translate.SR_ASR))
            for i in range(n)))
        return samples.tobytes()


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
