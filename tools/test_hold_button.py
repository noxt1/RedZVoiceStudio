"""Тест режима «ЗАЖАТЬ»: русский пропадает, отпустил — вернулся.

Проверяем главное:
  1. пока зажато — русский в кабеле заглушён;
  2. отпустили — русский вернулся (но только когда испанский договорил);
  3. испанский не лезет в кабель, если перевод выключили.

    python tools\\test_hold_button.py
"""

from __future__ import annotations

import os
import sys
import threading

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import live_tab as lt  # noqa: E402


class FakeBridge:
    """Мост: запоминает заглушён ли русский."""

    def __init__(self):
        self.running = True
        self.ducked = False
        self._q: list = []

    def set_duck(self, flag):
        self.ducked = bool(flag)

    def clear_stream(self):
        self._q.clear()

    def stream_pending(self):
        return bool(self._q)

    def push_pcm(self, pcm, sr):
        self._q.append(pcm)
        return True


class FakeStudio:
    def __init__(self):
        self.bridge = FakeBridge()
        self.root = None


class FakeLabel:
    def config(self, **kw):
        pass


def make_tab() -> object:
    """Живой объект вкладки без tkinter (нужны только методы логики)."""
    studio = FakeStudio()
    tab = lt.LiveTab.__new__(lt.LiveTab)
    tab.studio = studio
    tab.state_lbl = FakeLabel()
    tab.hold_btn = FakeLabel()
    tab.cont_btn = FakeLabel()
    tab._hold_on = False
    tab._hold_wait_play = False
    tab._hold_vk = 0
    tab._out_enabled = False
    tab._mute_ru = False
    tab._cont_on = False
    tab._swap_busy = False
    tab._swap_wait_play = False
    tab._cont_buf = []
    tab._cont_silence = 0.0
    tab._cont_has_speech = False
    tab._strong_blocks = 0
    tab._noise = 0.005
    tab._rms_history = []
    tab._smooth = []
    tab._queue = []
    tab._queue_lock = threading.Lock()
    tab._play_lock = threading.Lock()
    tab._play_queue = []
    tab._play_stream = None
    tab._playing = False
    tab._stream = None
    tab.translator = None
    tab._engine_ready = True
    return tab


def test_hold_mutes_russian() -> bool:
    print("=== 1. пока зажато — русский заглушён ===")
    tab = make_tab()
    bridge = tab.studio.bridge

    # имитируем нажатие: заглушение происходит сразу, до первого слова
    tab._hold_on = True
    tab._apply_mute()
    muted = bridge.ducked
    print(f"  русский заглушён: {muted}")
    return muted


def test_release_restores() -> bool:
    print("\n=== 2. отпустил — русский вернулся ===")
    tab = make_tab()
    bridge = tab.studio.bridge

    tab._hold_on = True
    tab._apply_mute()
    muted_while = bridge.ducked

    # отпустили: испанский ещё играет -> русский пока не возвращаем
    tab._hold_on = False
    tab._hold_wait_play = True
    bridge._q.append(np.zeros(10, dtype=np.float32))   # что-то ещё играет
    tab._check_hold()
    still_muted = bridge.ducked

    # испанский договорил -> русский вернулся
    bridge._q.clear()
    tab._check_hold()
    restored = not bridge.ducked

    print(f"  во время перевода русский заглушён: {muted_while}")
    print(f"  перевод ещё играет — русский заглушён: {still_muted}")
    print(f"  перевод договорил — русский вернулся: {restored}")
    ok = muted_while and still_muted and restored
    print(f"  поведение верное: {'ок' if ok else 'ошибка'}")
    return ok


def test_cont_keeps_russian() -> bool:
    print("\n=== 3. без «зажать» русский идёт в кабель ===")
    tab = make_tab()
    bridge = tab.studio.bridge
    tab._cont_on = True
    tab._apply_mute()
    ok = not bridge.ducked
    print(f"  в режиме «Непрерывно» русский слышен: {ok}")

    # а с галочкой «только испанский» — заглушён
    tab._mute_ru = True
    tab._apply_mute()
    muted = bridge.ducked
    print(f"  с галочкой «только испанский» русский заглушён: {muted}")
    return ok and muted


def test_late_chunk_dropped() -> bool:
    print("\n=== 4. опоздавший чанк не играет ===")
    import base64
    tab = make_tab()
    played: list = []
    tab.studio.bridge.push_pcm = lambda pcm, sr: played.append(pcm) or True
    tab._out_enabled = False
    pcm = (np.ones(50, dtype=np.int16) * 100).tobytes()
    tab._on_engine_event("chunk", {"pcm": base64.b64encode(pcm).decode()})
    ok = not played
    print(f"  чанк дошёл до кабеля: {bool(played)} (ожидаем False)")
    return ok


def main() -> None:
    r1 = test_hold_mutes_russian()
    r2 = test_release_restores()
    r3 = test_cont_keeps_russian()
    r4 = test_late_chunk_dropped()
    print("\n=== ИТОГ ===")
    print(f"  зажато — русский заглушён:  {'ок' if r1 else 'ошибка'}")
    print(f"  отпустил — русский вернулся: {'ок' if r2 else 'ошибка'}")
    print(f"  без зажатия русский слышен:  {'ок' if r3 else 'ошибка'}")
    print(f"  опоздавшие чанки отброшены: {'ок' if r4 else 'ошибка'}")
    if not (r1 and r2 and r3 and r4):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
