"""Отчёт для поддержки: логи и настройки есть, истории и голосов нет."""

import os
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import branding  # noqa: E402
import reports  # noqa: E402


class TestReport(unittest.TestCase):
    def _workspace(self, tmp: str) -> str:
        logs = os.path.join(tmp, "logs")
        os.makedirs(logs, exist_ok=True)
        with open(os.path.join(logs, "live_engine.log"), "w",
                  encoding="utf-8") as fh:
            fh.write("[play] мост: очередь пуста\n")
        with open(os.path.join(tmp, "ui_settings.json"), "w",
                  encoding="utf-8") as fh:
            fh.write('{"mode": "balanced"}')
        with open(os.path.join(tmp, "history.jsonl"), "w",
                  encoding="utf-8") as fh:
            fh.write('{"es": "secreto"}\n')
        profiles = os.path.join(tmp, "voice_profiles")
        os.makedirs(profiles, exist_ok=True)
        with open(os.path.join(profiles, "me.wav"), "wb") as fh:
            fh.write(b"RIFF0000")
        return tmp

    def test_report_contains_logs_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = self._workspace(tmp)
            path = reports.collect("снимок диагностики", workspace_dir=ws)
            self.assertTrue(os.path.exists(path))
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                text = zf.read("report.txt").decode("utf-8")
            self.assertIn("logs/live_engine.log", names)
            self.assertIn("settings.json", names)
            self.assertIn(branding.APP_VERSION, text)
            self.assertIn("снимок диагностики", text)
            # приватное не уходит
            self.assertNotIn("history.jsonl", names)
            self.assertFalse(any("voice_profiles" in n for n in names))

    def test_big_log_is_tailed(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = self._workspace(tmp)
            big = os.path.join(ws, "logs", "live_engine.log")
            with open(big, "wb") as fh:
                fh.write(b"x" * (reports.LOG_TAIL_BYTES + 5000))
                fh.write("ХВОСТ".encode("utf-8"))
            path = reports.collect("", workspace_dir=ws)
            with zipfile.ZipFile(path) as zf:
                data = zf.read("logs/live_engine.log")
            self.assertLess(len(data), reports.LOG_TAIL_BYTES + 1000)
            self.assertTrue(data.endswith("ХВОСТ".encode("utf-8")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
