"""Главное окно нового интерфейса RedZ Voice Studio.

Три раздела: Главная / Голоса / Настройки.
Боковая панель истории — выдвижная.
Все функции подключены к существующему аудиоконвейеру (не переписывается).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui.glass_card import GlassCard
from ui.home import HomePage
from ui.navigation import Navigation
from ui.settings import SettingsPage
from ui.sidebar import Sidebar
from ui.theme import (
    BAD, BG, BORDER_FOCUS, BORDER_SUBTLE, GOOD, HOVER,
    INCOMING_ACCENT, OUTGOING_ACCENT, RADIUS_CARD, SPACE_L, SPACE_M, SPACE_S,
    SPACE_XL, SURFACE_1, SURFACE_HOVER, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, WARN, FONT_APP_TITLE, FONT_BODY, FONT_CARD_TITLE,
    FONT_H2, FONT_SECONDARY, FONT_METRIC,
)
from ui.theme import apply_window_theme


class MainWindow:
    """Главное окно с тремя разделами и боковой панелью истории."""

    def __init__(self, studio):
        self.studio = studio
        self.root = tk.Tk()
        self.root.title("RedZ Voice Studio")
        self.root.geometry("1280x800")
        self.root.minsize(980, 680)

        # Mica / тёмная тема
        self._mica_ok = apply_window_theme(self.root)

        # Состояние
        self._current_page = None

        self._build_layout()
        self._bind_events()

        # Показываем Главную
        self.nav.select("Главная")
        self._show_home()

        # Периодическое обновление статуса движка (каждые 3 с)
        self.root.after(3000, self._refresh_engine)

    def _refresh_engine(self):
        """Периодически обновлять статус движка на главной странице."""
        status = self.studio.get_engine_status()
        self.update_engine_status(
            status["translator_ready"], status["translator_loading"])
        self.root.after(3000, self._refresh_engine)

    # ---------- построение ----------

    def _build_layout(self):
        # Контейнер: навигация слева, контент справа
        self.container = tk.Frame(self.root, bg=BG)
        self.container.pack(fill="both", expand=True)

        # Контент (создаём первым, чтобы навигация могла на него сослаться)
        self.content = tk.Frame(self.container, bg=BG)
        self.content.pack(side="left", fill="both", expand=True, padx=SPACE_L,
                          pady=SPACE_L)

        # Навигация
        self.nav = Navigation(
            self.container, on_select=self._on_section)
        self.nav.pack(side="left", fill="y")

        # Боковая панель истории (изначально скрыта)
        self.sidebar = Sidebar(self.root)
        self._sidebar_visible = False

        # Собираем разделы
        self._build_home()
        self._build_voices()
        self._build_settings()

    def _on_section(self, name: str):
        """Переключение раздела навигацией."""
        self._hide_all_sections()
        if name == "Главная":
            self._show_home()
        elif name == "Голоса":
            self._show_voices()
        elif name == "Настройки":
            self._show_settings()
        elif name == "История и фразы":
            self.sidebar.toggle()
            self._sidebar_visible = self.sidebar._visible

    def _hide_all_sections(self):
        for widget in self.content.winfo_children():
            widget.pack_forget()

    # ---------- Раздел: Главная ----------

    def _build_home(self):
        self.home = HomePage(self.content, self.studio)

    def _show_home(self):
        self.home.pack(fill="both", expand=True)
        # Обновить статус движка через Studio
        status = self.studio.get_engine_status()
        self.home.set_engine_status(
            status["translator_ready"], status["translator_loading"])

    # ---------- Раздел: Голоса ----------

    def _build_voices(self):
        self.voices = VoicesPage(self.content, self.studio)

    def _show_voices(self):
        self.voices.pack(fill="both", expand=True)

    # ---------- Раздел: Настройки ----------

    def _build_settings(self):
        self.settings = SettingsPage(self.content, self.studio)

    def _show_settings(self):
        self.settings.pack(fill="both", expand=True)

    # ---------- события ----------

    def _bind_events(self):
        # F12 — показать/скрыть боковую панель
        self.root.bind("<F12>", lambda e: self._toggle_sidebar())

    def _toggle_sidebar(self):
        self.sidebar.toggle()
        self._sidebar_visible = self.sidebar._visible

    # ---------- публичное API ----------

    def update_engine_status(self, ready: bool, loading: bool = False):
        """Обновить статус движка на главной странице."""
        if self.home is not None:
            self.home.set_engine_status(ready, loading)

    def set_outgoing(self, enabled: bool):
        """Включить/выключить исходящий перевод на главной."""
        if self.home is not None:
            self.home.set_outgoing(enabled)

    def set_incoming(self, enabled: bool):
        """Включить/выключить входящий перевод на главной."""
        if self.home is not None:
            self.home.set_incoming(enabled)

    def set_continuous(self, enabled: bool):
        """Включить/выключить непрерывный режим на главной."""
        if self.home is not None:
            self.home.set_continuous(enabled)

    def run(self):
        self.root.mainloop()


# Отложенный импорт VoicesPage, чтобы избежать возможных циклических зависимостей
from ui.voices import VoicesPage  # noqa: E402
