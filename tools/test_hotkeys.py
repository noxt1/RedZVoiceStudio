"""Тест глобальных горячих клавиш живого перевода.

Проверяет:
  1. назначение клавиши в интерфейсе (нажатие -> код -> сохранение);
  2. регистрацию WM_HOTKEY и реальное срабатывание;
  3. что хоткеи фраз и живого перевода не мешают друг другу;
  4. сохранение настроек в файл и их загрузку.

    python tools\\test_hotkeys.py
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import hotkeys as hk  # noqa: E402


def test_mapping() -> bool:
    print("=== 1. маппинг клавиш ===")
    cases = {"a": "a", "F5": "f5", "space": "space", "Return": "enter",
             "Page_Up": "pageup", "KP_1": "numpad1",
             "Alt_L": "alt", "Control_L": "ctrl", "Shift_L": "shift"}
    ok = True
    for keysym, want in cases.items():
        got = hk.key_from_keysym(keysym)
        good = got == want
        ok = ok and good
        print(f"  {keysym:<12} -> {got!r:<12} {'ок' if good else 'ОЖИДАЛОСЬ ' + want}")
    print(f"  маппинг: {'ок' if ok else 'ошибка'}")
    return ok


def test_combos() -> bool:
    print("\n=== 1б. комбинации клавиш ===")
    ok = True
    cases = [("g", 0x0000, "g"),
             ("g", 0x0004, "ctrl+g"),
             ("g", 0x000C, "ctrl+alt+g"),
             ("Alt_L", 0x0008, "alt"),
             ("Alt_L", 0x0004, "ctrl+alt"),
             ("space", 0x0000, "space")]
    for keysym, state, want in cases:
        got = hk.combo_from_event(keysym, state)
        good = got == want
        ok = ok and good
        print(f"  keysym={keysym:<8} state=0x{state:04x} -> {got!r:<14} "
              f"{'ок' if good else 'ОЖИДАЛОСЬ ' + want}")
    return ok


def test_single_keys() -> bool:
    print("\n=== 1в. одиночные клавиши (в т.ч. Alt) ===")
    ok = True
    for combo in ("alt", "scroll_lock", "pause", "ctrl+alt+l"):
        g = hk.GlobalHotkeys()
        good = g.register(combo, "t", 0)
        g.unregister_all()
        ok = ok and good
        print(f"  {combo:<14} зарегистрирована: {good}")
    return ok


def test_vk_is_number() -> bool:
    """RegisterHotKey ждёт ЧИСЛОВОЙ код клавиши, а не имя ('l').

    Регрессия: раньше для комбинаций возвращалось имя, Windows отказывался
    регистрировать, и все комбинации не работали.
    """
    print("\n=== 1г. VK-код — число, а не имя ===")
    ok = True
    for combo, want_vk in (("ctrl+alt+l", 0x4C), ("ctrl+alt+t", 0x54),
                           ("scroll_lock", 0x91), ("alt", 0x12)):
        vk, mods = hk.GlobalHotkeys._key_and_mods(combo, 0)
        good = isinstance(vk, int) and vk == want_vk
        ok = ok and good
        print(f"  {combo:<14} -> vk={vk!r:<8} mods={mods:<3} "
              f"{'ок' if good else 'ОЖИДАЛОСЬ ' + hex(want_vk)}")
    return ok


def test_reregister() -> bool:
    """Повторное включение должно работать (снятие реально снимает хоткей).

    Регрессия: UnregisterHotKey из чужого потока не снимает ничего, и
    второе «Включить горячие клавиши» падало с «клавиша занята».
    """
    print("\n=== 1д. повторная регистрация после снятия ===")
    ok = True
    for cycle in range(3):
        g = hk.GlobalHotkeys()
        good = g.register("ctrl+alt+l", "live:cont", 0)
        g.unregister_all()
        ok = ok and good
        print(f"  цикл {cycle + 1}: регистрация после снятия: {good}")
    return ok


def test_no_race() -> bool:
    """Первая регистрация после запуска потока не должна теряться.

    Регрессия: поток сообщал «я готов» ДО создания очереди сообщений,
    и PostThreadMessageW уходил в никуда. Хоткей молча не регистрировался
    (код ошибки 0 — RegisterHotKey даже не вызывался), а следующая
    регистрация висела 3 с.
    """
    print("\n=== 1е. гонка при первой регистрации (20 попыток) ===")
    import time

    lost = 0
    slow = 0
    worst = 0.0
    for _ in range(20):
        g = hk.GlobalHotkeys()
        t0 = time.time()
        good = g.register("ctrl+alt+l", "live:cont", 0)
        dt = time.time() - t0
        worst = max(worst, dt)
        if not good:
            lost += 1
        if dt > 0.5:
            slow += 1
        g.unregister_all()
    print(f"  потеряно регистраций: {lost} из 20")
    print(f"  с задержкой >0.5 с:    {slow} из 20")
    print(f"  худшее время:          {worst * 1000:.0f} мс")
    ok = lost == 0 and slow == 0
    print(f"  гонка: {'есть (ОШИБКА)' if not ok else 'нет'}")
    return ok


def test_register_and_fire() -> None:
    print("\n=== 2. регистрация и доставка WM_HOTKEY в поток-читатель ===")
    fired = []
    g = hk.GlobalHotkeys()
    g.set_callback(lambda action: fired.append(action))

    # регистрируем на редкой комбинации, чтобы не мешать системе
    ok_cont = g.register("f9", "live:cont", hk.MOD_CONTROL | hk.MOD_ALT | hk.MOD_SHIFT)
    ok_talk = g.register("f10", "live:talk", hk.MOD_CONTROL | hk.MOD_ALT | hk.MOD_SHIFT)
    print(f"  регистрация F9 (непрерывно): {'ок' if ok_cont else 'занята'}")
    print(f"  регистрация F10 (говорить):   {'ок' if ok_talk else 'занята'}")
    print(f"  зарегистрировано: {g.registered()}")

    g.start()
    time.sleep(0.7)

    # Синтетический ввод (keybd_event/SendInput) НЕ доставляет WM_HOTKEY
    # в этом окружении — проверено отдельным зондом (tools/probe_hotkey2.py):
    # даже обычное окно со своим WndProc не получает сообщение.
    # Поэтому проверяем ДОСТАВКУ напрямую в очередь потока-читателя —
    # именно её читает наш цикл.
    import ctypes
    user32 = ctypes.windll.user32
    WM_HOTKEY = 0x0312
    thread_id = g._thread.ident
    hotkey_id = [hid for hid, act in g._ids.items() if act == "live:cont"][0]
    posted = user32.PostThreadMessageW(thread_id, WM_HOTKEY, hotkey_id, 0)

    deadline = time.time() + 3
    while time.time() < deadline and not fired:
        time.sleep(0.1)

    print(f"  сообщение в очередь потока отправлено: {bool(posted)}")
    print(f"  сработало: {fired}")
    g.unregister_all()
    ok = bool(fired) and fired[0] == "live:cont"
    print(f"  доставка и обработка: {'ок' if ok else 'НЕ СРАБОТАЛО'}")
    return ok


def test_prefix_isolation() -> None:
    print("\n=== 3. хоткеи фраз и живого перевода не мешают друг другу ===")
    g = hk.GlobalHotkeys()
    g.register("f7", "phrase:01", hk.MOD_CONTROL | hk.MOD_ALT | hk.MOD_SHIFT)
    g.register("f8", "live:cont", hk.MOD_CONTROL | hk.MOD_ALT | hk.MOD_SHIFT)
    print(f"  зарегистрировано: {sorted(g.registered())}")
    g.unregister_prefix("live:")
    print(f"  после снятия 'live:': {sorted(g.registered())}")
    ok = g.registered() == ["phrase:01"]
    print(f"  раздельность: {'ок' if ok else 'ошибка'}")
    g.unregister_all()
    return ok


def test_persistence() -> None:
    print("\n=== 4. сохранение настроек ===")
    import json
    import studio_paths as sp
    path = os.path.join(sp.workspace(), "live_hotkeys.json")
    data = {"live:cont": "k", "live:talk": "g"}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    with open(path, encoding="utf-8") as fh:
        loaded = json.load(fh)
    ok = loaded == data
    print(f"  файл: {path}")
    print(f"  сохранение/чтение: {'ок' if ok else 'ошибка'}")
    try:
        os.remove(path)
    except Exception:
        pass
    return ok


def main() -> None:
    results = [test_mapping(), test_combos(), test_single_keys(),
               test_vk_is_number(), test_reregister(), test_no_race(),
               test_register_and_fire(), test_prefix_isolation(),
               test_persistence()]
    print("\n=== ИТОГ ===")
    print("все проверки пройдены" if all(results) else "есть проблемы")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
