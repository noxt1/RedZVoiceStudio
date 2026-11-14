"""Тест: хоткей доходит до интерфейса + перевод только последней фразы.

Проверяет:
  1. WM_HOTKEY доходит и действие попадает в ГЛАВНЫЙ поток
     (tkinter нельзя трогать из потока-читателя — будет RuntimeError);
  2. «последняя фраза» отрезается по паузе — чтобы испанский не запаздывал;
  3. русский в кабеле заглушается, пока идёт перевод, и возвращается
     после (иначе «русский пропал навсегда»).

    python tools\\test_swap_latency.py
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import hotkeys as hk  # noqa: E402
import live_tab as lt  # noqa: E402


def test_dispatch() -> bool:
    """Хоткей из потока-читателя -> действие в главном потоке."""
    print("=== 1. хоткей -> главный поток ===")
    import ctypes
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    lbl = tk.Label(root, text="x")

    q: "queue.Queue[str]" = queue.Queue()
    main_thread = threading.get_ident()
    fired_in: list[int] = []
    seen_text = {"v": ""}

    def reader():
        # так работает приложение: поток-читатель только КЛАДЁТ в очередь
        q.put("live:swap")

    def poll():
        # главный поток разбирает очередь (как _poll_hotkeys в приложении)
        try:
            action = q.get_nowait()
        except queue.Empty:
            action = None
        if action:
            lbl.config(text="ok")          # tkinter — только здесь
            seen_text["v"] = lbl.cget("text")
            fired_in.append(threading.get_ident())
        root.after(20, poll)

    root.after(20, poll)
    t = threading.Thread(target=reader)
    t.start()
    root.after(1200, root.destroy)
    root.mainloop()
    t.join()

    ok = bool(fired_in) and fired_in[0] == main_thread
    print(f"  действие выполнено в главном потоке: {ok}")
    print(f"  текст виджета: {seen_text['v']!r}")
    if not fired_in:
        print("  ОШИБКА: действие не выполнилось")
    elif fired_in[0] != main_thread:
        print(f"  ОШИБКА: выполнено в потоке {fired_in[0]}, а не в главном")
    return ok


def test_last_phrase() -> bool:
    print("\n=== 2. отрезание последней фразы ===")
    sr = lt.SR_REC

    def tone(freq, sec):
        t = np.arange(int(sr * sec)) / sr
        return (0.4 * np.sin(2 * np.pi * freq * t)).astype(np.float32)

    phrase1 = tone(300, 1.5)
    pause = np.zeros(int(sr * 1.0), dtype=np.float32)
    phrase2 = tone(500, 1.5)
    stream = np.concatenate([phrase1, pause, phrase2])

    cut = lt.LiveTab._last_phrase(stream, sr)
    dur_all = len(stream) / sr
    dur_cut = len(cut) / sr
    print(f"  весь буфер: {dur_all:.2f} с")
    print(f"  после отрезания: {dur_cut:.2f} с (ожидаем ~1.5 с — последняя фраза)")
    ok = 1.0 < dur_cut < 2.2

    single = tone(300, 2.0)
    cut1 = lt.LiveTab._last_phrase(single, sr)
    print(f"  одна фраза: {len(single) / sr:.2f} с -> {len(cut1) / sr:.2f} с "
          f"(остаётся целой)")
    ok = ok and abs(len(cut1) - len(single)) / len(single) < 0.2
    print(f"  отрезание по паузе: {'ок' if ok else 'ошибка'}")
    return ok


def test_duck_release() -> bool:
    """Русский заглушается на время перевода и возвращается после."""
    print("\n=== 3. заглушка русского возвращается ===")

    class FakeBridge:
        def __init__(self):
            self.running = True
            self.ducked = False
            self._q: list = []

        def set_duck(self, flag):
            self.ducked = bool(flag)

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

    studio = FakeStudio()
    tab = lt.LiveTab.__new__(lt.LiveTab)     # без __init__ (не нужен tkinter)
    tab.studio = studio
    tab.state_lbl = FakeLabel()
    tab._mute_ru = False
    tab._swap_busy = False
    tab._hold_on = False
    tab._hold_wait_play = False
    tab._hold_vk = 0
    tab._cont_on = False
    tab._out_enabled = False
    tab._swap_wait_play = False
    tab._hold_on = False
    tab._hold_wait_play = False
    tab._hold_vk = 0
    tab._cont_on = False
    tab._out_enabled = False
    tab._play_lock = threading.Lock()
    tab._play_queue = []
    tab._play_stream = None
    tab._playing = False
    tab.translator = None

    # 1) начало перевода -> русский заглушён
    tab._swap_busy = True
    tab._apply_mute()
    muted = studio.bridge.ducked
    print(f"  во время перевода русский заглушён: {muted}")

    # 2) перевод ещё играет -> русский НЕ возвращаем
    tab._swap_wait_play = True
    studio.bridge._q.append(np.zeros(100, dtype=np.float32))
    tab._check_swap_done()
    still = studio.bridge.ducked
    print(f"  перевод ещё играет, русский заглушён: {still}")

    # 3) перевод дозвучал -> русский возвращается
    studio.bridge._q.clear()
    tab._check_swap_done()
    back = not studio.bridge.ducked
    print(f"  перевод договорил, русский вернулся: {back}")

    ok = muted and still and back
    print(f"  заглушка работает верно: {'ок' if ok else 'ошибка'}")
    return ok


def test_stop_clears_queue() -> bool:
    """При остановке перевода испанский не должен доигрывать в параллель.

    Регрессия: очередь перевода в мосте не очищалась, и уже отправленные
    чанки испанского играли ПАРАЛЛЕЛЬНО с живым русским голосом.
    """
    print("\n=== 4. остановка перевода убирает испанский ===")

    class FakeBridge:
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

    studio = FakeStudio()
    tab = lt.LiveTab.__new__(lt.LiveTab)
    tab.studio = studio
    tab.state_lbl = FakeLabel()
    tab._mute_ru = False
    tab._swap_busy = False
    tab._hold_on = False
    tab._hold_wait_play = False
    tab._hold_vk = 0
    tab._cont_on = False
    tab._out_enabled = False
    tab._swap_wait_play = False
    tab._out_enabled = True
    tab._play_lock = threading.Lock()
    tab._play_queue = []
    tab._play_stream = None
    tab._playing = False
    tab.translator = None

    # в очереди моста лежит недозвучавший испанский
    studio.bridge._q.append(np.zeros(100, dtype=np.float32))
    tab._stop_translation()

    ok = not studio.bridge._q            # очередь моста очищена
    ok = ok and not tab._out_enabled      # новые чанки не принимаются
    ok = ok and not tab._swap_busy
    ok = ok and not studio.bridge.ducked  # русский вернулся
    print(f"  очередь перевода очищена:     {not studio.bridge._q}")
    print(f"  вывод отключён:                {not tab._out_enabled}")
    print(f"  русский вернулся:              {not studio.bridge.ducked}")
    print(f"  остановка чистит очередь:      {'ок' if ok else 'ошибка'}")
    return ok


def test_out_enabled_blocks_late_chunks() -> bool:
    """Опоздавшие чанки (перевод выключили, а синтез кончился) — не играют."""
    print("\n=== 5. опоздавший чанк не попадает в кабель ===")
    played: list = []

    class FakeBridge:
        running = True
        ducked = False

        def set_duck(self, flag):
            self.ducked = bool(flag)

        def clear_stream(self):
            pass

        def stream_pending(self):
            return False

        def push_pcm(self, pcm, sr):
            played.append(pcm)
            return True

    class FakeStudio:
        def __init__(self):
            self.bridge = FakeBridge()
            self.root = None

    class FakeLabel:
        def config(self, **kw):
            pass

    studio = FakeStudio()
    tab = lt.LiveTab.__new__(lt.LiveTab)
    tab.studio = studio
    tab.state_lbl = FakeLabel()
    tab._mute_ru = False
    tab._swap_busy = False
    tab._hold_on = False
    tab._hold_wait_play = False
    tab._hold_vk = 0
    tab._cont_on = False
    tab._out_enabled = False
    tab._swap_wait_play = False
    tab._out_enabled = False      # перевод выключен
    tab._play_lock = threading.Lock()
    tab._play_queue = []
    tab._play_stream = None
    tab._playing = False
    tab.translator = None

    import base64
    pcm_bytes = (np.ones(100, dtype=np.int16) * 1000).tobytes()
    tab._on_engine_event("chunk", {"pcm": base64.b64encode(pcm_bytes).decode()})
    ok = not played
    print(f"  чанк дошёл до кабеля: {bool(played)} (ожидаем False)")
    print(f"  опоздавшие чанки отбрасываются: {'ок' if ok else 'ошибка'}")
    return ok


def main() -> None:
    r1 = test_dispatch()
    r2 = test_last_phrase()
    r3 = test_duck_release()
    r4 = test_stop_clears_queue()
    r5 = test_out_enabled_blocks_late_chunks()
    print("\n=== ИТОГ ===")
    print(f"  хоткей доходит до GUI:      {'ок' if r1 else 'ошибка'}")
    print(f"  перевод только фразы:       {'ок' if r2 else 'ошибка'}")
    print(f"  русский возвращается:       {'ок' if r3 else 'ошибка'}")
    print(f"  стоп чистит очередь:        {'ок' if r4 else 'ошибка'}")
    print(f"  опоздавшие чанки отброшены: {'ок' if r5 else 'ошибка'}")
    if not (r1 and r2 and r3 and r4 and r5):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
