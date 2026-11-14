"""Диагностика оверлея: окно поверх всех? текст виден?

Проверяем по пикселям экрана в области окна оверлея.

    python tools\\diag_overlay.py
"""

from __future__ import annotations

import ctypes
import os
import sys
import time

from PIL import Image

user32 = ctypes.windll.user32

user32 = ctypes.windll.user32


def win_rect(hwnd):
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def grab(x, y, w, h):
    hdc = user32.GetDC(0)
    gdi32 = ctypes.windll.gdi32
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    gdi32.BitBlt(mdc, 0, 0, w, h, hdc, x, y, 0x00CC0020)

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16),
                    ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32),
                    ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32),
                    ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32)]

    bi = BIH()
    bi.biSize = ctypes.sizeof(BIH)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(0, hdc)
    return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)


def main() -> None:
    o = ov.Overlay(font_size=30, x=100, y=150)
    o.start()
    time.sleep(2.0)
    o.show("Как круто, брат!", "Que chido, guay!")
    time.sleep(1.2)

    hwnd = getattr(o, "_hwnd", None)
    # ВАЖНО: не трогаем o._tk из главного потока — окно принадлежит
    # потоку оверлея, tkinter из чужого потока бросает RuntimeError.
    if not hwnd:
        print("  оверлей не создал верхнее окно")
        o.stop()
        return
    for name, h in (("верхнее окно", hwnd),):
        try:
            l, t, r, b = win_rect(h)
            print(f"  {name}: hwnd={h} прямоугольник=({l},{t})-({r},{b}) "
                  f"размер={r - l}x{b - t}")
        except Exception as exc:
            print(f"  {name}: {exc}")

    l, t, r, b = win_rect(hwnd)
    w, h = max(1, r - l), max(1, b - t)
    img = grab(l, t, w, h)
    path = os.path.join(os.environ.get("TEMP", "."), "overlay_region.png")
    img.save(path)
    colors = img.getcolors(maxcolors=100000) or []
    bright = sum(c for c, col in colors if sum(col) > 600)
    print(f"  снимок области: {path}")
    print(f"  светлых пикселей (текст): {bright}")
    print(f"  текст в оверлее: {o._text!r}")
    o.stop()


if __name__ == "__main__":
    main()
