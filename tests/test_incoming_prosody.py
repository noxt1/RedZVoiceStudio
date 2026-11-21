"""Входящий перевод озвучивается с тоном и живостью, как исходящая речь.

Раньше `_synthesize_incoming` синтезировал с жёстко заданными параметрами
(temp=0.78, speed=0.97) и без пунктуации по тону: ползунок «живость» на
входящую озвучку не влиял, злая реплика читалась так же ровно, как
нейтральная — отсюда жалоба «слышно, что это синтез».
"""

import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import live_translate as lt  # noqa: E402


class _FakeTensor:
    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        import numpy as np
        return np.zeros(240, dtype=np.float32)


class _CaptureTts:
    """XTTS-заглушка: запоминает текст и параметры синтеза."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def inference_stream(self, text, lang, gpt, spk, **kwargs):
        self.calls.append((text, lang, dict(kwargs)))
        yield _FakeTensor()


class IncomingProsodyTests(unittest.TestCase):
    def _engine(self, level: int) -> lt.Engine:
        eng = lt.Engine()
        eng.tts = _CaptureTts()
        eng.gpt_latent = None
        eng.spk_emb = None
        eng.liveliness = level
        return eng

    def _run(self, eng: lt.Engine, text: str) -> tuple[str, str, dict]:
        torch_stub = types.ModuleType("torch")
        torch_stub.manual_seed = lambda seed: None
        with mock.patch.dict(sys.modules, {"torch": torch_stub}):
            eng._synthesize_incoming(text, 1)
        self.assertTrue(eng.tts.calls, "синтез не вызван")
        return eng.tts.calls[-1]

    def test_liveliness_reaches_incoming_tts(self):
        soft = self._run(self._engine(0), "Ты меня достал.")
        loud = self._run(self._engine(3), "Ты меня достал.")
        self.assertLess(soft[2]["temperature"], loud[2]["temperature"])
        self.assertLess(soft[2]["top_k"], loud[2]["top_k"])
        # Злая реплика идёт с восклицанием: XTTS читает её резче.
        self.assertTrue(soft[0].endswith("!"), soft[0])
        self.assertTrue(loud[0].endswith("!"), loud[0])
        self.assertEqual(soft[1], "ru")

    def test_neutral_phrase_uses_tone_module_params(self):
        call = self._run(self._engine(2), "Я сейчас вернусь.")
        self.assertAlmostEqual(call[2]["temperature"], 0.79, places=2)
        self.assertEqual(call[2]["repetition_penalty"], 10.0)
        self.assertGreaterEqual(call[2]["speed"], 0.93)
        self.assertLessEqual(call[2]["speed"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
