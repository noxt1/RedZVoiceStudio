"""Правка аудиомоста: перевод в наушники не должен зависеть от того,
успел ли открыться монитор-поток к моменту первого чанка.
"""
import os
import sys
import unittest
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))

import mic_bridge  # noqa: E402


class BridgeMonitorQueue(unittest.TestCase):
    def _bridge(self):
        with mock.patch.object(mic_bridge, "pick_sample_rate",
                               return_value=48000):
            return mic_bridge.MicBridge(
                mic_device=None, render_device=None,
                mic_gain=0.0, monitor_device=1, monitor_gain=1.0)

    def test_default_ducked_safe(self):
        """Старт без нажатий: микрофон заглушён, пока кабель не подтверждён."""
        bridge = self._bridge()
        self.assertTrue(bridge.ducked)
        self.assertEqual(bridge.mic_gain, 0.0)

    def test_incoming_queued_before_monitor_open(self):
        bridge = self._bridge()
        self.assertIsNone(bridge._mon)
        self.assertTrue(bridge.push_incoming_pcm(np.zeros(2400), 24000))
        self.assertEqual(len(bridge._mon_q), 1)
        # В кабель входящий перевод НЕ попадает
        self.assertEqual(len(bridge._stream_q), 0)

    def test_outgoing_queued_to_monitor_before_open(self):
        bridge = self._bridge()
        self.assertTrue(bridge.push_pcm(np.zeros(2400), 24000))
        self.assertEqual(len(bridge._mon_q), 1)
        self.assertEqual(len(bridge._stream_q), 1)

    def test_long_burst_not_truncated(self):
        """Регрессия: длинная фраза приходила пачкой и теряла хвост.

        Движок отдаёт куски по 0,5 с (12000 сэмплов @24 кГц) сразу все.
        Очередь на 8 чанков выбрасывала остаток, и в Discord доходила
        только часть перевода.
        """
        bridge = self._bridge()
        bridge._mic_blocks.clear()
        chunk = np.ones(12000, dtype=np.float32)   # 0.5 с @ 24 кГц
        for _ in range(12):                        # 6 с перевода
            bridge.push_pcm(chunk, 24000)
        self.assertEqual(bridge.stream_dropped, 0)
        self.assertEqual(bridge._stream_len, 12 * 12000 * 2)
        out = np.zeros((1024, 1), dtype=np.float32)
        played = 0
        for _ in range(400):
            if not bridge.stream_pending():
                break
            bridge._mix_out(out, 1024)
            played += int((out[:, 0] > 0.5).sum())
        self.assertEqual(played, 12 * 12000 * 2,
                         "перевод должен дойти целиком")
        self.assertFalse(bridge.stream_pending())

    def test_mic_gain_untouched_by_volume_helpers(self):
        bridge = self._bridge()
        bridge.set_gains(phrase_gain=0.5, monitor_gain=0.7, out_gain=0.8)
        self.assertEqual(bridge.mic_gain, 0.0)

    def test_monitor_callback_stitches_short_chunks(self):
        """Регрессия: второй чанк перезаписывал начало первого — «обрывки»."""
        bridge = self._bridge()
        bridge._mon_sr = bridge.sr
        bridge.monitor_gain = 1.0
        bridge._mon_q.append(np.full(100, 0.2, dtype=np.float32))
        bridge._mon_q.append(np.full(100, 0.4, dtype=np.float32))
        out = np.zeros((150, 1), dtype=np.float32)
        bridge._mon_callback(out, 150, None, None)
        np.testing.assert_allclose(out[0:100, 0], 0.2, atol=0.02)
        np.testing.assert_allclose(out[100:150, 0], 0.4, atol=0.02)
        self.assertEqual(len(bridge._mon_q[0]), 50)


if __name__ == "__main__":
    unittest.main()
