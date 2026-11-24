"""Политика языка собеседника: подтверждённый язык не теряется на мелочи."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import live_translate as lt  # noqa: E402


class PeerLangPolicy(unittest.TestCase):
    def setUp(self):
        # объект без загрузки моделей: проверяем только решение о языке
        self.eng = object.__new__(lt.Engine)
        self.eng.peer_lang = "auto"
        self.eng.peer_lang_confirmed = "es"
        self.eng._peer_lang_prob = 0.9
        self.eng._lang_hits = []
        self.eng._peer_lang_min_sec = 1.5
        self.eng._peer_lang_min_words = 2

    def test_confirmed_language_accepts_short_phrase(self):
        ok, reason = self.eng._detect_peer_lang("es", 0.55, 0.6, 1)
        self.assertTrue(ok, reason)

    def test_short_phrase_of_new_language_still_rejected(self):
        ok, _ = self.eng._detect_peer_lang("it", 0.95, 0.5, 1)
        self.assertFalse(ok)

    def test_low_confidence_new_language_rejected(self):
        ok, _ = self.eng._detect_peer_lang("it", 0.40, 2.0, 5)
        self.assertFalse(ok)

    def test_confirmed_language_survives_low_confidence(self):
        # уверенность ниже порога, но язык тот же — фразу не выбрасываем
        ok, _ = self.eng._detect_peer_lang("es", 0.30, 2.0, 4)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
