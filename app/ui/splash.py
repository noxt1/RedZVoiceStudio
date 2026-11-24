"""Экран загрузки RedZ Voice Studio.

Показывается на время инициализации: пока строятся страницы, опрашиваются
устройства и поднимается LiveTab, пользователь видит окно с прогрессом
вместо белого экрана.

Использование:
    splash = SplashScreen()
    splash.step("Загрузка интерфейса…", 20)
    ...
    splash.close()
"""

from __future__ import annotations

import tkinter as tk

from ui.theme import (
    ACCENT, BG, GOOD, SURFACE_1, SURFACE_2, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, FONT_APP_TITLE, FONT_BODY, FONT_SECONDARY,
)


class SplashScreen:
    """Полноэкранная заставка с прогрессом 0–100%."""

    def __init__(self, title: str = "RedZ Voice Studio") -> None:
        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg=BG)
        self.root.overrideredirect(True)      # без рамки
        self.root.attributes("-topmost", True)

        w, h = 460, 260
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2 - 40
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # --- логотип ---
        logo = tk.Label(self.root, text="RedZ", bg=BG, fg=ACCENT,
                        font=("Segoe UI Variable Display", 30, "bold"))
        logo.pack(pady=(38, 0))

        tk.Label(self.root, text="VOICE STUDIO", bg=BG, fg=TEXT_MUTED,
                 font=("Segoe UI Variable Text", 9, "bold")).pack(pady=(0, 24))

        # --- подпись этапа ---
        self.status = tk.Label(self.root, text="Запуск…", bg=BG,
                               fg=TEXT_SECONDARY, font=FONT_SECONDARY)
        self.status.pack(pady=(0, 10))

        # --- полоса прогресса ---
        self.bar_bg = tk.Frame(self.root, bg=SURFACE_2, height=6, width=380)
        self.bar_bg.pack(pady=(0, 6))
        self.bar_bg.pack_propagate(False)
        self.bar_fill = tk.Frame(self.bar_bg, bg=ACCENT, width=0, height=6)
        self.bar_fill.pack(side="left")

        # --- проценты ---
        self.pct = tk.Label(self.root, text="0%", bg=BG, fg=TEXT_MUTED,
                            font=FONT_SECONDARY)
        self.pct.pack()

        self._value = 0.0
        self.root.update()

    # ------------------------------------------------------------------
    def step(self, text: str, percent: float) -> None:
        """Обновить этап и прогресс (0–100)."""
        try:
            self.status.config(text=text)
            p = max(0.0, min(100.0, float(percent)))
            self._value = p
            self.bar_fill.config(width=int(380 * p / 100.0))
            self.pct.config(text=f"{int(p)}%")
            self.root.update()
        except Exception:
            pass

    def pulse(self, text: str) -> None:
        """Обновить только текст (без процентов)."""
        try:
            self.status.config(text=text)
            self.root.update()
        except Exception:
            pass

    def close(self) -> None:
        """Закрыть заставку."""
        try:
            self.root.destroy()
        except Exception:
            pass