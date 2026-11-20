"""Стриминг коротких фраз: где включён, где осталась проверка."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "tools", "live_translate.py")


class TestStreamShort(unittest.TestCase):
    def _source(self) -> str:
        with open(SRC, encoding="utf-8") as fh:
            return fh.read()

    def test_fast_and_balanced_stream(self):
        src = self._source()
        self.assertIn("def _stream_speak", src,
                      "нет общего пути потокового синтеза")
        # в режимах Fast/Balanced короткие фразы идут потоком
        for mode in ("fast", "balanced"):
            block = src[src.find(f'"{mode}": {{'):]
            block = block[:block.find("},")]
            self.assertIn('"stream_short": True', block,
                          f"режим {mode} должен стримить короткие фразы")

    def test_quality_keeps_verification(self):
        src = self._source()
        for mode in ("quality", "manual"):
            block = src[src.find(f'"{mode}": {{'):]
            block = block[:block.find("},")]
            self.assertIn('"stream_short": False', block,
                          f"режим {mode} должен сохранять проверку")
        self.assertIn("if not short or self.stream_short:", src,
                      "выбор ветки синтеза потерян")


if __name__ == "__main__":
    unittest.main(verbosity=2)
