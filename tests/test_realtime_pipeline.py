"""Тесты Real-Time Pipeline 2.0: режимы, частичный ASR, guards, очереди."""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
TOOLS = os.path.join(ROOT, "tools")
QTAPP = os.path.join(APP, "qtapp")
for path in (APP, QTAPP, TOOLS):
    if path not in sys.path:
        sys.path.insert(0, path)

import live_translate  # noqa: E402


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.engine = live_translate.Engine()
        self.engine.loaded = False   # ничего не грузим и не скачиваем

    def test_balanced_is_default(self):
        self.assertEqual(self.engine.mode, "balanced")
        self.assertEqual(self.engine.stream_chunk, 30)

    def test_fast_lowers_latency(self):
        info = self.engine.set_mode("fast")
        self.assertEqual(info["beam_size"], 1)
        self.assertEqual(info["stream_chunk"], 20)
        self.assertEqual(info["verify_attempts"], 0)

    def test_quality_raises_quality(self):
        info = self.engine.set_mode("quality")
        self.assertEqual(info["beam_size"], 3)
        self.assertEqual(info["stream_chunk"], 40)
        self.assertEqual(info["verify_attempts"], 2)
        self.assertEqual(info["asr_compute"], "float16")

    def test_manual_keeps_current_parameters(self):
        self.engine.set_mode("quality")
        info = self.engine.set_mode("manual")
        self.assertEqual(info["beam_size"], 3)
        self.assertEqual(info["asr_compute"], "float16")
        self.assertEqual(self.engine.mode, "manual")

    def test_unknown_mode_falls_back_to_balanced(self):
        info = self.engine.set_mode("turbo-max")
        self.assertEqual(info["mode"], "balanced")

    def test_mode_does_not_download(self):
        calls = []
        orig = live_translate.subprocess.Popen

        def spy(*a, **kw):
            calls.append(a)
            return orig(*a, **kw)

        live_translate.subprocess.Popen = spy
        try:
            for code in ("fast", "quality", "manual", "balanced"):
                self.engine.set_mode(code)
        finally:
            live_translate.subprocess.Popen = orig
        self.assertEqual(calls, [], "смена режима не должна ничего качать")

    def test_mode_reports_real_alternatives(self):
        info = self.engine.mode_info()
        self.assertGreaterEqual(info["asr_alternatives"], 1)
        self.assertEqual(info["tts_alternatives"], 1)


