"""Панель состояния Engine и аудиоустройств."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.ui.theme import ACCENT, BG, DIM, FG, GOOD, WARN, BAD, FONT_BODY, FONT_SMALL, SPACE_S, SPACE_M


class StatusPanel(tk.Frame):
    """Показывает состояние движка, аудиоустройств и задержку.

    Все обновления приходят через безопасную очередь событий (root.after),
    никакой прямой работы с аудио/моделями из GUI-потока.
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, bg=BG, **kwargs)
        self._build()
        self._engine_ready = False
        self._peer_active = False
        self._device_ok = False
        self._latency_ms = 0

    def _build(self):
        # Строка состояния движка
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", pady=(0, SPACE_S))

        self.lbl_engine = tk.Label(
            row, text="● Движок: не запущен",
            bg=BG, fg=BAD, font=FONT_BODY, anchor="w")
        self.lbl_engine.pack(side="left")

        # Индикатор задержки
        self.lbl_latency = tk.Label(
            row, text="задержка: —",
            bg=BG, fg=DIM, font=FONT_SMALL, anchor="e")
        self.lbl_latency.pack(side="right")

        # Аудиоустройства
        row2 = tk.Frame(self, bg=BG)
        row2.pack(fill="x", pady=(0, SPACE_S))

        self.lbl_device = tk.Label(
            row2, text="◌ Устройства: —",
            bg=BG, fg=DIM, font=FONT_BODY, anchor="w")
        self.lbl_device.pack(side="left")

        # Перехват речи игроков
        self.lbl_peer = tk.Label(
            row2, text="перехват: выкл",
            bg=BG, fg=DIM, font=FONT_SMALL, anchor="e")
        self.lbl_peer.pack(side="right")

    # ---------- публичные методы ----------

    def set_engine(self, ready: bool, loading: bool = False):
        """Состояние движка."""
        self._engine_ready = ready
        if loading:
            self.lbl_engine.config(text="● Движок: загрузка моделей…",
                                   fg=WARN)
        elif ready:
            self.lbl_engine.config(text="● Движок: готов",
                                   fg=GOOD)
        else:
            self.lbl_engine.config(text="● Движок: не запущен",
                                   fg=BAD)

    def set_devices(self, ok: bool, text: str | None = None):
        """Состояние аудиоустройств."""
        self._device_ok = ok
        color = GOOD if ok else (WARN if text else BAD)
        label = text or ("устройства OK" if ok else "устройства: не найдены")
        self.lbl_device.config(text=f"◌ {label}", fg=color)

    def set_peer(self, active: bool):
        """Состояние перехвата речи игроков."""
        self._peer_active = active
        self.lbl_peer.config(
            text="перехват: вкл" if active else "перехват: выкл",
            fg=GOOD if active else DIM)

    def set_latency(self, ms: int):
        """Текущая задержка перевода (мс)."""
        self._latency_ms = ms
        self.lbl_latency.config(text=f"задержка: {ms} мс")
