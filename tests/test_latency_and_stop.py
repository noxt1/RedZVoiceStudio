"""Проверка исправлений Этапа C.7.6: задержка, мегрельский, остановка."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))


class TestLatency(unittest.TestCase):
    """Очереди воспроизведения не должны копить секунды звука."""

    def test_bridge_queue_small(self):
        """deque maxlen для потока перевода — не больше 8 блоков (~170 мс)."""
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                            "mic_bridge.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        # maxlen=64 давал ~1.4 с задержки
        self.assertNotIn("deque(maxlen=64)", src,
                         "очередь на 64 блока даёт задержку ~1.4 с")
        self.assertIn("deque(maxlen=8)", src)

    def test_mic_blocks_small(self):
        """Буфер микрофона тоже уменьшен."""
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                            "mic_bridge.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("self._mic_blocks: deque[np.ndarray] = deque(maxlen=64)",
                         src)


class TestStopFlushesAudio(unittest.TestCase):
    """После остановки движка не должно звучать старьё."""

    def test_client_stop_clears_queue(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                            "live_client.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        i = src.find("def stop(self)")
        self.assertGreater(i, 0)
        stop_body = src[i:i + 1400]
        self.assertIn("get_nowait", stop_body,
                      "stop() должен выбросить накопленные чанки")
        self.assertIn("self._lines = queue.Queue()", stop_body,
                      "очередь должна пересоздаваться")

    def test_studio_stop_clears_translation(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                            "voice_studio.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        i = src.find("def stop_engine")
        self.assertGreater(i, 0)
        body = src[i:i + 2000]
        self.assertIn("_stop_translation", body,
                      "stop_engine должен гасить очередь воспроизведения")
        self.assertIn("_cont_on = False", body,
                         "флаги режимов должны сбрасываться")


class TestMegrelRemoved(unittest.TestCase):
    """Мегрельский удалён: ни в списке языков, ни в движке, ни в памяти."""

    def test_not_in_lang_order(self):
        import voice_lang
        self.assertNotIn("mg", voice_lang.LANG_ORDER)
        self.assertNotIn("mg", [c for c, _t in voice_lang.titles()])

    def test_not_in_langs_dict(self):
        import voice_lang
        self.assertNotIn("mg", voice_lang.LANGS)

    def test_engine_piper_disabled(self):
        path = os.path.join(os.path.dirname(__file__), "..", "tools",
                            "live_translate.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        # Piper должен быть отключён (заглушки)
        i = src.find("def _uses_piper")
        body = src[i:i + 400]
        self.assertIn("return False", body,
                      "Piper должен быть отключён")

    def test_no_piper_download(self):
        """В движке не должно быть скачивания голоса Piper."""
        path = os.path.join(os.path.dirname(__file__), "..", "tools",
                            "live_translate.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("urlretrieve", src,
                         "скачивание Piper осталось в коде")


class TestUnloadModels(unittest.TestCase):
    """Явная выгрузка моделей: память должна освобождаться."""

    def test_engine_has_unload(self):
        path = os.path.join(os.path.dirname(__file__), "..", "tools",
                            "live_translate.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("def unload_models", src)
        self.assertIn('cmd == "unload"', src)
        self.assertIn("gc.collect", src)

    def test_client_sends_unload(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                            "live_client.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        i = src.find("def stop(self)")
        body = src[i:i + 1200]
        self.assertIn('"unload"', body,
                      "клиент должен отправлять unload перед quit")


class TestAutoEnable(unittest.TestCase):
    """Автозапуск хоткеев и кабеля при старте."""

    def test_hotkeys_auto(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                            "voice_studio.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("_enable_live_hotkeys", src)
        self.assertIn("app.root.after(900, _enable_live_hotkeys)", src)

    def test_cable_auto(self):
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                            "voice_studio.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("_auto_enable_cable", src)
        self.assertIn("app.root.after(1500, _auto_enable_cable)", src)

    def test_ptt_auto_duck(self):
        """PTT глушит русский без галочки."""
        path = os.path.join(os.path.dirname(__file__), "..", "app",
                            "live_tab.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        i = src.find("def _restore_voice")
        body = src[i:i + 1200]
        # В PTT (_cont_on=False) русский возвращается всегда
        self.assertIn("self._mute_ru) and bool(self._cont_on)", body,
                      "PTT должен возвращать русский автоматически")


class TestMemorySavings(unittest.TestCase):
    """Загрузка моделей должна экономить RAM."""

    def test_low_cpu_mem_usage(self):
        path = os.path.join(os.path.dirname(__file__), "..", "tools",
                            "live_translate.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        i = src.find("def _load_chain")
        body = src[i:i + 2000]
        self.assertIn("low_cpu_mem_usage=True", body,
                      "модели должны грузиться с low_cpu_mem_usage")
        self.assertIn("torch.float16", body,
                      "нужен float16 для экономии RAM")

    def test_rss_logging(self):
        path = os.path.join(os.path.dirname(__file__), "..", "tools",
                            "live_translate.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("_rss_mb", src, "нет логирования памяти")


if __name__ == "__main__":
    unittest.main(verbosity=2)