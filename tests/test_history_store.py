"""История переводов на диске и экспорт (ROADMAP 8.3–8.4, 8.8)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (_ROOT, os.path.join(_ROOT, "app"),
          os.path.join(_ROOT, "app", "qtapp")):
    if p not in sys.path:
        sys.path.insert(0, p)

from PySide6.QtCore import QCoreApplication  # noqa: E402

import models  # noqa: E402

_APP = QCoreApplication.instance() or QCoreApplication([])


class HistoryStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.path = os.path.join(self.dir, "history.jsonl")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_persists_and_reloads(self) -> None:
        m = models.HistoryModel(path=self.path)
        m.add("out", "Привет", "Hola")
        m.add("in", "О нет", "Oh no")
        self.assertTrue(os.path.exists(self.path))

        again = models.HistoryModel(path=self.path)
        self.assertEqual(again.count(), 2)
        self.assertEqual(again.data(again.index(0), models.HistoryModel.RuRole),
                         "Привет")
        self.assertEqual(again.data(again.index(1), models.HistoryModel.DirRole),
                         "in")

    def test_remove_and_clear_rewrite_file(self) -> None:
        m = models.HistoryModel(path=self.path)
        m.add("out", "a", "a")
        m.add("out", "b", "b")
        m.removeAt(0)
        again = models.HistoryModel(path=self.path)
        self.assertEqual(again.count(), 1)
        self.assertEqual(again.data(again.index(0), models.HistoryModel.RuRole),
                         "b")

        again.clear()
        self.assertEqual(models.HistoryModel(path=self.path).count(), 0)

    def test_old_entries_are_pruned(self) -> None:
        old = time.time() - (models.HISTORY_RETENTION_DAYS + 1) * 86400
        fresh = time.time()
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": old, "dir": "out", "ru": "старое",
                                 "es": "viejo"}, ensure_ascii=False) + "\n")
            fh.write(json.dumps({"ts": fresh, "dir": "in", "ru": "новое",
                                 "es": "nuevo"}, ensure_ascii=False) + "\n")
        m = models.HistoryModel(path=self.path)
        self.assertEqual(m.count(), 1)
        self.assertEqual(m.data(m.index(0), models.HistoryModel.RuRole),
                         "новое")

    def test_broken_lines_are_skipped(self) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("не json\n\n")
            fh.write(json.dumps({"ts": time.time(), "dir": "out", "ru": "ok",
                                 "es": "ok"}, ensure_ascii=False) + "\n")
        self.assertEqual(models.HistoryModel(path=self.path).count(), 1)

    def test_export_json_and_txt(self) -> None:
        m = models.HistoryModel(path=self.path)
        m.add("out", "Привет", "Hola")
        m.add("in", "О нет", "Oh no")
        with mock.patch.object(models.sp, "workspace", lambda: self.dir):
            jpath = m.exportJson()
            tpath = m.exportTxt()
        self.assertTrue(jpath.endswith(".json") and os.path.exists(jpath))
        self.assertTrue(tpath.endswith(".txt") and os.path.exists(tpath))
        with open(jpath, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["ru"], "Привет")
        with open(tpath, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("RU -> ES", text)
        self.assertIn("Hola", text)

    def test_export_without_records_still_writes_file(self) -> None:
        m = models.HistoryModel(path=self.path)
        with mock.patch.object(models.sp, "workspace", lambda: self.dir):
            path = m.exportJson()
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), [])


if __name__ == "__main__":
    unittest.main()
