"""Автоматизация: запустить EXE и нажать «Озвучить всё моим голосом».

Нужен, чтобы поймать ошибку В СОБРАННОМ EXE (в исходниках не воспроизводится).

    python tools\\click_voice_all.py
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "dist", "RedZVoiceStudio.exe")
LOGS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio",
                    "workspace", "logs")


def find_window(needle: str = "RedZ Voice Studio") -> int:
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, lparam):  # noqa: ARG001
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        if needle in buf.value:
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append(((r.right - r.left) * (r.bottom - r.top), hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    if not found:
        return 0
    found.sort(reverse=True)
    return found[0][1]


def click_button(hwnd: int, needle: str) -> bool:
    """Найти кнопку по тексту (Tkinter рисует её в дочернем окне) и кликнуть."""
    # Ищем дочернее окно с нужным заголовком
    target = [0]
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(child, lparam):  # noqa: ARG001
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(child, buf, 512)
        if needle in buf.value:
            target[0] = child
            return False
        return True

    user32.EnumChildWindows(hwnd, WNDENUMPROC(cb), 0)
    if not target[0]:
        return False
    user32.SendMessageW(target[0], 0x00F5, 0, 0)  # BM_CLICK
    return True


def green_button_pos(hwnd: int):
    """Координаты центра зелёной кнопки внутри окна (в координатах окна)."""
    from PIL import Image
    import io
    import ctypes as C

    r = wt.RECT()
    user32.GetWindowRect(hwnd, C.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd)
    mem = user32.CreateCompatibleDC(hdc) if False else gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bitmap)
    user32.PrintWindow(hwnd, mem, 2)

    class BIH(C.Structure):
        _fields_ = [("biSize", C.c_uint32), ("biWidth", C.c_int32),
                    ("biHeight", C.c_int32), ("biPlanes", C.c_uint16),
                    ("biBitCount", C.c_uint16), ("biCompression", C.c_uint32),
                    ("biSizeImage", C.c_uint32), ("biXPelsPerMeter", C.c_int32),
                    ("biYPelsPerMeter", C.c_int32), ("biClrUsed", C.c_uint32),
                    ("biClrImportant", C.c_uint32)]

    class BI(C.Structure):
        _fields_ = [("bmiHeader", BIH), ("bmiColors", C.c_uint32 * 3)]

    info = BI()
    info.bmiHeader.biSize = C.sizeof(BIH)
    info.bmiHeader.biWidth = w
    info.bmiHeader.biHeight = -h
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0
    buf = C.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bitmap, 0, h, buf, C.byref(info), 0)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)

    px = img.load()
    xs, ys = [], []
    for yy in range(h):
        for xx in range(w):
            r0, g0, b0 = px[xx, yy]
            # ярко-зелёная кнопка приложения
            if g0 > 130 and r0 < 110 and b0 < 110 and g0 - r0 > 50 and g0 - b0 > 50:
                xs.append(xx)
                ys.append(yy)
    if not xs:
        return None
    return (sum(xs) // len(xs), sum(ys) // len(ys), r.left, r.top)


def main() -> None:
    print("запускаю EXE ...")
    proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    time.sleep(18)

    hwnd = find_window()
    if not hwnd:
        print("окно не найдено")
        proc.kill()
        return
    print("окно найдено:", hwnd)

    ok = click_button(hwnd, "Озвучить всё моим голосом")
    print("клик по кнопке:", ok)
    if not ok:
        # Tkinter не создаёт дочерних окон -> ищем зелёную кнопку по цвету
        pos = green_button_pos(hwnd)
        if not pos:
            print("зелёную кнопку не нашёл")
            proc.kill()
            return
        x, y, left, top = pos
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.5)
        user32.SetCursorPos(left + x, top + y)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        print(f"клик по зелёной кнопке: {left + x},{top + y}")

    time.sleep(25)

    print("\n=== логи ===")
    if os.path.isdir(LOGS):
        for f in sorted(os.listdir(LOGS), key=lambda n: os.path.getmtime(
                os.path.join(LOGS, n)), reverse=True)[:5]:
            path = os.path.join(LOGS, f)
            print(f"\n--- {f} ---")
            with open(path, encoding="utf-8", errors="replace") as fh:
                print(fh.read()[:3000])
    else:
        print("папки логов нет")

    proc.kill()


if __name__ == "__main__":
    main()
