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
