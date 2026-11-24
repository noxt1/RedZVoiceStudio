"""Диагностика режима «ЗАЖАТЬ»: кнопка должна заглушить русский.

Имитируем нажатие и отпускание кнопки и смотрим состояние моста.
"""

import os
import sys
import traceback

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))

import voice_studio  # noqa: E402


class FakeBridge:
    def __init__(self):
        self.running = True
        self.ducked = False
        self._q = []

    def set_duck(self, flag):
        self.ducked = bool(flag)
        print(f"  мост: duck={flag}", flush=True)

    def clear_stream(self):
        self._q.clear()

    def stream_pending(self):
        return bool(self._q)

    def push_pcm(self, pcm, sr):
        self._q.append(pcm)
        return True


def main() -> None:
    studio = voice_studio.Studio()
    live = studio.live
    bridge = FakeBridge()
    studio.bridge = bridge

    # движок считаем готовым (модели грузить не будем)
    class FakeTranslator:
        ready = True
        busy = False

        def translate_pcm(self, pcm, sr, floor=0.0):
            return True

        def poll(self):
            pass

    live.translator = FakeTranslator()
    live._ensure_engine = lambda: True

    # список микрофонов заполняется через root.after(400) — даём ему отработать
    def spin():
        studio.root.after(50, spin)

    studio.root.after(50, spin)
    deadline = 0
    while deadline < 20:
        studio.root.update()
        deadline += 1
        import time
        time.sleep(0.05)
    print(f"микрофон выбран: {live.mic_combo.get()!r}", flush=True)

    print("нажатие кнопки:", flush=True)
    try:
        live._hold_press()
    except Exception:
        traceback.print_exc()
    print(f"  русский заглушён: {bridge.ducked}", flush=True)
    print(f"  режим «зажато»: {live._hold_on}", flush=True)

    print("отпускание кнопки:", flush=True)
    try:
        live._hold_release()
    except Exception:
        traceback.print_exc()
    print(f"  режим «зажато»: {live._hold_on}", flush=True)
    print(f"  ждём окончания перевода: {live._hold_wait_play}", flush=True)

    # перевод «доиграл» -> русский возвращается
    live._check_hold()
    print(f"  русский вернулся: {not bridge.ducked}", flush=True)

    studio.root.destroy()


if __name__ == "__main__":
    main()
