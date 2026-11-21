"""Непрерывный монолог режется на короткие сегменты.

Жалоба владельца: собеседник слышит пару фраз в Discord и дальше тишина,
даже когда игрок говорит длинный монолог. Причина — принудительная
нарезка по MAX_SEG = 25 с: первый перевод начинался только на 25-й
секунде, а между кусками в кабель ничего не шло (замер:
out/probe_monologue_segments.py — 60 с монолога давали 3 фразы).
"""

from __future__ import annotations

import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "app"), os.path.join(ROOT, "app", "qtapp")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from live_engine import (  # noqa: E402
    ABS_SPEECH, BLOCK_SEC, MAX_SEG, SR_REC, LiveEngine)


def monologue(sec: float) -> np.ndarray:
    """Непрерывная речь без пауз: шум со слоговой огибающей."""
    n = int(SR_REC * sec)
    t = np.arange(n) / SR_REC
    env = 0.01 + 0.14 * np.maximum(0.0, np.sin(2 * np.pi * 5.0 * t)) ** 2
    rng = np.random.default_rng(7)
    return (rng.standard_normal(n) * env).astype(np.float32)


class MonologueSegmentationTests(unittest.TestCase):
    def _segments(self, sec: float = 60.0) -> list[float]:
        eng = LiveEngine()
        eng._cont_on = True
        # фон комнаты уже измерен, иначе первый сегмент отбросится
        eng._rms_history.extend([ABS_SPEECH * 0.2] * 120)
        segs: list[float] = []
        eng._queue_translate = (  # type: ignore[method-assign]
            lambda pcm, sr: segs.append(len(pcm) / sr))
        audio = monologue(sec)
        block = int(SR_REC * BLOCK_SEC)
        for i in range(0, len(audio) - block, block):
            chunk = audio[i:i + block].reshape(-1, 1)
            eng._cont_callback(chunk, len(chunk), None, None)
        eng._flush_segment()
        return segs

    def test_segment_is_short_enough_for_live_speech(self) -> None:
        # 25 с давало «пару фраз» за монолог — держим сегмент короче 12 с.
        self.assertLessEqual(MAX_SEG, 12.0)

    def test_monologue_gives_many_phrases_instead_of_two(self) -> None:
        segs = self._segments(60.0)
        self.assertGreaterEqual(
            len(segs), 5, f"за 60 с речи всего {len(segs)} фраз(ы)")
        self.assertLessEqual(max(segs), MAX_SEG + 0.1)
        # ни один кусок речи не потерян
        self.assertAlmostEqual(sum(segs), 60.0, delta=1.0)

    def test_first_phrase_does_not_wait_the_whole_monologue(self) -> None:
        segs = self._segments(60.0)
        self.assertTrue(segs)
        self.assertAlmostEqual(segs[0], MAX_SEG, delta=0.2)


if __name__ == "__main__":
    unittest.main()
