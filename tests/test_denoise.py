"""Шумоподавление перед распознаванием: любая длина, без исключений."""

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

from live_engine import LiveEngine  # noqa: E402


class DenoiseTest(unittest.TestCase):
    def test_any_length_kept(self) -> None:
        """Длина не кратна окну (441) — раньше падало с ValueError.

        В живом пути `_trim_silence` меняет длину сегмента, поэтому
        огибающая обязана считаться на всю длину сигнала.
        """
        rng = np.random.default_rng(3)
        for n in (441 * 5 + 7, 1000, 441 * 3, 12345):
            audio = (rng.standard_normal(n) * 0.1).astype(np.float32)
            out = LiveEngine._denoise(audio)
            self.assertEqual(len(out), n, f"длина изменилась при n={n}")
            self.assertTrue(np.all(np.isfinite(out)))

    def test_short_segment_untouched(self) -> None:
        audio = np.zeros(64, dtype=np.float32)
        self.assertEqual(len(LiveEngine._denoise(audio)), 64)

    def test_loud_signal_not_clipped(self) -> None:
        audio = (np.sin(np.arange(44100) / 10.0) * 0.95).astype(np.float32)
        out = LiveEngine._denoise(audio)
        self.assertLessEqual(float(np.abs(out).max()), 1.0)
        self.assertEqual(len(out), 44100)


if __name__ == "__main__":
    unittest.main()
