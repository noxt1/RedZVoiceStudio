"""Тесты обратного перевода (речь собеседника) и выбора моделей.

Проверяются чистые части без запуска движка: приём/отправка PCM,
сегментация, защита от аудиопетли, отчёт о моделях и сохранение настроек.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
TOOLS = os.path.join(ROOT, "tools")
QTAPP = os.path.join(APP, "qtapp")
for path in (APP, QTAPP, TOOLS):
    if path not in sys.path:
        sys.path.insert(0, path)

import live_client  # noqa: E402
import live_translate  # noqa: E402


class PeerPcmTests(unittest.TestCase):
    """send_peer_pcm должен принимать и bytes (loopback), и float32."""

    def _client(self):
        client = live_client.LiveTranslator(None, "x", "y")
        client.ready = True
        sent = []
        client._send = lambda msg: sent.append(msg)
        return client, sent

    def test_accepts_bytes(self):
        client, sent = self._client()
        pcm = (np.full(1600, 0.5) * 32767).astype(np.int16).tobytes()
        self.assertTrue(client.send_peer_pcm(pcm, 48000))
        self.assertEqual(sent[0]["cmd"], "peer")
        self.assertEqual(sent[0]["sr"], 48000)
        self.assertTrue(sent[0]["pcm"])

    def test_accepts_float_array(self):
        client, sent = self._client()
        arr = np.full(800, 0.25, dtype=np.float32)
        self.assertTrue(client.send_peer_pcm(arr, 16000))
        self.assertEqual(len(sent), 1)

    def test_empty_and_not_ready(self):
        client, sent = self._client()
        self.assertFalse(client.send_peer_pcm(b"", 48000))
        client.ready = False
        self.assertFalse(client.send_peer_pcm(b"\x00\x00", 48000))
        self.assertEqual(sent, [])


class ModelInfoTests(unittest.TestCase):
    """Отчёт о моделях строится по тому, что реально лежит на диске."""

    def setUp(self):
        self.engine = live_translate.Engine()

    def test_models_info_shape(self):
        info = self.engine.models_info()
        self.assertIn("asr", info)
        self.assertIn("mt", info)
        pairs = {m["pair"]: m for m in info["mt"]}
        for pair in ("ru->es", "es->ru", "en->ru"):
            self.assertIn(pair, pairs)
            self.assertIsInstance(pairs[pair]["installed"], bool)

    def test_reverse_available_uses_installed_models(self):
        with mock.patch.object(live_translate, "_reverse_mt_names",
                               return_value=["Helsinki-NLP/opus-mt-es-ru"]), \
                mock.patch.object(live_translate, "_model_installed",
                                  return_value=True):
            self.assertTrue(self.engine.reverse_available("es"))
        with mock.patch.object(live_translate, "_reverse_mt_names",
                               return_value=["Helsinki-NLP/opus-mt-es-ru"]), \
                mock.patch.object(live_translate, "_model_installed",
                                  return_value=False):
            self.assertFalse(self.engine.reverse_available("es"))

    def test_russian_needs_no_model(self):
        self.assertTrue(self.engine.reverse_available("ru"))

    def test_set_asr_rejects_missing_model(self):
        with mock.patch.object(live_translate, "_model_installed",
                               return_value=False):
            with self.assertRaises(RuntimeError):
                self.engine.set_asr("Systran/faster-whisper-small")


class PeerSegmentationTests(unittest.TestCase):
    """Захват собеседника: фразы уходят в движок, петля блокируется."""

    def setUp(self):
        from PySide6.QtCore import QCoreApplication

        self.app = QCoreApplication.instance() or QCoreApplication([])
        from live_engine import LiveEngine

        self.live = LiveEngine()
        self.sent = []
        translator = mock.Mock()
        translator.ready = True
        translator.send_peer_pcm = lambda pcm, sr: (
            self.sent.append((len(pcm), sr)) or True)
        translator.last_send_error = ""
        self.live._translator = translator

    def _feed(self, seconds, amp=0.3, sr=48000, block=0.1):
        """Речь с паузами: каждый третий блок — тихая пауза.

        Постоянный уровень VAD считает шумом (шумовой порог — нижний
        перцентиль), поэтому нужна модуляция как в живой речи.
        """
        block_len = int(sr * block)
        for i in range(int(seconds / block)):
            level = amp * 0.1 if i % 3 == 0 else amp
            data = (np.full(block_len, level, dtype=np.float32) * 32767)
            self.live._on_loopback_pcm(data.astype(np.int16).tobytes(), sr)
            self.app.processEvents()

    def test_speech_segment_goes_to_engine(self):
        self._feed(1.5)
        self.live._on_loopback_pcm(b"\x00\x00" * int(48000 * 0.9), 48000)
        self.assertTrue(self.sent)
        self.assertGreater(self.sent[0][0], 0)

    def test_silence_is_not_sent(self):
        self._feed(2.0, amp=0.0)
        self.assertFalse(self.sent)

    def test_echo_gate_blocks_capture(self):
        self.live._incoming_active = True
        self._feed(1.5)
        self.live._on_loopback_pcm(b"\x00\x00" * int(48000 * 0.9), 48000)
        self.assertFalse(self.sent)

    def test_long_phrase_is_split(self):
        # больше PEER_MAX_SEG (18 с) — фраза обязана уйти частями
        self._feed(20.0)
        self.assertTrue(self.sent)
        # куски не больше PEER_SEND_CHUNK секунд
        limit = int(48000 * (5.0 + 0.2)) * 2
        self.assertTrue(all(n <= limit for n, _sr in self.sent))


class IncomingRoutingTests(unittest.TestCase):
    """Входящее аудио идёт в наушники, но не в кабель."""

    def setUp(self):
        from PySide6.QtCore import QCoreApplication

        self.app = QCoreApplication.instance() or QCoreApplication([])
        from live_engine import LiveEngine

        self.live = LiveEngine()

    def test_incoming_not_into_cable_queue(self):
        pushed = []
        bridge = mock.Mock()
        bridge.running = True
        bridge.monitor_device = 7
        bridge.push_incoming_pcm = lambda pcm, sr: pushed.append(len(pcm)) or True
        self.live.bridge = bridge
        self.live._emit_incoming_audio(np.zeros(2400, dtype=np.float32))
        self.assertTrue(pushed)
        self.assertEqual(self.live._play_queue, [])

    def test_incoming_done_releases_gate(self):
        self.live._incoming_active = True
        self.live._suppress_capture = mock.Mock()
        self.live._incoming_finished()
        self.assertFalse(self.live._incoming_active)
        self.live._suppress_capture.assert_called_with(False)

    def test_peer_text_without_mt_is_reported(self):
        errors = []
        peers = []
        self.live.errorMessage.connect(errors.append)
        self.live.peerTextReady.connect(lambda a, b, c: peers.append((a, b, c)))
        self.live._on_event("peer_text", {
            "lang": "es", "src": "Hola", "ru": "", "missing_mt": "es->ru"})
        self.assertTrue(errors)
        self.assertIn("es->ru", errors[0])
        self.assertEqual(peers[0][0], "es")

    def test_peer_text_speaks_when_enabled(self):
        self.live._incoming_on = True
        self.live._translator = mock.Mock()
        self.live._translator.ready = True
        self.live._translator.incoming_speak = mock.Mock(return_value=True)
        self.live._suppress_capture = mock.Mock()
        self.live._on_event("peer_text", {"lang": "ru", "src": "Привет",
                                          "ru": "Привет"})
        self.live._translator.incoming_speak.assert_called_once()
        self.assertTrue(self.live.incomingActive)


class DirectionControlTests(unittest.TestCase):
    """Независимые направления: исходящий канал, язык пользователя."""

    def setUp(self):
        from PySide6.QtCore import QCoreApplication

        self.app = QCoreApplication.instance() or QCoreApplication([])
        from live_engine import LiveEngine

        self.live = LiveEngine()

    def test_outgoing_off_blocks_ptt(self):
        errors = []
        self.live.errorMessage.connect(errors.append)
        self.live.setIncomingEnabled = mock.Mock()
        self.live.setOutgoing(False)
        self.live._mic_idx = 3
        self.live.pressToTalk()
        self.assertFalse(self.live._hold_on)
        self.assertTrue(errors)
        self.assertIn("исходящий", errors[-1])

    def test_outgoing_flag_updates_property(self):
        self.live.setOutgoing(False)
        self.assertFalse(self.live.outgoingOn)
        self.live.setOutgoing(True)
        self.assertTrue(self.live.outgoingOn)

    def test_auto_download_off_by_default_and_forwarded(self):
        self.assertFalse(self.live.autoDownload)
        self.live._translator = mock.Mock()
        self.live._translator.ready = True
        self.live.setAutoDownload(True)
        self.assertTrue(self.live.autoDownload)
        self.live._translator.set_auto_download.assert_called_with(True)

    def test_package_event_updates_status(self):
        self.live._on_event("package", {"pair": "es->ru",
                                        "state": "downloading"})
        self.assertIn("es->ru", self.live.packageStatus)
        self.live._on_event("package", {"pair": "es->ru",
                                        "state": "installed"})
        self.assertIn("установлен", self.live.packageStatus)

    def test_src_lang_forwarded_to_engine(self):
        self.live._translator = mock.Mock()
        self.live._translator.ready = True
        self.live.setSrcLang("es")
        self.assertEqual(self.live.srcLang, "es")
        self.live._translator.set_src_lang.assert_called_with("es")

    def test_last_phrase_both_directions(self):
        self.live._on_text("Привет", "Hola", "neutral")
        self.assertEqual(self.live.lastOutOriginal, "Привет")
        self.assertEqual(self.live.lastOutTranslation, "Hola")
        self.live._on_event("peer_text", {"lang": "es", "src": "Hola",
                                          "ru": "Привет"})
        self.assertEqual(self.live.lastInOriginal, "Hola")
        self.assertEqual(self.live.lastInTranslation, "Привет")


class SettingsPersistenceTests(unittest.TestCase):
    """Языки и входящий перевод сохраняются в ui_settings.json."""

    def test_round_trip(self):
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.instance() or QCoreApplication([])
        import app_state

        tmp = tempfile.mkdtemp()
        with mock.patch.object(app_state.sp, "workspace", return_value=tmp):
            state = app_state.AppState()
            state.setPeerLang("es")
            state.setIncomingVolume(120)
            state.setIncoming(True)
            state.setOutgoing(False)
            state.setSrcLang("ru")
            state.setTargetLang("it")
            state.setAsrModel("Systran/faster-whisper-small")
            with open(os.path.join(tmp, "ui_settings.json"),
                      encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["peer_lang"], "es")
            self.assertEqual(data["incoming_volume"], 120)
            self.assertTrue(data["incoming_on"])
            self.assertEqual(data["target_lang"], "it")
            self.assertFalse(data["outgoing_on"])
            self.assertFalse(data["auto_download"])
            self.assertEqual(data["src_lang"], "ru")
            self.assertEqual(data["asr_model"],
                             "Systran/faster-whisper-small")
            state.shutdown()


if __name__ == "__main__":
    unittest.main()
