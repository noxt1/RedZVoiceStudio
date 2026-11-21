"""Пакет подтверждения: протокол, счётчики отказов, тайминги фраз.

Проверяется то, что нельзя увидеть в тестах движка по отдельности:

* версия протокола в `boot` совпадает у GUI и движка, а расхождение
  (старый процесс движка рядом с новой сборкой) даёт предупреждение;
* счётчики «фраза была — перевода нет» по причинам видны в метриках;
* строка таймингов фразы доходит до `lastMetrics` (её печатает
  «Собрать отчёт») и не стирается следующим событием метрик.

Модели не грузятся: проверяется только транспорт событий.
"""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
QTAPP = os.path.join(APP, "qtapp")
TOOLS = os.path.join(ROOT, "tools")
for path in (APP, QTAPP, TOOLS):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import live_client as lc  # noqa: E402
import live_translate as lt  # noqa: E402


class ProtocolVersionTests(unittest.TestCase):
    def test_app_and_engine_versions_match(self) -> None:
        """Версии не должны разъехаться незаметно при правке протокола."""
        self.assertEqual(lc.PROTOCOL_VERSION, lt.PROTOCOL_VERSION)


class EngineCounterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = lt.Engine()

    def test_skip_counters_by_reason(self) -> None:
        self.engine._peer_skip("lang", "тест")
        self.engine._peer_skip("lang")
        self.engine._peer_skip("no_mt", "es->ru")
        counts = self.engine.stats()["skipped"]
        self.assertEqual(counts["lang"], 2)
        self.assertEqual(counts["no_mt"], 1)
        self.assertEqual(counts["empty"], 0)

    def test_unknown_reason_falls_back_to_empty(self) -> None:
        self.engine._peer_skip("что-то новое")
        self.assertEqual(self.engine.stats()["skipped"]["empty"], 1)

    def test_stats_report_protocol(self) -> None:
        self.assertEqual(self.engine.stats()["protocol"],
                         lt.PROTOCOL_VERSION)

    def test_queued_item_has_arrival_time(self) -> None:
        self.engine.push_peer_pcm(b"\x00\x00" * 10, 16000)
        item = self.engine._peer_q.get_nowait()
        self.assertEqual(len(item), 6)
        self.assertGreater(item[5], 0.0)

    def test_pending_timing_matches_phrase(self) -> None:
        self.engine._pending_timings.append(
            {"ru": "Привет", "asr_ms": 150, "mt_ms": 400, "arrival": 1.0})
        self.assertEqual(self.engine._take_phrase_timing("другое"), {})
        self.assertEqual(self.engine._take_phrase_timing("Привет")["asr_ms"],
                         150)
        self.assertEqual(self.engine._pending_timings, [])


class GuiEventTests(unittest.TestCase):
    def setUp(self) -> None:
        from PySide6.QtCore import QCoreApplication

        self.app = QCoreApplication.instance() or QCoreApplication([])
        from live_engine import LiveEngine

        self.live = LiveEngine()
        self.errors: list[str] = []
        self.logs: list[str] = []
        self.live.errorMessage.connect(self.errors.append)
        self.live.logLine.connect(self.logs.append)

    def test_matching_protocol_is_quiet(self) -> None:
        self.live._on_event("boot", {"protocol": lc.PROTOCOL_VERSION})
        self.assertEqual(self.errors, [])
        self.assertEqual(self.live.lastMetrics["protocol_ok"], "да")
        self.assertNotIn("protocol_desync", self.live.lastMetrics)

    def test_mismatched_protocol_warns(self) -> None:
        self.live._on_event("boot", {"protocol": lc.PROTOCOL_VERSION + 1})
        self.assertTrue(self.errors, "нет предупреждения о расхождении")
        self.assertIn("протокол", self.errors[0])
        self.assertIn("protocol_desync", self.live.lastMetrics)

    def test_old_engine_without_protocol_warns(self) -> None:
        self.live._on_event("boot", {})
        self.assertTrue(self.errors, "boot без protocol должен предупреждать")

    def test_skip_counts_reach_metrics(self) -> None:
        self.live._on_event("peer_skip", {
            "reason": "lang", "label": "язык не подтверждён",
            "detail": "мало слов", "counts": {"lang": 2, "empty": 0}})
        self.assertIn("lang: 2", self.live.lastMetrics["skipped"])
        self.assertTrue(any("без перевода" in line for line in self.logs))

    def test_timing_line_reaches_metrics_and_survives_metrics(self) -> None:
        self.live._on_event("phrase_timing", {
            "dir": "in", "seq": 3, "lang": "es", "wait_ms": 1,
            "asr_ms": 155, "mt_ms": 475, "gate_ms": 2,
            "first_ms": 520, "tts_ms": 1600, "total_ms": 2753})
        timing = self.live.lastMetrics["timing"]
        self.assertIn("asr_ms=155", timing)
        self.assertIn("gate_ms=2", timing)
        # очередное событие метрик не должно стирать тайминги/протокол
        self.live._on_event("metrics", {"event": "metrics", "asr_ms": 1})
        self.assertEqual(self.live.lastMetrics["timing"], timing)

    def test_metrics_merge_keeps_earlier_keys(self) -> None:
        self.live._on_event("boot", {"protocol": lc.PROTOCOL_VERSION})
        self.live._on_event("metrics", {"asr_ms": 10, "mt_ms": 20})
        self.assertEqual(self.live.lastMetrics["protocol_ok"], "да")
        self.assertEqual(self.live.lastMetrics["asr_ms"], 10)


if __name__ == "__main__":
    unittest.main()
