"""Обратный перевод: реплика не рвётся на куски и не теряет озвучку.

Жалоба: при быстрой речи перевод идёт кусками, первая часть звучит,
вторая появляется только в истории; при медленной — переводится
«первая, вторая, третья часть» и смысл теряется.

Три причины, зафиксированные здесь тестами:

* длинная реплика собеседника уходила в движок кусками по 5 с, и КАЖДЫЙ
  кусок распознавался и переводился отдельно — без контекста;
* пауза 0,8 с внутри предложения считалась концом фразы;
* каждая новая фраза отменяла звук предыдущей (сравнение номера на
  равенство), а синтез шёл параллельными потоками в одну модель XTTS.

Звук синтетический, модели не грузятся — тест воспроизводим без GPU.
"""

from __future__ import annotations

import base64
import os
import sys
import threading
import time
import types
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

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import live_translate  # noqa: E402


class PeerPartJoinTests(unittest.TestCase):
    """Куски одной реплики склеиваются до распознавания."""

    def setUp(self) -> None:
        self.engine = live_translate.Engine()

    def test_parts_are_joined(self) -> None:
        self.assertIsNone(self.engine._join_peer_parts(b"a", last=False))
        self.assertIsNone(self.engine._join_peer_parts(b"b", last=False))
        self.assertEqual(self.engine._join_peer_parts(b"c", last=True), b"abc")
        # буфер пуст: следующая реплика не тянет за собой прошлую
        self.assertEqual(self.engine._join_peer_parts(b"x", last=True), b"x")

    def test_single_part_passes_unchanged(self) -> None:
        self.assertEqual(self.engine._join_peer_parts(b"one", last=True), b"one")

    def test_loop_transcribes_once_for_whole_phrase(self) -> None:
        """Один вызов ASR на всю реплику, а не на каждый кусок."""
        seen: list[int] = []
        done = threading.Event()

        def fake_transcribe(pcm, sr=16000, partial=False):
            seen.append(len(pcm))
            done.set()
            return "", "es"

        self.engine.transcribe_peer = fake_transcribe
        self.engine._peer_parts = []
        self.engine.push_peer_pcm(b"\x01\x00" * 800, 16000, last=False)
        self.engine.push_peer_pcm(b"\x01\x00" * 800, 16000, last=False)
        self.engine.push_peer_pcm(b"\x01\x00" * 400, 16000, last=True)
        threading.Thread(target=self.engine._peer_loop, daemon=True).start()
        self.assertTrue(done.wait(2.0), "фраза не дошла до распознавания")
        self.assertEqual(seen, [4000], "куски обработаны по отдельности")

    def test_queued_part_keeps_last_flag(self) -> None:
        self.engine.push_peer_pcm(b"\x00\x00" * 10, 16000, last=False)
        item = self.engine._peer_q.get_nowait()
        self.assertEqual(len(item), 5)
        self.assertFalse(item[3])
        self.assertIsNone(item[4])

    def test_queued_part_keeps_phrase_number(self) -> None:
        self.engine.push_peer_pcm(b"\x00\x00" * 10, 16000,
                                  last=False, phrase=7)
        self.assertEqual(self.engine._peer_q.get_nowait()[4], 7)


