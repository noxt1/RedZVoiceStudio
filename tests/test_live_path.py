"""Сквозной аудиопуть: потери, заглушка, очистка, предел очереди.

Проверки живут в `tools/live_path_check.py`, чтобы их можно было гонять
руками на чужой машине; здесь они же входят в обычный прогон тестов.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "app"))

import live_path_check  # noqa: E402


class TestLivePath(unittest.TestCase):
    def test_all_path_checks_pass(self):
        results = live_path_check.run_checks()
        failed = [r for r in results if not r["ok"]]
        self.assertEqual(failed, [], f"провалились проверки: {failed}")

    def test_long_translation_arrives_whole(self):
        result = live_path_check.check_queue_no_loss()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["dropped_chunks"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