class _EmitCapture:
    """Перехват событий движка вместо записи в stdout."""

    def __init__(self):
        self.events = []
        self._orig = live_translate.emit

    def __enter__(self):
        live_translate.emit = lambda obj: self.events.append(dict(obj))
        return self

    def __exit__(self, *exc):
        live_translate.emit = self._orig

    def of(self, kind):
        return [e for e in self.events if e.get("event") == kind]

    def wait(self, kind, timeout=3.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.of(kind):
                return self.of(kind)[-1]
            time.sleep(0.02)
        return None


class PeerLoopTests(unittest.TestCase):
    def setUp(self):
        self.engine = live_translate.Engine()
        self.engine.peer_lang = "es"
        self.engine.peer_lang_confirmed = "es"
        self.engine.transcribe_peer = (
            lambda pcm, sr, partial=False: ("Hola amigo", "es"))
        self.engine._translate_peer_to_ru = lambda *a: "Привет, друг"
        self.engine._is_own_voice = lambda text: False
        self.engine.reverse_available = lambda src: True
        self.thread = threading.Thread(target=self.engine._peer_loop,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        # поток демон, выходим вместе с процессом теста
        pass

    def test_partial_is_shown_but_not_translated(self):
        with _EmitCapture() as cap:
            self.engine.push_peer_pcm(b"\x00\x00" * 320, 16000, partial=True)
            part = cap.wait("peer_partial")
            self.assertIsNotNone(part)
            self.assertEqual(part["text"], "Hola amigo")
            self.assertFalse(cap.of("peer_text"),
                             "промежуточный текст переводить нельзя")

    def test_same_phrase_translated_once(self):
        with _EmitCapture() as cap:
            self.engine.push_peer_pcm(b"\x00\x00" * 320, 16000)
            self.assertIsNotNone(cap.wait("peer_text"))
            self.engine.push_peer_pcm(b"\x00\x00" * 320, 16000)
            time.sleep(0.4)
            self.assertEqual(len(cap.of("peer_text")), 1,
                             "повторная фраза не должна переводиться снова")
            self.assertGreaterEqual(self.engine.cancelled, 1)

    def test_stale_result_is_dropped(self):
        def bump(pcm, sr, partial=False):
            self.engine.gen += 1
            return "Hola", "es"

        self.engine.transcribe_peer = bump
        with _EmitCapture() as cap:
            self.engine.push_peer_pcm(b"\x00\x00" * 320, 16000)
            time.sleep(0.5)
            self.assertFalse(cap.of("peer_text"))
            self.assertGreaterEqual(self.engine.cancelled, 1)

    def test_metrics_reported_with_phrase(self):
        with _EmitCapture() as cap:
            self.engine.push_peer_pcm(b"\x00\x00" * 320, 16000)
            msg = cap.wait("peer_text")
            self.assertIsNotNone(msg)
            for key in ("asr_ms", "mt_ms", "total_ms", "queue",
                        "dropped", "cancelled"):
                self.assertIn(key, msg)


class PeerNoiseTests(unittest.TestCase):
    def setUp(self):
        self.engine = live_translate.Engine()
        self.engine.peer_lang = "es"
        self.engine.peer_lang_confirmed = "es"

        class _Boom:
            def transcribe(self, *a, **kw):
                raise AssertionError("шум не должен доходить до Whisper")

        self.engine.asr = _Boom()

    def test_flat_noise_is_not_sent_to_asr(self):
        """Ровный шум/тишина не должны становиться «речью»: раньше пиковая
        нормализация делала из них фразу, и она уходила в перевод и озвучку."""
        import numpy as np
        for pcm in (b"\x00\x00" * 16000,
                    (np.full(16000, 300, dtype=np.int16)).tobytes()):
            text, _lang = self.engine.transcribe_peer(pcm, 16000)
            self.assertEqual(text, "")
            self.assertEqual(self.engine._asr_skip, "no_speech")


class HallucinationFilterTests(unittest.TestCase):
    def test_whisper_repeat_loop_is_dropped(self):
        """Реальный случай: на обрывке записи Whisper ушёл в цикл, и этот
        текст ушёл в перевод («Значит, я пойду к тебе...»)."""
        text = ("So I'm going to see you soon, but I'm going to see you "
                "all the seasons and you're all the seasons and you're "
                "all the seasons again.")
        self.assertTrue(live_translate.is_hallucination(text))

    def test_russian_repeat_loop_is_dropped(self):
        text = ("Значит, я пойду к тебе, но я пойду к тебе, чтобы увидеть "
                "тебя и тебя, и ты пойдёшь со мной, и ты пойдёшь со мной, "
                "и ты пойдёшь со мной, и мы пойдём домой, и будем спать")
        self.assertTrue(live_translate.is_hallucination(text))

    def test_normal_speech_with_a_repeat_is_kept(self):
        """Живая речь не должна отбрасываться: короткие повторы — норма."""
        for text in (
            "Слушай, я не знаю, я не знаю, честно",
            "Сегодня утром я вышел на улицу и увидел, как Маршал "
            "занимается сексом с ослом.",
            "Entonces voy a ir a verte, pero no sé si voy a ir",
            "Боже мой, Боже мой, Боже мой, Боже мой!",
            "Пошёл нахуй, пошёл нахуй, пошёл нахуй.",
            "Vete a la mierda, vete a la mierda, vete a la mierda.",
        ):
            self.assertFalse(live_translate.is_hallucination(text), text)


class QueueTests(unittest.TestCase):
    def test_peer_queue_is_bounded(self):
        engine = live_translate.Engine()
        for _ in range(30):
            engine.push_peer_pcm(b"\x00\x00" * 100, 16000)
        self.assertLessEqual(engine._peer_q.qsize(), 8)
        self.assertGreater(engine.dropped, 0)

    def test_partial_dropped_first_on_overflow(self):
        engine = live_translate.Engine()
        for _ in range(8):
            engine.push_peer_pcm(b"\x00\x00" * 100, 16000, partial=True)
        before = engine._peer_q.qsize()
        ok = engine.push_peer_pcm(b"\x00\x00" * 100, 16000)
        self.assertLessEqual(engine._peer_q.qsize(), before)
        self.assertTrue(ok, "финальный фрагмент должен вытеснить промежуточный")
        self.assertGreater(engine.dropped, 0)


class AppPipelineTests(unittest.TestCase):
    def setUp(self):
        from PySide6.QtCore import QCoreApplication

        self.app = QCoreApplication.instance() or QCoreApplication([])
        from live_engine import LiveEngine

        self.live = LiveEngine()

    def test_mode_event_updates_engine(self):
        self.live._on_event("mode", {"mode": "fast", "asr_model": "x",
                                     "asr_compute": "int8_float16",
                                     "beam_size": 1, "stream_chunk": 20,
                                     "verify_attempts": 0,
                                     "asr_alternatives": 2,
                                     "tts_alternatives": 1})
        self.assertEqual(self.live.mode, "fast")
        self.assertIn("beam 1", self.live.modeInfo)

    def test_peer_partial_cleared_by_final_phrase(self):
        self.live._on_event("peer_partial", {"text": "hola", "seq": 1})
        self.assertEqual(self.live.peerPartial, "hola")
        self.live._on_event("peer_text", {"lang": "es", "ru": "привет",
                                          "src": "hola"})
        self.assertEqual(self.live.peerPartial, "")

    def test_metrics_event_stored(self):
        self.live._on_event("metrics", {"dir": "out_tts", "tts_first_ms": 120,
                                        "dropped": 3, "cancelled": 1})
        self.assertEqual(self.live.lastMetrics["tts_first_ms"], 120)
        self.assertEqual(self.live.lastMetrics["dropped"], 3)

    @staticmethod
    def _chunk_msg(seq: int) -> dict:
        import base64

        import numpy as np

        pcm = (np.zeros(100, dtype=np.int16)).tobytes()
        return {"seq": seq, "pcm": base64.b64encode(pcm).decode("ascii")}

    def test_previous_phrase_chunk_still_plays(self):
        """Новая фраза не отменяет звук предыдущей.

        Раньше номер сравнивался на равенство с последней запрошенной
        фразой, и как только начиналась следующая, остаток предыдущей
        выбрасывался: в истории текст есть, а озвучки нет.
        """
        got = []
        self.live._emit_incoming_audio = lambda pcm: got.append(pcm)
        self.live._incoming_seq = 5
        self.live._on_event("incoming_chunk", self._chunk_msg(4))
        self.assertEqual(len(got), 1)

    def test_cancelled_chunk_dropped(self):
        """А после остановки/выключения звук прошлых фраз не играет."""
        got = []
        self.live._emit_incoming_audio = lambda pcm: got.append(pcm)
        self.live._incoming_seq = 5
        self.live._clear_incoming()
        self.live._on_event("incoming_chunk", self._chunk_msg(5))
        self.assertEqual(got, [])
        self.assertGreaterEqual(self.live._cancelled, 1)


if __name__ == "__main__":
    unittest.main()