class PeerPartResetTests(unittest.TestCase):
    """Потерянный последний кусок не приклеивает следующую фразу."""

    def setUp(self) -> None:
        self.engine = live_translate.Engine()

    def test_next_phrase_number_drops_orphans(self) -> None:
        self.assertIsNone(self.engine._join_peer_parts(
            b"old1", last=False, phrase=1))
        self.assertIsNone(self.engine._join_peer_parts(
            b"old2", last=False, phrase=1))
        # последний кусок фразы 1 потерялся — приходит фраза 2
        self.assertIsNone(self.engine._join_peer_parts(
            b"new1", last=False, phrase=2))
        self.assertEqual(self.engine._join_peer_parts(
            b"new2", last=True, phrase=2), b"new1new2")

    def test_single_part_of_next_phrase_stays_alone(self) -> None:
        self.engine._join_peer_parts(b"old", last=False, phrase=1)
        self.assertEqual(self.engine._join_peer_parts(
            b"next", last=True, phrase=2), b"next")

    def test_same_phrase_number_still_joins(self) -> None:
        self.engine._join_peer_parts(b"a", last=False, phrase=5)
        self.engine._join_peer_parts(b"b", last=False, phrase=5)
        self.assertEqual(self.engine._join_peer_parts(
            b"c", last=True, phrase=5), b"abc")

    def test_timeout_drops_orphans_without_numbers(self) -> None:
        self.engine._join_peer_parts(b"old", last=False)
        self.engine._peer_parts_at -= live_translate.PEER_PARTS_TTL + 1.0
        self.assertEqual(self.engine._join_peer_parts(b"next", last=True),
                         b"next")
        self.assertEqual(self.engine._peer_parts, [])

    def test_fresh_parts_without_numbers_join(self) -> None:
        self.engine._join_peer_parts(b"a", last=False)
        self.engine._join_peer_parts(b"b", last=False)
        self.assertEqual(self.engine._join_peer_parts(b"c", last=True), b"abc")

    def test_buffer_is_bounded(self) -> None:
        chunk = b"\x00\x00" * 1000
        for _ in range(live_translate.PEER_PARTS_MAX_BYTES // len(chunk) + 3):
            self.engine._join_peer_parts(chunk, last=False)
            self.assertLessEqual(
                sum(len(p) for p in self.engine._peer_parts),
                live_translate.PEER_PARTS_MAX_BYTES)


class PeerJoinWindowTests(unittest.TestCase):
    """Пауза внутри предложения не делит реплику на две."""

    def setUp(self) -> None:
        from PySide6.QtCore import QCoreApplication

        self.app = QCoreApplication.instance() or QCoreApplication([])
        from live_engine import LiveEngine

        self.live = LiveEngine()
        self.sent: list[bool] = []          # флаги last отправленных кусков
        translator = mock.Mock()
        translator.ready = True
        translator.send_peer_pcm = lambda pcm, sr, last=True, phrase=None: (
            self.sent.append(last) or True)
        translator.last_send_error = ""
        self.live._translator = translator

    def _feed(self, seconds: float, amp: float = 0.3, sr: int = 48000,
              block: float = 0.1) -> None:
        block_len = int(sr * block)
        for i in range(int(seconds / block)):
            level = amp * 0.1 if i % 3 == 0 else amp
            data = (np.full(block_len, level, dtype=np.float32) * 32767)
            self.live._on_loopback_pcm(data.astype(np.int16).tobytes(), sr)
            self.app.processEvents()

    def _silence(self, seconds: float, sr: int = 48000) -> None:
        self.live._on_loopback_pcm(b"\x00\x00" * int(sr * seconds), sr)
        self.app.processEvents()

    def test_clause_pause_keeps_one_phrase(self) -> None:
        self._feed(1.5)
        self._silence(1.0)              # пауза на запятой
        self.assertEqual(self.sent, [])
        self._feed(1.0)                 # человек продолжает мысль
        self._silence(1.4)
        self.assertEqual(len(self.sent), 1, self.sent)

    def test_sentence_pause_starts_new_phrase(self) -> None:
        self._feed(1.5)
        self._silence(1.4)
        self._feed(1.5)
        self._silence(1.4)
        self.assertEqual(len(self.sent), 2)

    def test_long_phrase_parts_marked_not_last(self) -> None:
        self._feed(12.0)
        self._silence(1.4)
        self.assertGreater(len(self.sent), 1)
        self.assertEqual(self.sent[-1], True)
        self.assertTrue(all(flag is False for flag in self.sent[:-1]))

    def test_each_phrase_gets_its_own_number(self) -> None:
        """Номер реплики растёт: куски разных фраз не склеятся в движке."""
        seen: list[int | None] = []
        self.live._translator.send_peer_pcm = (
            lambda pcm, sr, last=True, phrase=None:
            seen.append(phrase) or self.sent.append(last) or True)
        self._feed(1.5)
        self._silence(1.4)
        self._feed(1.5)
        self._silence(1.4)
        self.assertEqual(len(seen), 2, seen)
        self.assertTrue(all(n is not None for n in seen), seen)
        self.assertEqual(len(set(seen)), len(seen), f"номер не растёт: {seen}")


class IncomingAudioTests(unittest.TestCase):
    """Новая фраза не отменяет звук предыдущей."""

    def setUp(self) -> None:
        from PySide6.QtCore import QCoreApplication

        self.app = QCoreApplication.instance() or QCoreApplication([])
        from live_engine import LiveEngine

        self.live = LiveEngine()
        self.played: list[int] = []
        self.live._emit_incoming_audio = lambda pcm: self.played.append(len(pcm))

    def _chunk(self, seq: int) -> None:
        pcm = np.zeros(240, dtype=np.int16).tobytes()
        self.live._on_event("incoming_chunk", {
            "seq": seq, "pcm": base64.b64encode(pcm).decode("ascii")})

    def test_previous_phrase_still_plays(self) -> None:
        self.live._incoming_seq = 5          # уже запрошена следующая фраза
        self._chunk(4)
        self.assertEqual(self.played, [240], "звук прошлой фразы выброшен")

    def test_stop_cancels_old_audio(self) -> None:
        self.live._incoming_seq = 5
        self.live._clear_incoming()
        self._chunk(5)
        self.assertEqual(self.played, [])


class IncomingQueueTests(unittest.TestCase):
    """Фразы озвучиваются по очереди, а не параллельно в одну модель."""

    def setUp(self) -> None:
        self.engine = live_translate.Engine()

    def test_phrases_are_voiced_in_order(self) -> None:
        seen: list[str] = []
        done = threading.Event()

        def fake(text, seq, prof):
            seen.append(text)
            if len(seen) == 2:
                done.set()

        self.engine._synthesize_incoming = fake
        self.engine.speak_incoming("один", 1)
        self.engine.speak_incoming("два", 2)
        self.assertTrue(done.wait(2.0), "вторая фраза не озвучена")
        self.assertEqual(seen, ["один", "два"])
        for _ in range(50):
            if not self.engine._incoming_worker_on:
                break
            time.sleep(0.02)
        self.assertFalse(self.engine._incoming_worker_on)

    def test_backlog_merges_instead_of_dropping(self) -> None:
        gate = threading.Event()
        started = threading.Event()

        def fake(text, seq, prof):
            started.set()
            gate.wait(2.0)

        self.engine._synthesize_incoming = fake
        self.engine.speak_incoming("первая", 1)
        self.assertTrue(started.wait(2.0))
        for i, text in enumerate(("вторая", "третья", "четвёртая"), start=2):
            self.engine.speak_incoming(text, i)
        gate.set()
        pending = " ".join(t for (t, _s, _p) in self.engine._incoming_jobs)
        self.assertIn("третья", pending)
        self.assertIn("четвёртая", pending)
        self.assertLessEqual(len(self.engine._incoming_jobs), 3)


class _FakeTensor:
    """Минимум от тензора torch для _synthesize_incoming."""

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return np.zeros(240, dtype=np.float32)


class _FakeTts:
    """XTTS-заглушка: долгий синтез из нескольких чанков."""

    def inference_stream(self, *args, **kwargs):
        for _ in range(5):
            time.sleep(0.1)
            yield _FakeTensor()


class TtsPriorityTests(unittest.TestCase):
    """Своя речь (PTT) не ждёт очередь входящих фраз на одном XTTS."""

    def setUp(self) -> None:
        self.engine = live_translate.Engine()
        self.order: list[str] = []
        gate = self.engine.lock
        self.assertIsInstance(gate, live_translate._TtsGate)
        orig_acquire = gate.acquire

        def spy(priority=live_translate._TtsGate.PRIO_OUT):
            orig_acquire(priority)
            self.order.append(threading.current_thread().name)

        gate.acquire = spy  # type: ignore[method-assign]
        self.engine.tts = _FakeTts()
        self.engine.gpt_latent = None
        self.engine.spk_emb = None

    def _wait_acquired(self, name: str, timeout: float = 3.0) -> None:
        deadline = time.time() + timeout
        while name not in self.order and time.time() < deadline:
            time.sleep(0.01)
        self.assertIn(name, self.order, f"{name} не получил XTTS: {self.order}")

    def _outgoing(self) -> None:
        """Как _stream_speak/_synth_full: обычный `with self.lock`."""
        with self.engine.lock:
            pass

    def test_outgoing_preempts_queued_incoming(self) -> None:
        torch_stub = types.ModuleType("torch")
        torch_stub.manual_seed = lambda seed: None
        with mock.patch.dict(sys.modules, {"torch": torch_stub}):
            first = threading.Thread(target=self.engine._synthesize_incoming,
                                     args=("первая фраза", 1), name="in1")
            first.start()
            self._wait_acquired("in1")
            second = threading.Thread(target=self.engine._synthesize_incoming,
                                      args=("вторая фраза", 2), name="in2")
            second.start()
            time.sleep(0.1)          # вторая входящая уже ждёт
            out = threading.Thread(target=self._outgoing, name="out")
            out.start()
            for thread in (first, second, out):
                thread.join(5)
        self.assertFalse(any(t.is_alive() for t in (first, second, out)),
                         "синтез завис на замке")
        self.assertEqual(self.order, ["in1", "out", "in2"],
                         f"исходящий встал за очередью входящих: {self.order}")


if __name__ == "__main__":
    unittest.main()
