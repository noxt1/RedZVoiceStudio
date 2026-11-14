"""Прототип главного окна с интерфейсом Liquid Glass.

Показывает новую навигацию (3 раздела) и визуальный стиль,
при этом все обработчики аудио/моделей/IPC остаются в существующем
voice_studio.py без изменений.

Этот прототип можно запустить независимо:
    python app/ui/proto_main.py
"""

from __future__ import annotations

import os
import sys

# Добавляем корень проекта в путь, чтобы импорты работали при запуске напрямую
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import tkinter as tk
from tkinter import ttk

from app.ui.glass_card import GlassCard
from app.ui.navigation import Navigation
from app.ui.status_panel import StatusPanel
from app.ui.sidebar import Sidebar
from app.ui.theme import (
    ACCENT, ACTIVE, BG, CARD_BG, CARD_BORDER, DIM, FG, GOOD, WARN, BAD,
    FONT_BODY, FONT_H2, FONT_SMALL, FONT_TITLE, RADIUS_L, SPACE_L, SPACE_M,
    SPACE_S, SPACE_XL, apply_window_theme,
)


class ProtoMainWindow:
    """Главное окно прототипа: 3 раздела + боковая панель истории."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("RedZ Voice Studio — прототип Liquid Glass")
        self.root.geometry("1280x800")
        self.root.minsize(1000, 600)

        # Mica / тёмная тема
        self._mica_ok = apply_window_theme(self.root)

        # Состояние (mock — в реальном приложении берётся из voice_studio)
        self._engine_ready = False
        self._engine_loading = False
        self._device_ok = False
        self._peer_active = False
        self._latency_ms = 0
        self._sidebar_visible = False

        self._build_layout()
        self._bind_events()

        # Имитация загрузки состояния
        self.root.after(500, self._simulate_status)

    # ---------- раскладка ----------

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

        # Собираем разделы
        self._build_home()
        self._build_voices()
        self._build_settings()

        # Показываем Главную
        self.nav.select("Главная")
        self._show_home()

    def _on_section(self, name: str):
        """Переключение раздела навигацией."""
        self._hide_all_sections()
        if name == "Главная":
            self._show_home()
        elif name == "Голоса":
            self._show_voices()
        elif name == "Настройки":
            self._show_settings()
        elif name == "Проверка голоса":
            self._show_voice_check()
        elif name == "Ресурс в игру":
            self._show_game_resource()

    def _hide_all_sections(self):
        for widget in self.content.winfo_children():
            widget.pack_forget()

    # ---------- Раздел: Главная ----------

    def _build_home(self):
        self.home = tk.Frame(self.content, bg=BG)

        # Заголовок раздела
        header = tk.Frame(self.home, bg=BG)
        header.pack(fill="x", pady=(0, SPACE_XL))
        tk.Label(
            header, text="Главная",
            bg=BG, fg=FG, font=FONT_TITLE, anchor="w").pack(side="left")
        tk.Label(
            header, text="RedZ Voice Studio",
            bg=BG, fg=DIM, font=FONT_SMALL, anchor="e").pack(side="right")

        # Статус-панель
        self.status_panel = StatusPanel(self.home)
        self.status_panel.pack(fill="x", pady=(0, SPACE_XL))

        # Две карточки: исходящий и входящий перевод
        cards_row = tk.Frame(self.home, bg=BG)
        cards_row.pack(fill="x", pady=(0, SPACE_L))

        self.card_out = self._make_direction_card(
            cards_row, "Исходящий", "RU → Español",
            "Говорите по-русски, в кабель уходит перевод вашим голосом.",
            accent=ACCENT)
        self.card_out.pack(side="left", fill="both", expand=True,
                           padx=(0, SPACE_M // 2))

        self.card_in = self._make_direction_card(
            cards_row, "Входящий", "AUTO → RU",
            "Речь других игроков переводится на русский в наушники.",
            accent=GOOD)
        self.card_in.pack(side="left", fill="both", expand=True,
                          padx=(SPACE_M // 2, 0))

        # Голосовой профиль и громкость
        mid = tk.Frame(self.home, bg=BG)
        mid.pack(fill="x", pady=(0, SPACE_L))

        self.card_voice = self._make_voice_card(mid)
        self.card_voice.pack(side="left", fill="both", expand=True,
                             padx=(0, SPACE_M // 2))

        self.card_vol = self._make_volume_card(mid)
        self.card_vol.pack(side="left", fill="both", expand=True,
                           padx=(SPACE_M // 2, 0))

        # PTT и непрерывный режим
        self.card_ptt = self._make_ptt_card(self.home)
        self.card_ptt.pack(fill="x", pady=(0, SPACE_L))

    def _make_direction_card(self, parent, title: str, subtitle: str,
                             description: str, accent) -> GlassCard:
        card = GlassCard(parent, radius=RADIUS_L, pad=SPACE_M)
        inner = card.inner

        tk.Label(inner, text=title, bg=CARD_BG, fg=FG,
                 font=FONT_H2, anchor="w").pack(anchor="w", pady=(0, 2))
        tk.Label(inner, text=subtitle, bg=CARD_BG, fg=accent,
                 font=FONT_SMALL, anchor="w").pack(anchor="w", pady=(0, 6))
        tk.Label(inner, text=description, bg=CARD_BG, fg=DIM,
                 font=FONT_BODY, anchor="w", justify="left",
                 wraplength=380).pack(anchor="w", pady=(0, 10))

        # Статус направления
        status = tk.Label(inner, text="◌ выключено",
                          bg=CARD_BG, fg=DIM, font=FONT_SMALL, anchor="w")
        status.pack(anchor="w")
        card._status_label = status

        # Кнопка включения
        btn = tk.Button(
            inner, text="Включить",
            bg=accent, fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=16, pady=6)
        btn.pack(anchor="w", pady=(8, 0))
        btn.bind("<Enter>", lambda e: btn.configure(bg=ACTIVE))
        btn.bind("<Leave>", lambda e: btn.configure(bg=accent))
        card._enable_btn = btn

        return card

    def _make_voice_card(self, parent) -> GlassCard:
        card = GlassCard(parent, radius=RADIUS_L, pad=SPACE_M)
        inner = card.inner

        tk.Label(inner, text="Голосовой профиль",
                 bg=CARD_BG, fg=FG, font=FONT_H2, anchor="w").pack(
                     anchor="w", pady=(0, 6))

        row = tk.Frame(inner, bg=CARD_BG)
        row.pack(fill="x", pady=(0, 6))
        tk.Label(row, text="Профиль:", bg=CARD_BG, fg=DIM,
                 font=FONT_SMALL).pack(side="left")
        combo = ttk.Combobox(row, state="readonly", width=24,
                             values=["Профиль 1 (мой голос)", "Профиль 2"])
        combo.current(0)
        combo.pack(side="left", padx=(SPACE_S, 0))

        btn = tk.Button(
            inner, text="🔊 Прослушать профиль",
            bg=ACCENT, fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=16, pady=6)
        btn.pack(anchor="w", pady=(4, 4))
        btn.bind("<Enter>", lambda e: btn.configure(bg=ACTIVE))
        btn.bind("<Leave>", lambda e: btn.configure(bg=ACCENT))

        btn2 = tk.Button(
            inner, text="+ Создать профиль",
            bg=CARD_BORDER, fg=FG, activeforeground=FG,
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=16, pady=6)
        btn2.pack(anchor="w")
        btn2.bind("<Enter>", lambda e: btn2.configure(bg=ACTIVE))
        btn2.bind("<Leave>", lambda e: btn2.configure(bg=CARD_BORDER))

        return card

    def _make_volume_card(self, parent) -> GlassCard:
        card = GlassCard(parent, radius=RADIUS_L, pad=SPACE_M)
        inner = card.inner

        tk.Label(inner, text="Громкость",
                 bg=CARD_BG, fg=FG, font=FONT_H2, anchor="w").pack(
                     anchor="w", pady=(0, 6))

        # Оригинал
        row1 = tk.Frame(inner, bg=CARD_BG)
        row1.pack(fill="x", pady=(0, 8))
        tk.Label(row1, text="Оригинал", bg=CARD_BG, fg=DIM,
                 font=FONT_SMALL).pack(side="left")
        tk.Label(row1, text="70%", bg=CARD_BG, fg=FG,
                 font=FONT_SMALL).pack(side="right")
        scale1 = tk.Scale(
            row1, from_=0, to=100, orient="horizontal",
            bg=CARD_BG, fg=FG, troughcolor="#1e2632",
            highlightthickness=0, length=200, showvalue=False)
        scale1.set(70)
        scale1.pack(side="right", padx=(SPACE_S, 0), fill="x", expand=True)

        # Перевод
        row2 = tk.Frame(inner, bg=CARD_BG)
        row2.pack(fill="x")
        tk.Label(row2, text="Перевод", bg=CARD_BG, fg=DIM,
                 font=FONT_SMALL).pack(side="left")
        tk.Label(row2, text="80%", bg=CARD_BG, fg=FG,
                 font=FONT_SMALL).pack(side="right")
        scale2 = tk.Scale(
            row2, from_=0, to=150, orient="horizontal",
            bg=CARD_BG, fg=FG, troughcolor="#1e2632",
            highlightthickness=0, length=200, showvalue=False)
        scale2.set(80)
        scale2.pack(side="right", padx=(SPACE_S, 0), fill="x", expand=True)

        return card

    def _make_ptt_card(self, parent) -> GlassCard:
        card = GlassCard(parent, radius=RADIUS_L, pad=SPACE_M)
        inner = card.inner

        tk.Label(inner, text="Режим работы",
                 bg=CARD_BG, fg=FG, font=FONT_H2, anchor="w").pack(
                     anchor="w", pady=(0, 8))

        # Kнопка PTT
        self.btn_ptt = tk.Button(
            inner, text="🎤 ЗАЖАТЬ И ГОВОРИТЬ",
            bg="#1e6f3f", fg="#fff", activebackground="#154a2c",
            activeforeground="#fff", font=("Segoe UI Variable", 12, "bold"),
            relief="flat", cursor="hand2", padx=24, pady=14)
        self.btn_ptt.pack(fill="x", pady=(0, 6))
        self.btn_ptt.bind("<ButtonPress-1>", self._ptt_press)
        self.btn_ptt.bind("<ButtonRelease-1>", self._ptt_release)

        # Непрерывный режим
        row = tk.Frame(inner, bg=CARD_BG)
        row.pack(fill="x")
        self.btn_cont = tk.Button(
            row, text="🔴 Непрерывно: выкл",
            bg=CARD_BORDER, fg=FG, activeforeground=FG,
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=16, pady=8)
        self.btn_cont.pack(side="left", padx=(0, 8))
        self.btn_cont.bind("<Button-1>", lambda e: self._toggle_cont())

        return card

    def _ptt_press(self, event):
        self.btn_ptt.configure(text="🎤 ГОВОРИ… (отпусти)", bg="#8a2f2f")
        self.status_panel.set_engine(True)
        self.card_out._status_label.config(text="● активен", fg=GOOD)
        self.card_out._enable_btn.config(text="Выключить", bg=BAD)

    def _ptt_release(self, event):
        self.btn_ptt.configure(text="🎤 ЗАЖАТЬ И ГОВОРИТЬ", bg="#1e6f3f")
        self.card_out._status_label.config(text="◌ выключено", fg=DIM)
        self.card_out._enable_btn.config(text="Включить", bg=ACCENT)

    def _toggle_cont(self):
        if self.btn_cont.cget("text").endswith("выкл"):
            self.btn_cont.configure(text="🔴 Непрерывно: ВКЛ", bg="#8a2f2f")
            self.card_in._status_label.config(text="● слушает", fg=GOOD)
            self.card_in._enable_btn.config(text="Выключить", bg=BAD)
        else:
            self.btn_cont.configure(text="🔴 Непрерывно: выкл", bg=CARD_BORDER)
            self.card_in._status_label.config(text="◌ выключено", fg=DIM)
            self.card_in._enable_btn.config(text="Включить", bg=ACCENT)

    # ---------- Раздел: Голоса ----------

    def _build_voices(self):
        self.voices = tk.Frame(self.content, bg=BG)

        header = tk.Frame(self.voices, bg=BG)
        header.pack(fill="x", pady=(0, SPACE_XL))
        tk.Label(
            header, text="Голоса",
            bg=BG, fg=FG, font=FONT_TITLE, anchor="w").pack(side="left")

        # Карточки профилей
        row = tk.Frame(self.voices, bg=BG)
        row.pack(fill="x", pady=(0, SPACE_L))

        for i, name in enumerate(["Профиль 1", "Профиль 2", "Профиль 3"]):
            card = self._make_voice_profile_card(row, name, active=(i == 0))
            card.pack(side="left", fill="both", expand=True,
                      padx=(0 if i == 0 else SPACE_M // 2,
                           SPACE_M // 2 if i == 2 else 0))

        # Создание нового профиля
        card_new = GlassCard(self.voices, radius=RADIUS_L, pad=SPACE_M)
        inner = card_new.inner
        tk.Label(inner, text="+ Создать новый профиль",
                 bg=CARD_BG, fg=ACCENT, font=FONT_H2, anchor="w").pack(
                     anchor="w", pady=(0, 6))
        tk.Label(inner, text="Запишите 5–8 подсказок — XTTS клонирует ваш голос.",
                 bg=CARD_BG, fg=DIM, font=FONT_BODY, anchor="w").pack(
                     anchor="w", pady=(0, 10))
        btn = tk.Button(
            inner, text="Начать запись",
            bg=ACCENT, fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=16, pady=8)
        btn.pack(anchor="w")
        btn.bind("<Enter>", lambda e: btn.configure(bg=ACTIVE))
        btn.bind("<Leave>", lambda e: btn.configure(bg=ACCENT))
        card_new.pack(fill="x", pady=(SPACE_L, 0))

    def _make_voice_profile_card(self, parent, name: str, active: bool) -> GlassCard:
        card = GlassCard(parent, radius=RADIUS_L, pad=SPACE_M)
        inner = card.inner

        if active:
            card.set_focus(True)

        tk.Label(inner, text=name,
                 bg=CARD_BG, fg=ACCENT if active else FG,
                 font=FONT_H2, anchor="w").pack(anchor="w", pady=(0, 4))

        tk.Label(inner, text="XTTS · клонирован",
                 bg=CARD_BG, fg=DIM, font=FONT_SMALL, anchor="w").pack(
                     anchor="w", pady=(0, 8))

        btn_play = tk.Button(
            inner, text="▶ Прослушать",
            bg=CARD_BORDER, fg=FG, activeforeground=FG,
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=14, pady=5)
        btn_play.pack(side="left", padx=(0, SPACE_S))
        btn_play.bind("<Enter>", lambda e: btn_play.configure(bg=ACTIVE))
        btn_play.bind("<Leave>", lambda e: btn_play.configure(bg=CARD_BORDER))

        btn_test = tk.Button(
            inner, text="Тест",
            bg=CARD_BORDER, fg=FG, activeforeground=FG,
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=14, pady=5)
        btn_test.pack(side="left")
        btn_test.bind("<Enter>", lambda e: btn_test.configure(bg=ACTIVE))
        btn_test.bind("<Leave>", lambda e: btn_test.configure(bg=CARD_BORDER))

        return card

    # ---------- Раздел: Настройки ----------

    def _build_settings(self):
        self.settings = tk.Frame(self.content, bg=BG)

        header = tk.Frame(self.settings, bg=BG)
        header.pack(fill="x", pady=(0, SPACE_XL))
        tk.Label(
            header, text="Настройки",
            bg=BG, fg=FG, font=FONT_TITLE, anchor="w").pack(side="left")

        # Категории настроек в карточках
        cats = [
            ("Аудиоустройства", "Выбор микрофона и выхода, мост, диагностика", ACCENT),
            ("Языки", "RU → ES/EN/OW/IT, язык чужой речи, уверенность", GOOD),
            ("Горячие клавиши", "PTT, непрерывный режим, фразы звуковой панели", WARN),
            ("Модели и производительность", "ASR, MT, TTS, кэш, VRAM", BAD),
        ]

        for title, desc, accent in cats:
            card = GlassCard(self.settings, radius=RADIUS_L, pad=SPACE_M)
            inner = card.inner
            tk.Label(inner, text=title, bg=CARD_BG, fg=FG,
                     font=FONT_H2, anchor="w").pack(anchor="w", pady=(0, 2))
            tk.Label(inner, text=desc, bg=CARD_BG, fg=DIM,
                     font=FONT_BODY, anchor="w", justify="left",
                     wraplength=500).pack(anchor="w", pady=(0, 8))
            btn = tk.Button(
                inner, text="Открыть",
                bg=accent, fg="#fff", activeforeground="#fff",
                activebackground=ACTIVE, font=FONT_BODY,
                relief="flat", cursor="hand2", padx=14, pady=5)
            btn.pack(anchor="w")
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=ACTIVE))
            btn.bind("<Leave>", lambda e, b=btn, a=accent: b.configure(bg=a))
            card.pack(fill="x", pady=SPACE_M)

    # ---------- Дополнительные инструменты ----------

    def _show_voice_check(self):
        self._hide_all_sections()
        frame = tk.Frame(self.content, bg=BG)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Проверка голоса", bg=BG, fg=FG,
                 font=FONT_TITLE).pack(anchor="w", pady=(0, SPACE_L))
        tk.Label(frame, text="Разборчивость · схожесть голоса · правила проекта",
                 bg=BG, fg=DIM, font=FONT_BODY).pack(anchor="w")

    def _show_game_resource(self):
        self._hide_all_sections()
        frame = tk.Frame(self.content, bg=BG)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Ресурс в игру", bg=BG, fg=FG,
                 font=FONT_TITLE).pack(anchor="w", pady=(0, SPACE_L))
        tk.Label(frame, text="Пути установки для RedM/FiveM и внешнего плеера",
                 bg=BG, fg=DIM, font=FONT_BODY).pack(anchor="w")

    # ---------- показ/скрытие разделов ----------

    def _show_home(self):
        self.home.pack(fill="both", expand=True)

    def _show_voices(self):
        self.voices.pack(fill="both", expand=True)

    def _show_settings(self):
        self.settings.pack(fill="both", expand=True)

    # ---------- события ----------

    def _bind_events(self):
        # Клик по панели статуса — показать/скрыть боковую панель
        self.root.bind("<F12>", lambda e: self._toggle_sidebar())

    def _toggle_sidebar(self):
        self.sidebar.toggle()
        self._sidebar_visible = self.sidebar._visible

    # ---------- симуляция состояния (для демо) ----------

    def _simulate_status(self):
        self.status_panel.set_engine(True, loading=True)
        self.root.after(1500, lambda: self.status_panel.set_engine(True))
        self.root.after(1600, lambda: self.status_panel.set_devices(
            True, "устройства OK"))
        self.root.after(1700, lambda: self.status_panel.set_peer(False))
        self.root.after(1800, lambda: self.status_panel.set_latency(520))

    def run(self):
        self.root.mainloop()


def main():
    app = ProtoMainWindow()
    app.run()


if __name__ == "__main__":
    main()
