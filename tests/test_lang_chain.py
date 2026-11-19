"""Проверка цепочки выбора языка в новом UI (Этап C.7.5).

Главный баг: комбобокс был заполнен БЕЗ кодов ("Испанский", "Old West"),
а обработчик брал split(":")[0] — получал название вместо кода, ничего
не применялось, и перевод шёл на ПРЕДЫДУЩИЙ язык.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import studio_core as core


class TestLangComboValues(unittest.TestCase):
    """Комбобокс языка должен содержать коды, а не только названия."""

    def test_lang_titles_have_codes(self):
        """Каждая строка комбобокса начинается с кода."""
        titles = core.lang_titles()
        self.assertGreater(len(titles), 0)
        for code, title in titles:
            self.assertEqual(len(code), 2, f"код {code!r} не 2 символа")
            self.assertTrue(title)

    def test_split_gives_correct_code(self):
        """split(':')[0] даёт именно код языка."""
        for code, title in core.lang_titles():
            val = f"{code}: {title}"
            extracted = val.split(":")[0].strip()
            self.assertEqual(extracted, code,
                             f"{val!r} -> {extracted!r} вместо {code!r}")

    def test_mg_removed(self):
        """Мегрельский должен быть удалён полностью."""
        titles = dict(core.lang_titles())
        self.assertNotIn("mg", titles, "мегрельский должен быть удалён")
        codes = [c for c, _t in core.lang_titles()]
        self.assertEqual(codes, ["es", "en", "ow", "it"])

    def test_peer_lang_titles(self):
        """Языки собеседника тоже с кодами."""
        peer = core.peer_lang_titles()
        self.assertGreater(len(peer), 30)
        codes = [c for c, _t in peer]
        self.assertIn("auto", codes)
        self.assertNotIn("ka", codes, "грузинский убран вместе с мегрельским")


class TestSetLangCode(unittest.TestCase):
    """set_lang_code должен находить язык по коду."""

    def _make_live(self):
        from live_tab import LiveTab
        live = LiveTab.__new__(LiveTab)
        live.studio = MagicMock()
        live.translator = None
        # lang_combo — реальный объект с values, чтобы enumerate работал
        class _Combo:
            def __init__(self, values):
                self._values = list(values)
                self._idx = 0
            def __getitem__(self, key):
                if key == "values":
                    return self._values
                raise KeyError(key)
            def current(self, idx=None):
                if idx is None:
                    return self._idx
                self._idx = idx
        live.lang_combo = _Combo(
            [f"{c}: {t}" for c, t in core.lang_titles()])
        live._on_lang = MagicMock()
        return live

    def test_mg_removed_from_set_lang(self):
        """set_lang_code больше не находит mg."""
        live = self._make_live()
        self.assertFalse(live.set_lang_code("mg"))

    def test_finds_each_lang(self):
        for code, _t in core.lang_titles():
            live = self._make_live()
            self.assertTrue(live.set_lang_code(code), f"{code} не найден")

    def test_unknown_returns_false(self):
        live = self._make_live()
        self.assertFalse(live.set_lang_code("zz"))


class TestEngineLangList(unittest.TestCase):
    """Движок принимает языки из voice_lang.LANG_ORDER."""

    def test_lang_order_matches_titles(self):
        import voice_lang
        self.assertEqual(tuple(voice_lang.LANG_ORDER),
                         tuple(c for c, _t in voice_lang.titles()))

    def test_set_lang_source_uses_lang_order(self):
        path = os.path.join(os.path.dirname(__file__), "..", "tools",
                            "live_translate.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("voice_lang.LANG_ORDER", src)
        self.assertNotIn('code not in ("es", "en", "ow", "it")', src)

    def test_piper_removed(self):
        """Piper удалён вместе с мегрельским."""
        import voice_lang
        # Для существующих языков piper не нужен
        self.assertEqual(voice_lang.piper_voice("es"), "")
        self.assertEqual(voice_lang.piper_voice("en"), "")
        # mg больше нет в LANGS, значит info() вернёт es
        self.assertNotIn("mg", voice_lang.LANGS)


if __name__ == "__main__":
    unittest.main(verbosity=2)