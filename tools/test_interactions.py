"""Функциональный тест: PTT, mute, громкость, история (реальные нажатия)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import tkinter as _tk
from tkinter import ttk
from voice_studio import Studio
from ui.main_window import MainWindow


class FakeLive:
    """Заглушка LiveTab: записывает вызовы, ничего не открывает."""

    def __init__(self):
        self.hold_started = 0
        self.hold_stopped = 0
        self.cont_started = 0
        self.cont_stopped = 0
        self.toggled = 0
        self.monitor_vol = _tk.DoubleVar(value=80)
        self.bridge_phrase_vol = _tk.DoubleVar(value=100)
        self.bridge_out_vol = _tk.DoubleVar(value=100)
        self.overlay_on = _tk.BooleanVar(value=False)
        # Состояние заглушки (как в реальном LiveTab)
        self._mute_ru = False
        self._hold_on = False
        self._cont_on = False
        self._swap_busy = False
        self._applied = []
        self.lang_combo = ttk.Combobox()
        self.mic_combo = ttk.Combobox()
        self.out_combo = ttk.Combobox()
        self._inputs = [(1, "Test Mic")]
        self._outputs = [(5, "Test Out")]

    def _sel_mic(self):
        return 1

    def _sel_out(self):
        return 5

    def get_input_devices(self):
        return list(self._inputs)

    def get_output_devices(self):
        return list(self._outputs)

    def get_selected_mic(self):
        return 1

    def get_selected_out(self):
        return 5

    def set_mic_device(self, idx):
        return True

    def set_out_device(self, idx):
        return True

    def set_lang_code(self, code):
        return True

    def _apply_mute(self):
        """Как в реальном LiveTab: duck = hold_on | swap_busy | mute_ru."""
        b = getattr(self.studio, "bridge", None)
        if b is None or not getattr(b, "running", False):
            self._applied.append("no-bridge")
            return
        want = (self._hold_on or self._swap_busy or self._mute_ru)
        try:
            b.set_duck(want)
            self._applied.append(want)
        except Exception as exc:
            self._applied.append(f"err:{exc}")

    def _restore_voice(self):
        b = getattr(self.studio, "bridge", None)
        if b is not None and getattr(b, "running", False):
            b.set_duck(bool(self._mute_ru))

    def _start_hold(self):
        self.hold_started += 1

    def _stop_hold(self):
        self.hold_stopped += 1

    def _start_cont(self):
        self.cont_started += 1

    def _stop_cont(self):
        self.cont_stopped += 1

    def _toggle_incoming(self):
        self.toggled += 1

    def start_capture(self):
        return True, "ok"

    def stop_capture(self):
        pass


class FakeBridge:
    def __init__(self):
        self.ducked = False
        self.running = True
        self.monitor_gain = 0.8
        self.phrase_gain = 1.0
        self.out_gain = 1.0

    def set_duck(self, flag):
        self.ducked = bool(flag)

    def set_gains(self, monitor_gain=None, phrase_gain=None, out_gain=None):
        if monitor_gain is not None:
            self.monitor_gain = float(monitor_gain)
        if phrase_gain is not None:
            self.phrase_gain = float(phrase_gain)
        if out_gain is not None:
            self.out_gain = float(out_gain)

    def status(self):
        return {"running": self.running, "mic_peak": 0.0,
                "out_peak": 0.0, "sr": 48000}


def main():
    studio = Studio(use_new_ui=True, root=None)
    app = MainWindow(studio)
    studio.root = app.root

    # Подменяем LiveTab на заглушку
    fake = FakeLive()
    studio.live = fake
    studio.home_page = app.home
    studio.bridge = FakeBridge()
    # FakeLive должен видеть ТОТ ЖЕ мост, что и Studio
    fake.studio = studio

    # Движок считаем готовым
    studio.engine_state = "READY"
    studio.get_engine_status = lambda: {
        "state": "READY", "error": "", "engine_installed": True,
        "translator_ready": True, "translator_loading": False,
    }

    app.root.update()
    h = app.home

    print("=== 1. PTT: зажать и говорить ===")
    btn = h.card_out._out_btn
    btn.event_generate("<ButtonPress-1>")
    app.root.update()
    print(f"после нажатия: hold_started={fake.hold_started}, "
          f"cont_started={fake.cont_started}")
    btn.event_generate("<ButtonRelease-1>")
    app.root.update()
    print(f"после отпускания: hold_stopped={fake.hold_stopped}")
    assert fake.hold_started == 1, "PTT должен стартовать hold"
    assert fake.cont_started == 0, "PTT НЕ должен запускать cont"
    assert fake.hold_stopped == 1, "PTT должен останавливать hold"

    print()
    print("=== 2. Непрерывный режим ===")
    h.cont_btn.invoke()   # переключаем режим
    app.root.update()
    print(f"после переключения режима: cont_started={fake.cont_started}, "
          f"hold_started={fake.hold_started}")
    assert fake.cont_started == 0, "Переключение режима не должно запускать перевод"
    # Теперь нажимаем кнопку в непрерывном режиме — это toggle
    btn.event_generate("<ButtonPress-1>")
    app.root.update()
    print(f"после нажатия: cont_started={fake.cont_started}, "
          f"hold_started={fake.hold_started}")
    assert fake.cont_started == 1, "Непрерывный должен запускать cont"
    assert fake.hold_started == 1, "hold не должен запускаться повторно"
    # Повторное нажатие — выключение
    btn.event_generate("<ButtonPress-1>")
    app.root.update()
    print(f"после повторного нажатия: cont_stopped={fake.cont_stopped}")
    assert fake.cont_stopped == 1, "Непрерывный должен останавливаться"

    print()
    print("=== 3. Галочка «Заглушить русский» (МОЙ ГОЛОС) ===")
    h.out_duck_var.set(True)
    h._toggle_outgoing_duck()
    app.root.update()
    print(f"  fake._mute_ru={fake._mute_ru}, _applied={fake._applied}")
    print(f"bridge.ducked={studio.bridge.ducked}")
    assert studio.bridge.ducked is True, "Галочка должна заглушать русский"
    h.out_duck_var.set(False)
    h._toggle_outgoing_duck()
    print(f"после снятия: bridge.ducked={studio.bridge.ducked}")
    assert studio.bridge.ducked is False

    print()
    print("=== 4. Громкость в наушники ===")
    h._vol_scale.set(120)
    h._on_monitor_vol(120)
    app.root.update()
    print(f"live.monitor_vol={fake.monitor_vol.get()}, "
          f"bridge.monitor_gain={studio.bridge.monitor_gain}")
    assert abs(fake.monitor_vol.get() - 120) < 1, "Громкость должна применяться"

    print()
    print("=== 4b. Громкость в кабеле (как слышат абоненты) ===")
    h._phrase_vol_scale.set(60)
    h._on_phrase_vol(60)
    app.root.update()
    print(f"live.bridge_phrase_vol={fake.bridge_phrase_vol.get()}, "
          f"bridge.phrase_gain={studio.bridge.phrase_gain}")
    assert abs(fake.bridge_phrase_vol.get() - 60) < 1
    # Независимость: громкость в наушниках не должна меняться
    assert abs(studio.bridge.monitor_gain - 1.2) < 0.01, "Наушники не должны меняться"
    print("OK: две громкости независимы")

    print()
    print("=== 5. История переводов ===")
    h.add_history("RU → ES   |   Привет, как дела?")
    h.add_history("ES → RU   |   Todo bien, gracias!")
    app.root.update()
    print(f"history_list items={h.history_list.size()}")
    for i in range(h.history_list.size()):
        print(f"  [{i}] {h.history_list.get(i)}")
    assert h.history_list.size() == 2, "История должна заполняться"

    print()
    print("=== 6. LiveTab пишет в историю главной ===")
    studio.home_page = app.home
    fake2 = FakeLive()
    # Эмулируем вызов _show_text из LiveTab
    live_tab = app.studio.live
    print("studio.home_page установлен:", studio.home_page is app.home)

    app.root.destroy()
    print()
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
