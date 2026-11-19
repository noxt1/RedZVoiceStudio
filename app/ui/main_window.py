"""Главное окно нового интерфейса RedZ Voice Studio по референсу.

Боковая навигация слева, главный контент справа.
Всё подключено к существующему аудиоконвейеру Studio / LiveTab.
"""

from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import ttk

from ui.home import HomePage
from ui.navigation import Navigation
from ui.settings import SettingsPage
from ui.sidebar import Sidebar
from ui.theme import (
    ACCENT, BAD, BG, BORDER_SUBTLE, GOOD, HOVER,
    INCOMING_ACCENT, OUTGOING_ACCENT, RADIUS_CARD, SPACE_L, SPACE_M, SPACE_S,
    SPACE_XL, SURFACE_1, SURFACE_HOVER, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, WARN, FONT_APP_TITLE, FONT_BODY, FONT_CARD_TITLE,
    FONT_H2, FONT_SECONDARY, FONT_METRIC,
)


def _diag(text: str) -> None:
    """Записать диагностику в файл (в EXE консоли нет)."""
    try:
        import studio_paths as sp
        logs = os.path.join(sp.workspace(), "logs")
        os.makedirs(logs, exist_ok=True)
        with open(os.path.join(logs, "ui_error.log"), "a",
                  encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {text}\n")
    except Exception:
        pass


class MainWindow:
    """Главное окно с боковой навигацией и тремя разделами."""

    def __init__(self, studio):
        self.studio = studio
        self.root = tk.Tk()
        self.root.title("RedZ Voice Studio")
        self.root.geometry("1400x900")
        self.root.minsize(1100, 700)
        self.root.configure(bg="#0B1118")

        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_columnconfigure(2, minsize=0)
        self.root.grid_rowconfigure(0, weight=1)

        self._current_page = None

        self._build_layout()
        self._bind_events()

        # Все разделы строятся заранее (на этапе заставки), чтобы при
        # переключении вкладок не было подгрузки и «белого кадра».
        self._build_home()
        self._build_voices()
        self._build_settings()

        self.nav.select("Главная")
        self._show_home()

        self.root.after(3000, self._refresh_engine)

    def _refresh_engine(self):
        try:
            status = self.studio.get_engine_status()
            self.update_engine_status(
                status["translator_ready"], status["translator_loading"])
        except Exception:
            pass
        self.root.after(3000, self._refresh_engine)

    def _build_layout(self):
        # Навигационная панель слева (фиксированная ширина)
        self.nav_frame = tk.Frame(self.root, bg="#101923", width=200)
        self.nav_frame.grid(row=0, column=0, sticky="ns")
        self.nav_frame.grid_propagate(False)

        self.nav = Navigation(
            self.nav_frame, on_select=self._on_section)
        self.nav.pack(fill="both", expand=True)

        # Контент справа — заполняет всё оставшееся пространство
        self.content = tk.Frame(self.root, bg="#0B1118")
        self.content.grid(row=0, column=1, sticky="nsew", padx=SPACE_L,
                          pady=SPACE_L)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        # Боковая панель истории (изначально скрыта) — колонка 2 в grid
        self.sidebar = Sidebar(self.root)
        self._sidebar_visible = False

        # Собираем разделы
        self._build_home()

    def _on_section(self, name: str):
        if name == "Главная":
            self._switch_lazy(self._show_home)
        elif name == "Голоса":
            self._switch_lazy(self._show_voices)
        elif name == "Настройки":
            self._switch_lazy(self._show_settings)
        elif name == "История и фразы":
            self.sidebar.toggle()
            self._sidebar_visible = self.sidebar._visible

    def _switch_lazy(self, show_fn):
        """Показать раздел.

        Все страницы построены заранее (на этапе заставки), поэтому
        переключение мгновенное — без подгрузки и «белого кадра».
        """
        self._hide_all_sections()
        try:
            show_fn()
        except Exception as exc:
            _diag(f"не удалось показать раздел: {exc}")

    def _hide_all_sections(self):
        for widget in self.content.winfo_children():
            widget.grid_forget()

    def _build_home(self):
        self.home = HomePage(self.content, self.studio)
        # Ссылка из Studio/LiveTab — чтобы переводы попадали в «Последние переводы»
        try:
            self.studio.home_page = self.home
        except Exception:
            pass

    def _show_home(self):
        self.home.grid(row=0, column=0, sticky="nsew")
        try:
            status = self.studio.get_engine_status()
            self.home.set_engine_status(
                status["translator_ready"], status["translator_loading"])
        except Exception:
            pass

    def _build_voices(self):
        from ui.voices import VoicesPage
        self.voices = VoicesPage(self.content, self.studio)
        self._voices_built = True

    def _show_voices(self):
        self.voices.grid(row=0, column=0, sticky="nsew")

    def _build_settings(self):
        self.settings = SettingsPage(self.content, self.studio)

    def _show_settings(self):
        self.settings.grid(row=0, column=0, sticky="nsew")
        # Устройства могли появиться после создания страницы — обновляем
        try:
            self.settings._refresh_devices()
            self.settings._refresh_engine()
        except Exception:
            pass

    def _bind_events(self):
        self.root.bind("<F12>", lambda e: self._toggle_sidebar())
        # Ловим исключения в callback'ах Tkinter: без этого падение
        # выглядит как «тихий краш» (в EXE консоли нет).
        self.root.report_callback_exception = self._on_callback_error

    def _on_callback_error(self, exc, val, tb):
        """Исключение в callback Tkinter — логируем, не роняем окно."""
        import traceback
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            logs = os.path.join(
                __import__("studio_paths").workspace(), "logs")
            os.makedirs(logs, exist_ok=True)
            with open(os.path.join(logs, "gui_crash.log"), "a",
                      encoding="utf-8") as fh:
                fh.write(f"\n===== Tk callback "
                         f"{time.strftime('%H:%M:%S')} =====\n{text}")
                fh.flush()
        except Exception:
            pass
        # Показываем в статус-баре, а не молча
        try:
            self.home.status_lbl.config(text=f"ошибка: {str(val)[:60]}", fg="#F07878")
        except Exception:
            pass

    def _toggle_sidebar(self):
        self.sidebar.toggle()
        self._sidebar_visible = self.sidebar._visible

    def update_engine_status(self, ready: bool, loading: bool = False):
        if self.home is not None:
            self.home.set_engine_status(ready, loading)

    def set_outgoing(self, enabled: bool):
        if self.home is not None:
            self.home.set_outgoing(enabled)

    def set_incoming(self, enabled: bool):
        if self.home is not None:
            self.home.set_incoming(enabled)

    def set_continuous(self, enabled: bool):
        if self.home is not None:
            self.home.set_continuous(enabled)

    def add_history(self, entry: str):
        if self.home is not None:
            self.home.add_history(entry)

    def run(self):
        self.root.mainloop()


# Отложенный импорт VoicesPage, чтобы избежать возможных циклических зависимостей
