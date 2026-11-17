"""Настройки декодирования перевода по направлению.

Замер (build/quality_sweep.py, 12 реальных фраз): обратный перевод выигрывает
от beam=4 (chrF 36,9 против 30,7), прямому greedy точнее (41,6 против 37,8)
и втрое быстрее. Тесты фиксируют это разделение.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import live_translate as lt  # noqa: E402


class MtBeamPolicy(unittest.TestCase):
    def _engine(self):
        eng = object.__new__(lt.Engine)
        eng._mt_reverse = lambda src: [("tok", "model")]
        eng._mt_cache = {}
        eng.lang = "es"
        self.calls = []

        def run_chain(text, chain, beam=1):
            self.calls.append(beam)
            return f"<{text}>"

        eng._run_chain = run_chain
        return eng

    def test_reverse_uses_beam_search(self):
        eng = self._engine()
        eng.translate_to_ru("Hola amigo", "es")
        self.assertEqual(self.calls, [lt.MT_BEAMS_REVERSE])
        self.assertGreaterEqual(lt.MT_BEAMS_REVERSE, 2)

    def test_forward_stays_greedy(self):
        eng = self._engine()
        eng._mt_for = lambda code: [("tok", "model")]
        eng.translate_text("Привет, друг")
        self.assertEqual(self.calls, [1])

    def test_empty_and_same_language_untouched(self):
        eng = self._engine()
        self.assertEqual(eng.translate_to_ru("", "es"), "")
        self.assertEqual(eng.translate_to_ru("Привет", "ru"), "Привет")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
