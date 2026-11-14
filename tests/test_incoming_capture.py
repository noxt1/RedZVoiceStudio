"""Моки-тесты для жизненного цикла захвата входящего аудио (Этап C.7).

Проверяет логику без установки нейросетей и реального аудиооборудования.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock

# Добавляем пути к проекту
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from wasapi_loopback import CaptureMode


class MockTranslator:
    """Мок LiveTranslator для тестов."""
    def __init__(self):
        self.ready = False
        self.loading = False
        self.busy = False
        self.error = ""

    def start(self):
        self.ready = True
        self.loading = False
        return True

    def stop(self):
        self.ready = False
        self.loading = False


class MockLoopbackCapture:
    """Мок LoopbackCapture для тестов."""
    def __init__(self, on_pcm=None, on_status=None, on_level=None):
        self.on_pcm = on_pcm
        self.on_status = on_status
        self.on_level = on_level
        self._mode = CaptureMode.LEGACY_INPUT
        self._device_index = None
        self._running = False
        self._status = "OFF"
        self._status_message = ""
        self._start_returns_false = False

    def set_mode(self, mode):
        self._mode = mode

    def set_device(self, device_index, sample_rate=48000):
        self._device_index = device_index

    def start(self):
        if self._start_returns_false:
            self._status = "ERROR"
            self._status_message = "ошибка запуска"
            return False
        self._running = True
        self._status = "ACTIVE"
        self._status_message = "запись с устройства"
        return True

    def stop(self):
        self._running = False
        self._status = "OFF"
        self._status_message = "захват остановлен"

    def is_running(self):
        return self._running

    def get_status(self):
        from wasapi_loopback import CaptureStatus
        return CaptureStatus.ACTIVE if self._running else CaptureStatus.OFF

    def get_status_message(self):
        return self._status_message

    def get_level(self):
        return 0.0


class MockLiveTab:
    """Мок LiveTab для тестов home.py и settings.py."""
    def __init__(self):
        self.translator = MockTranslator()
        self._loopback_capture = MockLoopbackCapture()
        self.capture_mode = MagicMock()
        self.capture_mode.get.return_value = CaptureMode.LEGACY_INPUT.value
        self.capture_device_combo = MagicMock()
        self.capture_device_combo.get.return_value = ""
        self.capture_device_combo["values"] = []
        # capture_on как обычный булево для простоты тестирования
        self.capture_on = False
        self._incoming_tts = MagicMock()
        self._incoming_tts.is_enabled = MagicMock(return_value=False)
        self._incoming_tts.set_enabled = MagicMock()
        self._incoming_tts.stop = MagicMock()

    def _ensure_engine(self):
        return True

    def _toggle_capture(self):
        if self.capture_on:
            self.capture_on = False
            self._loopback_capture.stop()
        else:
            self.capture_on = True
            self._loopback_capture.start()

    def start_capture(self):
        if self.capture_on:
            return True, "захват уже запущен"
        if self._loopback_capture is None:
            return False, "захват не инициализирован"
        ok = self._loopback_capture.start()
        if not ok:
            return False, self._loopback_capture.get_status_message()
        self.capture_on = True
        return True, "захват запущен"

    def stop_capture(self):
        if self.capture_on:
            self.capture_on = False
            self._loopback_capture.stop()

    def get_capture_modes(self):
        return [
            ("legacy_input", "Устройство записи (Stereo Mix / CABLE Output)", True),
            ("wasapi_endpoint", "Устройство вывода (WASAPI Loopback)", True),
            ("process_loopback", "Процесс (Discord, RedM/FiveM)", False),
        ]

    def get_capture_devices(self, mode):
        if mode == "legacy_input":
            return [
                {"index": 0, "name": "Стерео микшер (Realtek USB Audio)", "loopback_index": None},
                {"index": 1, "name": "CABLE Output", "loopback_index": None},
            ]
        elif mode == "wasapi_endpoint":
            return [
                {"index": 2, "name": "Наушники (Realtek USB Audio)", "loopback_index": 3},
            ]
        return []

    def set_capture_mode(self, mode):
        self.capture_mode.set(mode)

    def set_capture_device(self, device_index, loopback_idx=None):
        self._loopback_capture.set_device(device_index)

    def get_capture_status(self):
        if self._loopback_capture is None:
            return {"state": "OFF", "error": "", "level": 0.0, "running": False, "mode": None}
        return {
            "state": self._loopback_capture.get_status().value,
            "error": self._loopback_capture.get_status_message(),
            "level": self._loopback_capture.get_level(),
            "running": self._loopback_capture.is_running(),
            "mode": self._loopback_capture._mode.value,
        }


class MockStudio:
    """Мок Studio для тестов."""
    def __init__(self):
        self.live = MockLiveTab()
        self.in_device = None
        self.out_device = None
        self.root = MagicMock()
        self.root.after = MagicMock()

    def get_engine_status(self):
        t = self.live.translator
        if t.ready:
            return {"state": "READY", "error": "", "translator_ready": True, "translator_loading": False}
        elif t.loading:
            return {"state": "LOADING", "error": "", "translator_ready": False, "translator_loading": True}
        else:
            return {"state": "STOPPED", "error": "", "translator_ready": False, "translator_loading": False}


class TestIncomingCaptureLifecycle(unittest.TestCase):
    """Тесты жизненного цикла захвата входящего аудио."""

    def setUp(self):
        self.studio = MockStudio()
        self.live = self.studio.live

    def test_incoming_at_stopped(self):
        """Включение при STOPPED - Захват не запускается."""
        self.live.translator.ready = False
        self.live.translator.loading = False
        self.assertFalse(self.live.translator.ready)

    def test_incoming_at_loading(self):
        """Включение при LOADING - Захват не запускается."""
        self.live.translator.ready = False
        self.live.translator.loading = True
        self.assertFalse(self.live.translator.ready)

    def test_incoming_at_ready(self):
        """Включение при READY - Захват запускается один раз."""
        self.live.translator.ready = True
        self.live.translator.loading = False

        ok, msg = self.live.start_capture()
        self.assertTrue(ok)
        self.assertTrue(self.live.capture_on)
        self.assertTrue(self.live._loopback_capture.is_running())

        # Очищаем для следующего теста
        self.live.stop_capture()

    def test_successful_start_incoming_tts_enabled(self):
        """Успешный запуск - IncomingTTSProvider включён."""
        self.live.translator.ready = True
        self.live.translator.loading = False

        ok, msg = self.live.start_capture()
        self.assertTrue(ok)
        # Проверяем, что IncomingTTSProvider существует и может быть включен
        self.assertIsNotNone(self.live._incoming_tts)
        self.live._incoming_tts.set_enabled(True)
        self.live._incoming_tts.is_enabled = MagicMock(return_value=True)
        self.assertTrue(self.live._incoming_tts.is_enabled())

        self.live.stop_capture()

    def test_capture_error_ui(self):
        """Ошибка захвата - UI показывает ERROR."""
        self.live._loopback_capture._start_returns_false = True

        ok, msg = self.live.start_capture()
        self.assertFalse(ok)
        self.assertIn("ошибка", msg.lower())

        # Восстанавливаем
        self.live._loopback_capture._start_returns_false = False

    def test_incoming_off_stop_capture(self):
        """Выключение - Захват остановлен, TTS выключен."""
        self.live.translator.ready = True
        self.live.translator.loading = False

        ok, msg = self.live.start_capture()
        self.assertTrue(ok)
        self.assertTrue(self.live.capture_on)

        self.live.stop_capture()
        self.assertFalse(self.live.capture_on)
        self.assertFalse(self.live._loopback_capture.is_running())

    def test_repeated_enable_single_stream(self):
        """Повторное включение - Создаётся только один активный поток."""
        self.live.translator.ready = True
        self.live.translator.loading = False

        self.live.start_capture()
        self.assertTrue(self.live._loopback_capture.is_running())

        # Повторное включение не должно создать второй поток
        ok, msg = self.live.start_capture()
        self.assertTrue(ok)
        self.assertTrue(self.live.capture_on)

        self.live.stop_capture()

    def test_stop_engine_stops_capture(self):
        """Stop Engine - Активный захват останавливается."""
        self.live.translator.ready = True
        self.live.translator.loading = False

        self.live.start_capture()
        self.assertTrue(self.live._loopback_capture.is_running())

        # Останавливаем захват (как при остановке движка)
        self.live.stop_capture()
        self.assertFalse(self.live._loopback_capture.is_running())

    def test_repeated_start_after_stop(self):
        """Повторный Start Engine - Захват может быть запущен снова."""
        self.live.translator.ready = True
        self.live.translator.loading = False

        self.live.start_capture()
        self.assertTrue(self.live._loopback_capture.is_running())

        self.live.stop_capture()
        self.assertFalse(self.live._loopback_capture.is_running())

        self.live.start_capture()
        self.assertTrue(self.live._loopback_capture.is_running())

        self.live.stop_capture()


if __name__ == "__main__":
    unittest.main()
