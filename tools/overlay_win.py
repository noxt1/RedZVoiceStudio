"""Оверлей с субтитрами поверх игры — чистый Win32/GDI, без tkinter.

Игрок не слышит, что именно сказал его персонаж (в наушниках от сервера
тишина, а перевод уходит в кабель). Оверлей показывает текст поверх игры:
что сказано по-русски и как это звучит.

Почему не tkinter: окно Tk поверх игры не рисуется корректно —
прозрачность и текст конфликтуют (проверено: чёрный прямоугольник без
текста). Решение на чистом Win32 работает предсказуемо.

Особенности (важно для игры):
  * окно всегда сверху, прозрачное (цвет-ключ), без рамки;
  * ПРОЗРАЧНО ДЛЯ МЫШИ: WS_EX_TRANSPARENT — клики проходят в игру;
  * НЕ ЗАБИРАЕТ ФОКУС: WS_EX_NOACTIVATE — игра не теряет ввод;
  * не появляется в панели задач: WS_EX_TOOLWINDOW;
  * текст берётся из файла: «русский TAB перевод», гаснет через hold секунд.

Запуск:
    python tools\\overlay_win.py <файл_с_текстом>
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# --- стили окна ---
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
WS_POPUP = 0x80000000
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
LWA_COLORKEY = 0x00000001

# --- сообщения ---
WM_DESTROY = 0x0002
WM_PAINT = 0x000F
WM_CLOSE = 0x0010
WM_TIMER = 0x0113
CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001

# --- GDI ---
TRANSPARENT = 1
DT_LEFT = 0x00000000
DT_TOP = 0x00000000
DT_WORDBREAK = 0x00000010
DT_CALCRECT = 0x00000400
DT_SINGLELINE = 0x00000020

# Цвет-ключ: этот цвет становится прозрачным.
BG_RGB = 0x00001010          # BGR: #101216 -> R=0x16 G=0x12 B=0x10
FG_RGB = 0x00F2F2F2          # BGR: #f2f2f2
PEER_RGB = 0x007AC0E8        # BGR: #e8c07a — тёплый жёлтый для чужих реплик

FONT_NAME = "Segoe UI"
FONT_SIZE = 26

_DEBUG = os.environ.get("AURALOOM_OVERLAY_DEBUG") == "1"

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class PAINTSTRUCT(ctypes.Structure):
    """В Python 3.14 нет wintypes.PAINTSTRUCT — определяем сами."""
    _fields_ = [("hdc", wintypes.HDC), ("fErase", wintypes.BOOL),
                ("rcPaint", wintypes.RECT), ("fRestore", wintypes.BOOL),
                ("fIncUpdate", wintypes.BOOL),
                ("rgbReserved", ctypes.c_byte * 32)]


class WNDCLASS(ctypes.Structure):
    """Аналогично: wintypes.WNDCLASS в 3.14 отсутствует."""
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HMODULE), ("hIcon", ctypes.c_void_p),
                ("hCursor", ctypes.c_void_p), ("hbrBackground", ctypes.c_void_p),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF,
                                             wintypes.BYTE, wintypes.DWORD]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASS)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.SetTimer.restype = ctypes.c_uint
gdi32.SetTextColor.restype = wintypes.COLORREF
gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

# ВАЖНО: на 64-битной Windows HANDLE'ы (HDC, HFONT, HBRUSH) — 64-битные.
# Без этих типов ctypes обрезает их до 32 бит, и отрисовка молча не
# работает (текст не виден, окно пустое).
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
gdi32.CreateFontW.restype = wintypes.HGDIOBJ
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                            wintypes.HBRUSH]
user32.FillRect.restype = ctypes.c_int
# DrawTextW живёт в USER32 (в gdi32 её нет)
user32.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int,
                            ctypes.POINTER(wintypes.RECT), ctypes.c_uint]
user32.DrawTextW.restype = ctypes.c_int

# ВАЖНО: без argtypes 64-битные lparam/wparam обрезаются, и вызовы
# (DefWindowProcW, SetWindowPos, GetMessageW) падают с OverflowError.
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_long
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p,
                                  wintypes.BOOL]
user32.InvalidateRect.restype = wintypes.BOOL
user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.UINT,
                            ctypes.c_void_p]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = ctypes.c_long
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.DestroyWindow.argtypes = [wintypes.HWND]


def log_error(text: str) -> None:
    """Записать ошибку оверлея в файл (рядом с файлом текста)."""
    try:
        path = os.environ.get("AURALOOM_OVERLAY_LOG", "")
        if not path:
            return
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {text}\n")
    except Exception:
        pass


class OverlayApp:
    """Окно оверлея: прозрачное, поверх всех, сквозь мышь."""

    def __init__(self, text_file: str, x: int = 60, y: int = 60,
                 hold: float = 7.0) -> None:
        self.text_file = text_file
        self.x = x
        self.y = y
        self.hold = hold
        self.hwnd = 0
        self.own_text = ""
        self.peer_text = ""
        self.until = 0.0
        self.last_raw = None
        self._class_name = "AuraloomOverlayWin"

    # ---------- GDI-шрифт и кисть ----------
    def _font(self):
        return gdi32.CreateFontW(
            -FONT_SIZE, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0,
            5, 0, FONT_NAME)

    def _brush(self):
        return gdi32.CreateSolidBrush(BG_RGB)

    # ---------- процедура окна ----------
    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TIMER:
            self._poll()
            return 0
        if msg == WM_PAINT:
            ps = PAINTSTRUCT()
            user32.BeginPaint(hwnd, ctypes.byref(ps))
            hdc = user32.GetDC(hwnd)
            font = self._font()
            old_font = gdi32.SelectObject(hdc, font)
            brush = self._brush()
            old_brush = gdi32.SelectObject(hdc, brush)
            # заливаем фон цветом-ключом — иначе под текстом будет
            # непрозрачный чёрный прямоугольник
            client = wintypes.RECT(0, 0, 4000, 800)
            user32.FillRect(hdc, ctypes.byref(client), brush)
            gdi32.SetBkMode(hdc, TRANSPARENT)

            def measure(text: str) -> int:
                """Высота текста в пикселях (DrawTextW НЕ обновляет RECT,
                поэтому считаем через DT_CALCRECT отдельно)."""
                r = wintypes.RECT(0, 0, 2800, 400)
                user32.DrawTextW(hdc, text, -1, ctypes.byref(r),
                                 DT_LEFT | DT_TOP | DT_WORDBREAK | DT_CALCRECT)
                return max(0, r.bottom - r.top)

            own_h = measure(self.own_text) if self.own_text else 0
            peer_h = measure(self.peer_text) if self.peer_text else 0

            y = 10
            drawn = 0
            if self.own_text:
                # 1) наша речь — основным цветом
                gdi32.SetTextColor(hdc, FG_RGB)
                rect = wintypes.RECT(14, y, 2900, y + own_h + 4)
                drawn = user32.DrawTextW(hdc, self.own_text, -1,
                                         ctypes.byref(rect),
                                         DT_LEFT | DT_TOP | DT_WORDBREAK)
                y += own_h + 8
            peer_drawn = 0
            if self.peer_text:
                # 2) речь других игроков — другим цветом, ниже
                gdi32.SetTextColor(hdc, PEER_RGB)
                rect2 = wintypes.RECT(14, y, 2900, y + peer_h + 4)
                peer_drawn = user32.DrawTextW(hdc, self.peer_text, -1,
                                              ctypes.byref(rect2),
                                              DT_LEFT | DT_TOP | DT_WORDBREAK)
            gdi32.SelectObject(hdc, old_font)
            gdi32.SelectObject(hdc, old_brush)
            gdi32.DeleteObject(font)
            gdi32.DeleteObject(brush)
            user32.ReleaseDC(hwnd, hdc)
            user32.EndPaint(hwnd, ctypes.byref(ps))
            if _DEBUG:
                log_error(f"paint: своя={self.own_text!r} (h={own_h}) "
                          f"чужая={self.peer_text!r} (h={peer_h}) "
                          f"peer_drawn={peer_drawn} шрифт={font} hdc={hdc}")
            return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ---------- текст ----------
    def _poll(self) -> None:
        try:
            with open(self.text_file, encoding="utf-8") as fh:
                raw = fh.read()
        except Exception:
            raw = ""
        if raw != self.last_raw:
            self.last_raw = raw
            self._parse(raw)
        # текст гаснет сам — через hold секунд после последней реплики
        if (self.own_text or self.peer_text) and time.time() > self.until:
            self.own_text = ""
            self.peer_text = ""
            self._resize()

    def _parse(self, raw: str) -> None:
        """Разобрать файл оверлея.

        Формат — две строки:
          1) наша речь: «русский TAB перевод»
          2) речь других игроков: «оригинал TAB перевод на русский»
        """
        lines = raw.split("\n")
        own = lines[0] if lines else ""
        peer = lines[1] if len(lines) > 1 else ""
        self.own_text = self._format(own)
        self.peer_text = self._format(peer)
        if self.own_text or self.peer_text:
            self.until = time.time() + self.hold
        else:
            self.until = 0.0
        self._resize()

    @staticmethod
    def _format(line: str) -> str:
        """«текст TAB перевод» -> «текст\\n» перевод»."""
        ru, _, target = (line or "").partition("\t")
        ru = ru.strip().lstrip("\ufeff")
        target = target.strip().lstrip("\ufeff")
        parts = []
        if ru:
            parts.append(ru)
        if target:
            parts.append(f"» {target}")
        return "\n".join(parts)

    def _resize(self) -> None:
        """Подогнать размер окна под текст."""
        if not self.hwnd:
            return
        try:
            hdc = user32.GetDC(self.hwnd)
            font = self._font()
            old = gdi32.SelectObject(hdc, font)
            width = 0
            height = 0
            for text in (self.own_text, self.peer_text):
                if not text:
                    continue
                rect = wintypes.RECT(0, 0, 2000, 400)
                user32.DrawTextW(hdc, text, -1, ctypes.byref(rect),
                                 DT_LEFT | DT_TOP | DT_WORDBREAK | DT_CALCRECT)
                width = max(width, rect.right - rect.left)
                height += rect.bottom - rect.top + 8
            gdi32.SelectObject(hdc, old)
            user32.ReleaseDC(self.hwnd, hdc)
            w = max(120, width + 24)
            h = max(40, height + 16)
            if _DEBUG:
                log_error(f"resize: своя={self.own_text!r} чужая={self.peer_text!r} "
                          f"-> {w}x{h}")
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, self.x, self.y, w, h,
                                SWP_NOACTIVATE | SWP_SHOWWINDOW)
            user32.InvalidateRect(self.hwnd, None, True)
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        except Exception as exc:  # noqa: BLE001
            log_error(f"resize: {type(exc).__name__}: {exc}")

    # ---------- запуск ----------
    def run(self) -> None:
        proc = WNDPROC(self._wndproc)
        instance = kernel32.GetModuleHandleW(None)
        wndclass = WNDCLASS()
        wndclass.style = CS_HREDRAW | CS_VREDRAW
        wndclass.lpfnWndProc = proc
        wndclass.hInstance = instance
        wndclass.lpszClassName = self._class_name
        user32.RegisterClassW(ctypes.byref(wndclass))

        ex = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | \
            WS_EX_NOACTIVATE | WS_EX_TOPMOST
        self.hwnd = user32.CreateWindowExW(
            ex, self._class_name, "Auraloom Overlay", WS_POPUP,
            self.x, self.y, 420, 120, None, None, instance, None)
        if not self.hwnd:
            log_error(f"CreateWindowExW: ошибка {ctypes.get_last_error()}")
            return
        # цвет-ключ: этот цвет станет прозрачным
        user32.SetLayeredWindowAttributes(self.hwnd, BG_RGB, 0, LWA_COLORKEY)
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, self.x, self.y, 420, 120,
                            SWP_NOACTIVATE | SWP_SHOWWINDOW)
        user32.SetTimer(self.hwnd, 1, 120, None)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: overlay_win.py <файл_с_текстом>")
        return
    text_file = sys.argv[1]
    os.environ.setdefault("AURALOOM_OVERLAY_LOG",
                          os.path.join(os.path.dirname(os.path.abspath(text_file)),
                                       "overlay_err.log"))
    app = OverlayApp(
        text_file,
        x=int(os.environ.get("AURALOOM_OVERLAY_X", "60")),
        y=int(os.environ.get("AURALOOM_OVERLAY_Y", "60")),
        hold=float(os.environ.get("AURALOOM_OVERLAY_HOLD", "7")))
    app.run()


if __name__ == "__main__":
    main()
