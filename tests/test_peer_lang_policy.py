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


class PeerLangFallback(unittest.TestCase):
    """Неподтверждённый язык не должен съедать фразу целиком."""

    def setUp(self):
        self.eng = object.__new__(lt.Engine)
        self.eng.peer_lang_confirmed = "es"
        self.eng._lang_hits = []
        self.eng.reverse_available = lambda code: code in ("es", "en", "it")

    def test_confirmed_language_is_used_for_unconfirmed_detection(self):
        self.assertEqual(self.eng._fallback_peer_lang("it", "hola amigo"), "es")

    def test_detected_language_used_when_nothing_confirmed(self):
        self.eng.peer_lang_confirmed = ""
        self.assertEqual(self.eng._fallback_peer_lang("it", "ciao amico"), "it")

    def test_russian_never_used_as_reverse_source(self):
        self.eng.peer_lang_confirmed = ""
        self.assertEqual(self.eng._fallback_peer_lang("ru", "hola amigo"), "")

    def test_guess_only_for_non_cyrillic_text(self):
        self.eng.peer_lang_confirmed = ""
        self.eng.reverse_available = lambda code: code == "es"
        self.assertEqual(
            self.eng._fallback_peer_lang("", "hola amigo", allow_guess=True),
            "es")
        self.assertEqual(
            self.eng._fallback_peer_lang("", "привет, друг", allow_guess=True),
            "")

    def test_no_model_means_no_fallback(self):
        self.eng.peer_lang_confirmed = "de"
        self.eng.reverse_available = lambda code: False
        self.assertEqual(self.eng._fallback_peer_lang("de", "hallo"), "")


class _Seg:
    text = "Hola amigo, ¿qué tal?"
    no_speech_prob = 0.0
    avg_logprob = -0.3


class _Info:
    def __init__(self, language: str, prob: float = 0.7):
        self.language = language
        self.language_probability = prob


class _FakeAsr:
    def __init__(self, language: str):
        self.info = _Info(language)

    def transcribe(self, audio, **kwargs):
        return [_Seg()], self.info


def _pcm(seconds: float = 2.0) -> bytes:
    """Структура как у речи: громкие слоги и тихие паузы (не ровный шум)."""
    import array
    import math
    n = int(seconds * lt.SR_ASR)
    block = max(1, int(lt.SR_ASR * 0.2))
    samples = array.array("h", (
        int((12000 if (i // block) % 2 else 800)
            * math.sin(2 * math.pi * 180 * i / lt.SR_ASR))
        for i in range(n)))
    return samples.tobytes()


class TranscribePeerKeepsPhrase(unittest.TestCase):
    """Главный баг живой сессии: фраза терялась из-за языка."""

    def setUp(self):
        self.eng = object.__new__(lt.Engine)
        self.eng.peer_lang = "auto"
        self.eng.peer_lang_confirmed = "es"
        self.eng._peer_lang_prob = 0.0
        self.eng._lang_hits = []
        self.eng._peer_lang_min_sec = 1.5
        self.eng._peer_lang_min_words = 2
        self.eng.beam_size = 1
        self.eng._asr_skip = ""
        self.eng.reverse_available = lambda code: code in ("es", "en", "it")

    def test_unconfirmed_language_still_yields_translation_source(self):
        self.eng.asr = _FakeAsr("it")
        text, lang = self.eng.transcribe_peer(_pcm(), lt.SR_ASR)
        self.assertTrue(text)
        self.assertEqual(lang, "es")
        self.assertEqual(self.eng._asr_skip, "")

    def test_foreign_text_detected_as_russian_is_not_left_untranslated(self):
        self.eng.peer_lang_confirmed = ""
        self.eng.asr = _FakeAsr("ru")
        text, lang = self.eng.transcribe_peer(_pcm(), lt.SR_ASR)
        self.assertTrue(text)
        self.assertNotEqual(lang, "ru")

    def test_real_russian_stays_russian(self):
        self.eng.peer_lang_confirmed = ""
        _Seg.text = "Привет, друг, как дела?"
        try:
            self.eng.asr = _FakeAsr("ru")
            _text, lang = self.eng.transcribe_peer(_pcm(), lt.SR_ASR)
        finally:
            _Seg.text = "Hola amigo, ¿qué tal?"
        self.assertEqual(lang, "ru")


if __name__ == "__main__":
    unittest.main()
