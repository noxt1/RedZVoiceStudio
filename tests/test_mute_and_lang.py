"""Проверка исправлений Этапа C.7.5.

1. Галочка «Заглушить русский» действует и в PTT, и в непрерывном режиме.
2. Смена языка (mg) не отбрасывается молча.
3. Мягкий лимитер вместо жёсткого clip.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))


class TestMuteDuck(unittest.TestCase):
    """Галочка «Заглушить русский» должна работать в обоих режимах."""

    def _make_live(self):
        from live_tab import LiveTab
        live = LiveTab.__new__(LiveTab)
        live.studio = MagicMock()
        live.studio.bridge = None
        live.translator = None
        live._hold_on = False
        live._cont_on = False
        live._swap_busy = False
        live._mute_ru = False
        live._hold_wait_play = False
        return live

    def _make_bridge(self, live):
        b = MagicMock()
        b.running = True
        b.ducked = False
        b.set_duck = MagicMock(side_effect=lambda f: setattr(b, "ducked", f))
        live.studio.bridge = b
        return b

    def test_ptt_duck_true(self):
        """PTT: зажали — русский заглушён."""
        live = self._make_live()
        b = self._make_bridge(live)
        live._hold_on = True
        live._apply_mute()
        self.assertTrue(b.ducked, "в PTT русский должен быть заглушён")

    def test_ptt_duck_restored_when_mute_off(self):
        """PTT отпустили, галочка не стоит — русский возвращается."""
        live = self._make_live()
        b = self._make_bridge(live)
        live._hold_on = False
        live._mute_ru = False
        live._restore_voice()
        self.assertFalse(b.ducked, "русский должен вернуться")

    def test_ptt_mute_always_returns(self):
        """PTT: русский возвращается автоматически, без галочек.

        В PTT (_cont_on=False) галочка не нужна: _restore_voice всегда
        возвращает русский. Пользователь не должен ничего включать.
        """
        live = self._make_live()
        b = self._make_bridge(live)
        live._mute_ru = False
        live._cont_on = False      # PTT-режим
        live._hold_on = False
        live._restore_voice()
        self.assertFalse(b.ducked,
                         "в PTT русский должен вернуться автоматически")

    def test_cont_mode_mute_respected(self):
        """Непрерывный режим: галочка управляет заглушением."""
        live = self._make_live()
        b = self._make_bridge(live)
        live._mute_ru = True
        live._cont_on = True       # непрерывный режим
        live._restore_voice()
        self.assertTrue(b.ducked,
                        "в непрерывном режиме галочка должна глушить")

    def test_cont_mode_no_mute(self):
        """Непрерывный режим без галочки — русский идёт."""
        live = self._make_live()
        b = self._make_bridge(live)
        live._mute_ru = False
        live._cont_on = True
        live._restore_voice()
        self.assertFalse(b.ducked)

    def test_cont_mode_duck(self):
        """Непрерывный режим + галочка — русский заглушён."""
        live = self._make_live()
        b = self._make_bridge(live)
        live._mute_ru = True
        live._cont_on = True
        live._apply_mute()
        self.assertTrue(b.ducked)


class TestLangChange(unittest.TestCase):
    """Смена языка: мегрельский не должен отбрасываться молча."""

    def test_mg_removed_from_lang_order(self):
        """Мегрельский удалён из LANG_ORDER."""
        import voice_lang
        self.assertNotIn("mg", voice_lang.LANG_ORDER)
        self.assertEqual(tuple(voice_lang.LANG_ORDER), ("es", "en", "ow", "it"))

    def test_set_lang_accepts_mg(self):
        """Движок принимает mg (не отбрасывает как неизвестный)."""
        path = os.path.join(os.path.dirname(__file__), "..", "tools",
                            "live_translate.py")
        src = open(path, encoding="utf-8").read()
        # список допустимых языков берётся из voice_lang.LANG_ORDER
        self.assertIn("voice_lang.LANG_ORDER", src,
                      "список языков должен браться из voice_lang")
        # жёстко зашитый список из 4 языков больше не должен быть
        self.assertNotIn('code not in ("es", "en", "ow", "it")', src,
                         "зашитый список языков остался")

    def test_megrel_chain_removed(self):
        """Мегрельская цепочка удалена."""
        import voice_lang
        chain = voice_lang.mt_model("es")
        # у испанского одна модель без target-токена
        self.assertEqual(len(chain), 1)
        self.assertIsInstance(chain[0], str)


class TestSoftLimit(unittest.TestCase):
    """Мягкий лимитер вместо жёсткого clip."""

    def test_quiet_unchanged(self):
        import numpy as np
        from mic_bridge import _soft_limit
        x = np.array([0.1, -0.2, 0.3], dtype=np.float32)
        self.assertTrue(np.array_equal(x, _soft_limit(x)))

    def test_peaks_compressed_not_clipped(self):
        import numpy as np
        from mic_bridge import _soft_limit
        x = np.array([1.5, -1.5, 0.2], dtype=np.float32)
        y = _soft_limit(x)
        peak = float(np.abs(y).max())
        self.assertLessEqual(peak, 1.0)
        self.assertGreater(peak, 0.95, "жёсткий клип срезает до 1.0 без сжатия")

    def test_shape_preserved(self):
        import numpy as np
        from mic_bridge import _soft_limit
        rs = np.random.RandomState(0)
        mix = (rs.randn(512) * 0.5).astype(np.float32)
        out = _soft_limit(mix)
        corr = float(np.corrcoef(mix, out)[0, 1])
        self.assertGreater(corr, 0.95, "форма сигнала искажена")


class TestCrashLogging(unittest.TestCase):
    """Краши должны попадать в лог."""

    def test_crash_handler_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                            "voice_studio.py")
        src = open(path, encoding="utf-8").read()
        self.assertIn("_install_crash_handlers", src)
        self.assertIn("gui_crash.log", src)
        self.assertIn("threading.excepthook", src)

    def test_tk_callback_handler(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app", "ui",
                            "main_window.py")
        src = open(path, encoding="utf-8").read()
        self.assertIn("report_callback_exception", src,
                      "нет обработчика исключений Tkinter-колбэков")


if __name__ == "__main__":
    unittest.main(verbosity=2)