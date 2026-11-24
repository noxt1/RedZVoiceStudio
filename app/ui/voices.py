"""Страница «Голоса» — три под-вкладки вместо перегруженной одной.

    1. «🎯 Мой голос за 3 минуты» — запись голоса пошагово:
       крупная читаемая фраза + готовый звуковой образец интонации,
       после записи — проверка качества («ок») и сравнение с образцом.
    2. «💬 Подсказки» — все подсказки отдельно: почитать и послушать.
    3. «📁 Образцы» — получившиеся записи и собранный образец голоса:
       прослушать, сравнить с подсказкой (одновременно или с задержкой),
       удалить лишнее.

Звуковые подсказки — готовые референсы, записанные заранее и включённые
в поставку (voices/prompts). Ничего не синтезируется во время работы и
пользователю не нужно ничего записывать, чтобы услышать образец.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import tkinter as tk
from tkinter import ttk

import numpy as np
import soundfile as sf

import prompt_library as plib
import studio_core as core
import studio_paths as sp
from ui.audio_play import compare as play_compare
from ui.audio_play import play_array, play_file
import ui.audio_play as ap
from ui.dark_table import DarkTable
from ui.glass_card import GlassCard
from ui.theme import (
    ACCENT, ACTIVE, BAD, BG, BORDER_SUBTLE, FONT_APP_TITLE, FONT_BODY,
    FONT_CARD_TITLE, FONT_H2, FONT_METRIC, FONT_MONO, FONT_SECONDARY, GOOD,
    HOVER, RADIUS_CARD, SPACE_L, SPACE_M, SPACE_S, SPACE_XL, SPACE_XS,
    SURFACE_1, SURFACE_2, SURFACE_HOVER, SURFACE_PRESSED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, WARN,
)

GREEN = "#1e6f3f"

TABS = (
    ("quick", "🎯  Мой голос за 3 минуты"),
    ("prompts", "💬  Подсказки"),
    ("samples", "📁  Образцы"),
)

# Эмоции → человекочитаемая подпись (совпадает с voice_prompts)
_EMO_FILTERS = (
    ("all", "Все"),
    ("friendly", "Тепло"),
    ("angry", "Возмущённо"),
    ("energetic", "Энергично"),
    ("neutral", "Спокойно"),
)

_TAKE_RE = re.compile(r"^p(\d+)_take_(\d{6})\.wav$")


class VoicesPage(tk.Frame):
    """Страница управления голосом: запись, подсказки, образцы."""

    def __init__(self, master, studio, **kwargs):
        super().__init__(master, bg=BG, **kwargs)
        self.studio = studio

        # Состояние сценария записи
        self._quick_active = False
        self._quick_index = 0
        self._phase = "idle"          # idle / playing / recording / review
        self._last_take: str | None = None
        self._rec_started = 0.0
        self._rec_limit = 5.0
        self._play_token = 0          # для отмены запланированных воспроизведений
        self._tab = "quick"

        # Общие настройки
        self._compare_mode = tk.StringVar(value="together")
        self._prompt_filter = tk.StringVar(value="all")
        self._selected_prompt = 0
        self._selected_take: str | None = None

        self._build()
        self._refresh()

    # ==================================================================
    # Построение
    # ==================================================================
    def _build(self):
        # Внутри одного родителя нельзя мешать pack и grid, поэтому
        # верхняя часть (шапка + переключатель) и рабочая область —
        # разные контейнеры.
        self._style_trees()
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # --- Заголовок ---
        header = tk.Frame(body, bg=BG)
        header.pack(fill="x", pady=(0, SPACE_M))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header, text="Голоса", bg=BG, fg=TEXT_PRIMARY,
            font=FONT_APP_TITLE, anchor="w").pack(side="left")
        tk.Label(
            header, text="запись  •  подсказки  •  образцы", bg=BG,
            fg=TEXT_MUTED, font=FONT_SECONDARY, anchor="e").pack(side="right")

        # --- Переключатель под-вкладок ---
        self._tab_bar = tk.Frame(body, bg=SURFACE_1, highlightthickness=0, bd=0)
        self._tab_bar.pack(fill="x", pady=(0, SPACE_L))
        self._tab_buttons: dict[str, tk.Button] = {}
        for key, title in TABS:
            btn = tk.Button(
                self._tab_bar, text=title, bg=SURFACE_1, fg=TEXT_MUTED,
                activebackground=SURFACE_HOVER, activeforeground=TEXT_PRIMARY,
                font=FONT_BODY, relief="flat", anchor="w", cursor="hand2",
                padx=SPACE_M, pady=SPACE_S, highlightthickness=0, bd=0,
                command=lambda k=key: self._select_tab(k))
            btn.pack(side="left")
            self._tab_buttons[key] = btn

        # --- Рабочая область под-вкладок ---
        # Каждая под-вкладка — прокручиваемая: на длинных списках
        # (подсказки, образцы) содержимое уезжает за нижний край окна,
        # и без прокрутки до него не добраться.
        from scrollframe import ScrollFrame
        self._tabs_host = tk.Frame(body, bg=BG)
        self._tabs_host.pack(fill="both", expand=True)
        self._tabs_host.grid_columnconfigure(0, weight=1)
        self._tabs_host.grid_rowconfigure(0, weight=1)

        self.tab_quick = ScrollFrame(self._tabs_host, bg=BG)
        self.tab_prompts = ScrollFrame(self._tabs_host, bg=BG)
        self.tab_samples = ScrollFrame(self._tabs_host, bg=BG)

        self._build_quick(self.tab_quick.body)
        self._build_prompts(self.tab_prompts.body)
        self._build_samples(self.tab_samples.body)

        self._select_tab("quick")

        # опрос прогресса клонирования (Studio кладёт строки в log_queue)
        self._clone_was_running = False
        self.after(500, self._clone_progress_tick)
        # обновление кнопок «играть/стоп» (плеер работает в потоке)
        self.after(250, self._play_button_tick)

    def _play_button_tick(self):
        """Синхронизировать кнопки с состоянием плеера."""
        try:
            self._sync_play_buttons()
        except Exception:
            pass
        self.after(250, self._play_button_tick)

    # ---------- общие мелкие виджеты ----------

    def _btn(self, parent, text, command, bg=SURFACE_2, fg=TEXT_PRIMARY,
             padx=14, pady=7, font=None, state="normal"):
        btn = tk.Button(
            parent, text=text, bg=bg, fg=fg, activeforeground=fg,
            activebackground=SURFACE_PRESSED, font=font or FONT_BODY,
            relief="flat", cursor="hand2", padx=padx, pady=pady,
            highlightthickness=0, bd=0, state=state, command=command)
        btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=SURFACE_HOVER))
        btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=bg))
        return btn

    def _style_trees(self):
        """Устарело: таблицы теперь на своём виджете DarkTable."""
        return

    def _display_name(self) -> str:
        return (getattr(self.studio, "name", "") or "Cyril").strip() or "Cyril"

    def _prompt_text_ru(self, item: dict) -> str:
        """Русский текст подсказки с именем пользователя."""
        return (item.get("ru") or "").replace("{name}", self._display_name())

    def _select_tab(self, key: str):
        self._tab = key
        for k, btn in self._tab_buttons.items():
            active = (k == key)
            btn.configure(bg=SURFACE_2 if active else SURFACE_1,
                          fg=TEXT_PRIMARY if active else TEXT_MUTED)
        for frame in (self.tab_quick, self.tab_prompts, self.tab_samples):
            frame.grid_forget()
        frame = {"quick": self.tab_quick, "prompts": self.tab_prompts,
                 "samples": self.tab_samples}[key]
        frame.grid(row=0, column=0, sticky="nsew")
        # Обновляем только видимые элементы: Canvas перерисовывает
        # содержимое, но не пересоздаёт его (иначе «прогрузка плиток»).
        try:
            frame.canvas.update_idletasks()
            frame.body.update_idletasks()
        except Exception:
            pass
        # если это «Образцы» — обновляем таблицу (данные могли измениться)
        if key == "samples":
            try:
                self._refresh_samples()
            except Exception:
                pass

    # ==================================================================
    # Под-вкладка 1. «Мой голос за 3 минуты»
    # ==================================================================
    def _build_quick(self, parent):
        card = GlassCard(parent, radius=RADIUS_CARD, pad=SPACE_M)
        card.pack(fill="x", pady=(0, 0))
        inner = card.inner
        inner.grid_columnconfigure(0, weight=1)

        tk.Label(
            inner, text="🎯  Мой голос за 3 минуты", bg=SURFACE_1,
            fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(0, SPACE_S))

        tk.Label(
            inner,
            text="18 коротких фраз. Приложение показывает фразу, проигрывает "
                 "готовый образец интонации и записывает тебя. После каждой "
                 "фразы — пауза: можно переделать или сравнить с образцом.",
            bg=SURFACE_1, fg=TEXT_SECONDARY, font=FONT_BODY,
            anchor="w", justify="left", wraplength=700).pack(
                anchor="w", pady=(0, SPACE_M))

        # --- Профиль клона ---
        #
        # Выбор профиля живёт на главной (в карточке исходящего перевода),
        # чтобы не дублировать. Здесь только показываем, куда пойдут записи.
        self.quick_profile_hint = tk.Label(
            inner, text="", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w", justify="left",
            wraplength=700)
        self.quick_profile_hint.pack(anchor="w", pady=(0, SPACE_S))

        # --- Кнопки запуска ---
        self.btn_start = self._btn(
            inner, "▶  Начать запись", self._quick_start, bg=GREEN, fg="#fff",
            padx=20, pady=11, font=("Segoe UI Variable", 11, "bold"))
        self.btn_start.pack(anchor="w", pady=(0, SPACE_M))

        # --- Прогресс ---
        prog_row = tk.Frame(inner, bg=SURFACE_1)
        prog_row.pack(fill="x", pady=(0, SPACE_S))

        self.quick_step = tk.Label(
            prog_row, text="Фраза 1 из 18", bg=SURFACE_1, fg=ACCENT,
            font=FONT_SECONDARY, anchor="w")
        self.quick_step.pack(side="left")

        self.quick_timer = tk.Label(
            prog_row, text="", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="e")
        self.quick_timer.pack(side="right")

        self.progress = tk.Canvas(inner, height=6, bg=SURFACE_2,
                                  highlightthickness=0, bd=0)
        self.progress.pack(fill="x", pady=(0, SPACE_M))
        self.progress.bind("<Configure>", lambda e: self._draw_progress())
        self._progress_value = 0.0

        # --- Крупная читаемая фраза ---
        phrase_box = tk.Frame(inner, bg=SURFACE_2, highlightthickness=0, bd=0)
        phrase_box.pack(fill="x", pady=(0, SPACE_S))
        self.phrase_box = phrase_box

        self.prompt_text = tk.Label(
            phrase_box, text="Нажми «Начать запись» — здесь появится фраза",
            bg=SURFACE_2, fg=TEXT_PRIMARY,
            font=("Segoe UI Variable", 19, "bold"), anchor="w",
            justify="left", wraplength=620, padx=SPACE_M, pady=SPACE_M)
        self.prompt_text.pack(fill="x")

        self.prompt_emo = tk.Label(
            inner, text="", bg=SURFACE_1, fg=ACCENT, font=FONT_SECONDARY,
            anchor="w")
        self.prompt_emo.pack(anchor="w", pady=(0, SPACE_M))

        # --- Звуковая подсказка ---
        audio_row = tk.Frame(inner, bg=SURFACE_1)
        audio_row.pack(fill="x", pady=(0, SPACE_S))

        self.btn_play_prompt = self._btn(
            audio_row, "🔊  Образец интонации", self._play_current_prompt,
            bg=SURFACE_2, fg=TEXT_PRIMARY, padx=14, pady=8)
        self.btn_play_prompt.pack(side="left", padx=(0, SPACE_S))

        self.btn_redo = self._btn(
            audio_row, "🎙  Перезаписать", self._redo_take,
            bg=SURFACE_2, fg=TEXT_PRIMARY, padx=14, pady=8, state="disabled")
        self.btn_redo.pack(side="left", padx=(0, SPACE_S))

        self.btn_next = self._btn(
            audio_row, "▶  Дальше", self._quick_advance, bg=GREEN, fg="#fff",
            padx=18, pady=8, state="disabled")
        self.btn_next.pack(side="left")

        # --- Уровень микрофона ---
        meter_row = tk.Frame(inner, bg=SURFACE_1)
        meter_row.pack(fill="x", pady=(SPACE_XS, SPACE_S))
        self.level_bar = tk.Canvas(meter_row, height=4, bg=SURFACE_2,
                                   highlightthickness=0, bd=0)
        self.level_bar.pack(fill="x")
        self.level_bar.bind("<Configure>", lambda e: self._draw_level(0.0))

        # --- Статус ---
        self.quick_status = tk.Label(
            inner, text="Готов к записи", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_BODY, anchor="w", justify="left", wraplength=620)
        self.quick_status.pack(anchor="w", pady=(0, SPACE_M))

        # --- Сравнение с образцом ---
        cmp_card = tk.Frame(inner, bg=SURFACE_2, highlightthickness=0, bd=0)
        cmp_card.pack(fill="x", pady=(0, SPACE_M))

        tk.Label(
            cmp_card, text="Сравнить с образцом интонации", bg=SURFACE_2,
            fg=TEXT_PRIMARY, font=FONT_CARD_TITLE, anchor="w",
            padx=SPACE_M, pady=SPACE_M).pack(anchor="w")

        cmp_row = tk.Frame(cmp_card, bg=SURFACE_2)
        cmp_row.pack(fill="x", padx=SPACE_M, pady=(0, SPACE_S))

        self.btn_cmp_together = self._btn(
            cmp_row, "🔊  Одновременно", lambda: self._set_compare_mode("together"),
            bg=SURFACE_1, fg=TEXT_PRIMARY, padx=12, pady=6)
        self.btn_cmp_together.pack(side="left", padx=(0, SPACE_S))

        self.btn_cmp_delay = self._btn(
            cmp_row, "⏱  С задержкой", lambda: self._set_compare_mode("delay"),
            bg=SURFACE_1, fg=TEXT_PRIMARY, padx=12, pady=6)
        self.btn_cmp_delay.pack(side="left")

        tk.Label(
            cmp_row, text="— образец и своя запись —", bg=SURFACE_2,
            fg=TEXT_MUTED, font=FONT_SECONDARY, anchor="w").pack(
                side="left", padx=SPACE_M)

        self.btn_compare = self._btn(
            cmp_card, "▶  Сравнить: образец + моя запись", self._compare_current,
            bg=SURFACE_1, fg=TEXT_PRIMARY, padx=14, pady=8, state="disabled")
        self.btn_compare.pack(anchor="w", padx=SPACE_M, pady=(0, SPACE_M))

        # --- Финальные действия ---
        self.final_row = tk.Frame(inner, bg=SURFACE_1)
        self.final_row.pack(fill="x", pady=(0, 0))
        self.final_row.pack_forget()

        self.btn_build_ref = self._btn(
            self.final_row, "★  Собрать образец голоса", self._build_reference,
            bg=ACCENT, fg="#0B1118", padx=14, pady=8)
        self.btn_build_ref.pack(side="left", padx=(0, SPACE_S))

        self.btn_clone = self._btn(
            self.final_row, "🎙  Клонировать и озвучить всё", self._clone_all,
            bg=GREEN, fg="#fff", padx=14, pady=8)
        self.btn_clone.pack(side="left")

        self.final_status = tk.Label(
            inner, text="", bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY,
            anchor="w")
        self.final_status.pack(anchor="w", pady=(SPACE_S, 0))

        # --- Прогресс клонирования ---
        self.clone_box = tk.Frame(inner, bg=SURFACE_2, highlightthickness=0, bd=0)
        # не показываем, пока не запущена задача
        self.clone_title = tk.Label(
            self.clone_box, text="", bg=SURFACE_2, fg=TEXT_PRIMARY,
            font=("Segoe UI Variable", 11, "bold"), anchor="w")
        self.clone_title.pack(fill="x", padx=SPACE_M, pady=(SPACE_M, 2))

        self.clone_stage = tk.Label(
            self.clone_box, text="", bg=SURFACE_2, fg=ACCENT,
            font=FONT_SECONDARY, anchor="w")
        self.clone_stage.pack(fill="x", padx=SPACE_M)

        self.clone_bar = tk.Canvas(self.clone_box, height=8, bg=SURFACE_1,
                                   highlightthickness=0, bd=0)
        self.clone_bar.pack(fill="x", padx=SPACE_M, pady=(SPACE_S, 2))
        self.clone_bar.bind("<Configure>", lambda e: self._draw_clone_bar())
        self._clone_value = 0.0

        self.clone_count = tk.Label(
            self.clone_box, text="", bg=SURFACE_2, fg=TEXT_SECONDARY,
            font=FONT_SECONDARY, anchor="w")
        self.clone_count.pack(fill="x", padx=SPACE_M, pady=(0, 2))

        self.clone_log = tk.Text(self.clone_box, height=5, bg=SURFACE_1,
                                 fg=TEXT_SECONDARY, font=FONT_MONO,
                                 relief="flat", bd=0, wrap="word")
        self.clone_log.pack(fill="x", padx=SPACE_M, pady=(0, SPACE_M))
        self.clone_log.configure(state="disabled")

        self._set_compare_mode("together")

    # ==================================================================
    # Под-вкладка 2. «Подсказки»
    # ==================================================================
    def _build_prompts(self, parent):
        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x", pady=(0, SPACE_M))

        tk.Label(
            head, text="💬  Подсказки", bg=BG, fg=TEXT_PRIMARY,
            font=FONT_H2, anchor="w").pack(side="left")

        self.btn_play_all = self._btn(
            head, "▶  Прослушать все", self._play_all_prompts,
            bg=SURFACE_2, fg=TEXT_PRIMARY, padx=14, pady=7)
        self.btn_play_all.pack(side="right")

        # Фильтр по эмоции
        filt = tk.Frame(parent, bg=BG)
        filt.pack(fill="x", pady=(0, SPACE_S))
        tk.Label(filt, text="Интонация:", bg=BG, fg=TEXT_MUTED,
                 font=FONT_SECONDARY, anchor="w").pack(side="left",
                                                       padx=(0, SPACE_S))
        self._filter_buttons: dict[str, tk.Button] = {}
        for key, title in _EMO_FILTERS:
            btn = self._btn(
                filt, title, lambda k=key: self._set_filter(k),
                bg=SURFACE_1, fg=TEXT_MUTED, padx=12, pady=5)
            btn.pack(side="left", padx=(0, SPACE_XS))
            self._filter_buttons[key] = btn
        self._set_filter("all")

        # Список
        list_card = GlassCard(parent, radius=RADIUS_CARD, pad=SPACE_M)
        list_card.pack(fill="both", expand=True, pady=(0, SPACE_M))
        inner = list_card.inner
        inner.grid_columnconfigure(0, weight=1)

        self.prompt_table = DarkTable(
            inner,
            columns=(("n", "#", 0, "center"),
                     ("text", "Фраза (что сказать)", 6, "w"),
                     ("emo", "Интонация", 3, "w"),
                     ("dur", "Длит.", 1, "center")),
            visible_rows=10, on_select=self._on_prompt_select)
        self.prompt_table.pack(fill="both", expand=True, pady=(0, SPACE_M))

        # Детали выбранной подсказки
        detail = tk.Frame(inner, bg=SURFACE_2, highlightthickness=0, bd=0)
        detail.pack(fill="x")
        self.prompt_detail = detail

        self.detail_ru = tk.Label(
            detail, text="", bg=SURFACE_2, fg=TEXT_PRIMARY,
            font=("Segoe UI Variable", 14, "bold"), anchor="w", justify="left",
            wraplength=620, padx=SPACE_M, pady=SPACE_M)
        self.detail_ru.pack(fill="x")

        self.detail_es = tk.Label(
            detail, text="", bg=SURFACE_2, fg=TEXT_MUTED, font=FONT_SECONDARY,
            anchor="w", justify="left", wraplength=620, padx=SPACE_M)
        self.detail_es.pack(fill="x")

        drow = tk.Frame(detail, bg=SURFACE_2)
        drow.pack(fill="x", padx=SPACE_M, pady=SPACE_M)

        self.btn_detail_play = self._btn(
            drow, "🔊  Образец", self._play_selected_prompt,
            bg=SURFACE_1, fg=TEXT_PRIMARY, padx=14, pady=7)
        self.btn_detail_play.pack(side="left", padx=(0, SPACE_S))

        self.btn_detail_cmp = self._btn(
            drow, "▶  Сравнить с моей записью", self._compare_selected,
            bg=SURFACE_1, fg=TEXT_PRIMARY, padx=14, pady=7, state="disabled")
        self.btn_detail_cmp.pack(side="left")

        self.detail_status = tk.Label(
            detail, text="Выбери подсказку в списке", bg=SURFACE_2,
            fg=TEXT_MUTED, font=FONT_SECONDARY, anchor="w",
            padx=SPACE_M, pady=SPACE_M)
        self.detail_status.pack(fill="x")

    # ==================================================================
    # Под-вкладка 3. «Образцы»
    # ==================================================================
    def _build_samples(self, parent):
        # --- Профили голоса ---
        prof_card = GlassCard(parent, radius=RADIUS_CARD, pad=SPACE_M)
        prof_card.pack(fill="x", pady=(0, SPACE_M))
        pinner = prof_card.inner
        pinner.grid_columnconfigure(0, weight=1)

        tk.Label(
            pinner, text="🎭  Профили голоса", bg=SURFACE_1, fg=TEXT_PRIMARY,
            font=FONT_H2, anchor="w").pack(anchor="w", pady=(0, SPACE_XS))

        tk.Label(
            pinner,
            text="Несколько клонов одного голоса. Выбери активный — "
                 "он используется для перевода и клонирования.",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY,
            anchor="w", justify="left", wraplength=620).pack(
                anchor="w", pady=(0, SPACE_S))

        prof_row = tk.Frame(pinner, bg=SURFACE_1)
        prof_row.pack(fill="x", pady=(0, SPACE_S))

        self.profile_var = tk.StringVar(value=sp.get_active_profile() or "（общий）")
        self.profile_combo = ttk.Combobox(
            prof_row, textvariable=self.profile_var, state="readonly",
            values=["（общий）"] + sp.list_profiles(), width=28)
        # выставляем текущий элемент явно: иначе комбобокс показывает
        # пустую строку, хотя профиль выбран
        _vals = ["（общий）"] + sp.list_profiles()
        _act = sp.get_active_profile()
        self.profile_combo.current(_vals.index(_act) if _act in _vals else 0)
        self.profile_combo.pack(side="left")
        self.profile_combo.bind(
            "<<ComboboxSelected>>", self._on_profile_change)

        self.btn_new_profile = self._btn(
            prof_row, "＋  Новый профиль", self._new_profile,
            bg=SURFACE_2, fg=TEXT_PRIMARY, padx=12, pady=6)
        self.btn_new_profile.pack(side="left", padx=(SPACE_S, 0))

        self.btn_del_profile = self._btn(
            prof_row, "🗑", self._delete_profile,
            bg=SURFACE_2, fg=TEXT_MUTED, padx=10, pady=6)
        self.btn_del_profile.pack(side="left", padx=(SPACE_XS, 0))

        self.profile_status = tk.Label(
            pinner, text="", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w", justify="left",
            wraplength=620)
        self.profile_status.pack(anchor="w")

        # --- Образец голоса ---
        ref_card = GlassCard(parent, radius=RADIUS_CARD, pad=SPACE_M)
        ref_card.pack(fill="x", pady=(0, SPACE_M))
        inner = ref_card.inner
        inner.grid_columnconfigure(0, weight=1)

        tk.Label(
            inner, text="📁  Образец голоса", bg=SURFACE_1, fg=TEXT_PRIMARY,
            font=FONT_H2, anchor="w").pack(anchor="w", pady=(0, SPACE_S))

        self.ref_status = tk.Label(
            inner, text="Проверяю…", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_BODY, anchor="w", justify="left", wraplength=620)
        self.ref_status.pack(anchor="w", pady=(0, SPACE_M))

        ref_btns = tk.Frame(inner, bg=SURFACE_1)
        ref_btns.pack(anchor="w", pady=(0, SPACE_M))

        self.btn_play_ref = self._btn(
            ref_btns, "▶  Прослушать образец", self._play_reference,
            bg=SURFACE_2, fg=TEXT_PRIMARY, padx=14, pady=7)
        self.btn_play_ref.pack(side="left", padx=(0, SPACE_S))

        self.btn_build_ref2 = self._btn(
            ref_btns, "★  Собрать из записей", self._build_reference,
            bg=ACCENT, fg="#0B1118", padx=14, pady=7)
        self.btn_build_ref2.pack(side="left", padx=(0, SPACE_S))

        self.btn_clone2 = self._btn(
            ref_btns, "🎙  Клонировать и озвучить всё", self._clone_all,
            bg=GREEN, fg="#fff", padx=14, pady=7)
        self.btn_clone2.pack(side="left")

        # Импорт готового reference.wav (например, из другого профиля
        # или от другой программы) — без пересборки из дублей.
        self.btn_import_ref = self._btn(
            ref_btns, "📥  Импортировать", self._import_reference,
            bg=SURFACE_2, fg=TEXT_PRIMARY, padx=14, pady=7)
        self.btn_import_ref.pack(side="left", padx=(SPACE_S, 0))

        # --- Мои записи ---
        take_card = GlassCard(parent, radius=RADIUS_CARD, pad=SPACE_M)
        take_card.pack(fill="both", expand=True)
        inner2 = take_card.inner
        inner2.grid_columnconfigure(0, weight=1)

        top = tk.Frame(inner2, bg=SURFACE_1)
        top.pack(fill="x", pady=(0, SPACE_S))

        tk.Label(
            top, text="Записи", bg=SURFACE_1, fg=TEXT_PRIMARY,
            font=FONT_CARD_TITLE, anchor="w").pack(side="left")

        self.btn_del_take = self._btn(
            top, "🗑  Удалить", self._delete_selected_take,
            bg=SURFACE_2, fg=TEXT_MUTED, padx=12, pady=5, state="disabled")
        self.btn_del_take.pack(side="right", padx=(SPACE_S, 0))

        self.btn_take_play = self._btn(
            top, "▶  Прослушать", self._play_selected_take,
            bg=SURFACE_2, fg=TEXT_PRIMARY, padx=12, pady=5, state="disabled")
        self.btn_take_play.pack(side="right", padx=(SPACE_S, 0))

        self.btn_take_cmp = self._btn(
            top, "🔊  Сравнить с образцом", self._compare_selected_take,
            bg=SURFACE_2, fg=TEXT_PRIMARY, padx=12, pady=5, state="disabled")
        self.btn_take_cmp.pack(side="right")

        # --- Выборка дублей для нового профиля ---
        #
        # Пользователь переслушивает записи и отмечает те, которые
        # понравились. Клон собирается ИМЕННО из них, а не «из всех
        # подряд, что нашлись в папке».
        pick_row = tk.Frame(inner2, bg=SURFACE_1)
        pick_row.pack(fill="x", pady=(0, SPACE_S))

        self.btn_pick_all = self._btn(
            pick_row, "☑  Выбрать все", self._pick_all_takes,
            bg=SURFACE_2, fg=TEXT_PRIMARY, padx=12, pady=5)
        self.btn_pick_all.pack(side="left", padx=(0, SPACE_XS))

        self.btn_pick_none = self._btn(
            pick_row, "☐  Снять", self._pick_no_takes,
            bg=SURFACE_2, fg=TEXT_MUTED, padx=12, pady=5)
        self.btn_pick_none.pack(side="left", padx=(0, SPACE_S))

        self.pick_count = tk.Label(
            pick_row, text="отмечено: 0", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w")
        self.pick_count.pack(side="left", padx=(0, SPACE_S))

        self.btn_add_to_profile = self._btn(
            pick_row, "＋  Создать профиль и клонировать",
            self._add_selected_to_profile,
            bg=GREEN, fg="#fff", padx=12, pady=5, state="disabled")
        self.btn_add_to_profile.pack(side="right")

        # --- Фильтр по источнику ---
        #
        # Дубли лежат в разных местах: общая папка и папки профилей.
        # Фильтр показывает либо всё, либо только конкретный профиль —
        # чтобы было видно, что именно вошло в клон.
        filter_row = tk.Frame(inner2, bg=SURFACE_1)
        filter_row.pack(fill="x", pady=(0, SPACE_S))

        tk.Label(
            filter_row, text="Показать:", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w").pack(side="left",
                                                  padx=(0, SPACE_S))

        self.take_filter_var = tk.StringVar(value="Все дубли")
        self.take_filter_combo = ttk.Combobox(
            filter_row, textvariable=self.take_filter_var, state="readonly",
            width=30)
        self.take_filter_combo["values"] = self._take_filter_values()
        self.take_filter_combo.current(0)
        self.take_filter_combo.pack(side="left")
        self.take_filter_combo.bind(
            "<<ComboboxSelected>>", self._on_take_filter_change)

        self.btn_open_profile = self._btn(
            filter_row, "📂  Открыть папку профиля",
            self._open_active_profile_folder,
            bg=SURFACE_2, fg=TEXT_PRIMARY, padx=12, pady=5)
        self.btn_open_profile.pack(side="right")

        self.take_table = DarkTable(
            inner2,
            columns=(("file", "Файл", 3, "w"), ("phrase", "Фраза", 5, "w"),
                     ("dur", "Длит.", 1, "center"), ("q", "Качество", 2, "center"),
                     ("saved", "Где", 2, "center")),
            visible_rows=10, on_select=self._on_take_select,
            on_check=self._on_take_check, selectable=True)
        self.take_table.pack(fill="both", expand=True, pady=(0, SPACE_M))

        # Режим сравнения
        cmpmode = tk.Frame(inner2, bg=SURFACE_1)
        cmpmode.pack(fill="x")

        tk.Label(
            cmpmode, text="Сравнение:", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w").pack(side="left",
                                                  padx=(0, SPACE_S))
        self.btn_cmp2_together = self._btn(
            cmpmode, "Одновременно", lambda: self._set_compare_mode("together"),
            bg=SURFACE_2, fg=TEXT_MUTED, padx=12, pady=5)
        self.btn_cmp2_together.pack(side="left", padx=(0, SPACE_XS))
        self.btn_cmp2_delay = self._btn(
            cmpmode, "С задержкой", lambda: self._set_compare_mode("delay"),
            bg=SURFACE_2, fg=TEXT_MUTED, padx=12, pady=5)
        self.btn_cmp2_delay.pack(side="left")

        self.samples_status = tk.Label(
            inner2, text="", bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY,
            anchor="w", wraplength=620)
        self.samples_status.pack(anchor="w", pady=(SPACE_S, 0))

    # ==================================================================
    # Обновление состояния
    # ==================================================================
    def _refresh(self):
        self._update_ref_status()
        self._refresh_prompts()
        self._refresh_samples()

    def _update_ref_status(self):
        # reference активного профиля (или общий, если профиль не выбран)
        try:
            ref_path = sp.active_reference()
        except Exception:
            ref_path = sp.output_paths()["reference"]
        active = sp.get_active_profile()
        if os.path.exists(ref_path):
            try:
                info = sf.info(ref_path)
                where = f"профиль «{active}»" if active else "общий"
                self.ref_status.config(
                    text=f"Образец готов ({where}): {info.duration:.1f} c, "
                         f"{info.samplerate} Гц — {ref_path}",
                    fg=GOOD)
                for b in (self.btn_play_ref, self.btn_build_ref2,
                          self.btn_clone2, self.btn_clone):
                    b.config(state="normal")
                return
            except Exception:
                self.ref_status.config(
                    text=f"Образец есть, но не читается: {ref_path}", fg=WARN)
                return
        self.ref_status.config(
            text="Образца пока нет. Запиши фразы на вкладке «Мой голос за "
                 "3 минуты» — он соберётся автоматически.", fg=TEXT_MUTED)
        for b in (self.btn_play_ref, self.btn_clone2, self.btn_clone):
            b.config(state="disabled")
        self.btn_build_ref2.config(state="normal")

    # ==================================================================
    # Подсказки
    # ==================================================================
    def _set_filter(self, key: str):
        self._prompt_filter.set(key)
        for k, btn in self._filter_buttons.items():
            active = (k == key)
            btn.configure(bg=SURFACE_2 if active else BG,
                          fg=TEXT_PRIMARY if active else TEXT_MUTED)
        self._refresh_prompts()

    def _refresh_prompts(self):
        if not hasattr(self, "prompt_table"):
            return
        filt = self._prompt_filter.get()
        items = plib.manifest()
        rows = []
        for it in items:
            if filt != "all" and it.get("emotion") != filt:
                continue
            rows.append({
                "_id": str(it.get("index", 0)),
                "n": it.get("index", 0) + 1,
                "text": self._prompt_text_ru(it),
                "emo": it.get("emotion_label", ""),
                "dur": (f"{it.get('duration', 0):.1f} c"
                        if it.get("duration") else "—"),
            })
        self.prompt_table.set_rows(rows)
        if rows:
            self.prompt_table.select(rows[0]["_id"])
            self._selected_prompt = int(rows[0]["_id"])
            self._show_prompt_detail(self._selected_prompt)
        else:
            self.detail_ru.config(text="Подсказок с такой интонацией нет")
            self.detail_es.config(text="")
            self.detail_status.config(text="", fg=TEXT_MUTED)
            self.btn_detail_cmp.config(state="disabled")

    def _on_prompt_select(self, rid: str = ""):
        try:
            self._selected_prompt = int(rid)
        except (TypeError, ValueError):
            return
        self._show_prompt_detail(self._selected_prompt)

    def _show_prompt_detail(self, index: int):
        item = None
        for it in plib.manifest():
            if it.get("index") == index:
                item = it
                break
        if not item:
            return
        self.detail_ru.config(text=self._prompt_text_ru(item))
        self.detail_es.config(
            text=f"Образец: {item.get('es', '')}   •   "
                 f"интонация: {item.get('emotion_label', '')}")
        path = plib.audio_path(index)
        if path:
            self.detail_status.config(
                text=f"Готовый образец: {os.path.basename(path)} "
                     f"({item.get('duration', 0):.1f} c)", fg=GOOD)
            self.btn_detail_play.config(state="normal")
        else:
            self.detail_status.config(
                text="Готовый образец не найден — будет синтез вслух",
                fg=WARN)
            self.btn_detail_play.config(state="normal")
        self._update_detail_cmp_button()

    def _update_detail_cmp_button(self):
        """Сравнение доступно, если есть запись этой подсказки."""
        take = self._take_for_prompt(self._selected_prompt)
        self.btn_detail_cmp.config(state="normal" if take else "disabled")

    # ==================================================================
    # Образцы / записи
    # ==================================================================
    def _samples_dir(self) -> str:
        """Папка дублей: у каждого профиля своя.

        Раньше все дубли лежали в одной куче voice_samples/, и reference
        собирался из ВСЕХ записей подряд — разные итерации клонирования
        смешивались. Теперь дубли идут в voice_profiles/<профиль>/takes/,
        а общий reference.wav остаётся для случая «без профиля».
        """
        try:
            active = sp.get_active_profile()
        except Exception:
            active = ""
        if active:
            d = os.path.join(sp.profile_dir(active), "takes")
            try:
                os.makedirs(d, exist_ok=True)
            except Exception:
                pass
            return d
        return sp.output_paths()["samples"]

    def _takes_meta_path(self) -> str:
        return os.path.join(self._samples_dir(), "takes.json")

    def _all_take_sources(self) -> list[tuple[str, str]]:
        """Все папки с дублями: (путь, метка источника).

        Показываем дубли из ВСЕХ мест, чтобы их можно было выбрать и
        добавить в любой профиль — независимо от того, какой профиль
        активен сейчас.

        Возвращает список (папка, метка): общая папка + папки профилей.
        """
        out: list[tuple[str, str]] = []
        # общая папка
        out.append((sp.output_paths()["samples"], ""))
        # профили
        try:
            for name in sp.list_profiles():
                d = os.path.join(sp.profile_dir(name), "takes")
                if os.path.isdir(d):
                    out.append((d, name))
        except Exception:
            pass
        return out

    def _all_take_files(self) -> list[tuple[str, str]]:
        """Все дубли: (путь, метка профиля).

        ВАЖНО: дедуп НЕ между источниками. Один и тот же дубль может
        лежать и в общей папке, и в профиле (мы его туда копируем) — это
        разные записи для пользователя, и обе должны быть видны. Иначе
        фильтр «Профиль: Кирилл» показывал бы 0 файлов.
        """
        result: list[tuple[str, str]] = []
        for d, label in self._all_take_sources():
            try:
                names = sorted(f for f in os.listdir(d)
                               if f.lower().endswith(".wav"))
            except Exception:
                continue
            # дедуп только внутри одной папки (на случай дублей имён)
            seen_here: set[str] = set()
            for fn in names:
                if fn in seen_here:
                    continue
                seen_here.add(fn)
                result.append((os.path.join(d, fn), label))
        return result

    # ---------- фильтр дублей по источнику ----------

    def _take_filter_values(self) -> list[str]:
        """Варианты фильтра: всё / общая папка / профили."""
        vals = ["Все дубли", "Общая папка"]
        try:
            for name in sp.list_profiles():
                vals.append(f"Профиль: {name}")
        except Exception:
            pass
        return vals

    def _take_filter_code(self) -> str:
        """Код фильтра: 'all' / 'common' / имя профиля."""
        choice = self.take_filter_var.get()
        if choice.startswith("Профиль: "):
            return choice[len("Профиль: "):]
        if choice == "Общая папка":
            return "common"
        return "all"

    def _on_take_filter_change(self, _event=None):
        """Сменить фильтр источника."""
        if not hasattr(self, "take_filter_combo"):
            return
        if not self.take_filter_combo.winfo_exists():
            return
        self.take_filter_combo["values"] = self._take_filter_values()
        self._refresh_samples()

    def _open_active_profile_folder(self):
        """Открыть папку активного профиля в Проводнике.

        Если профиль не выбран — открываем общую папку дублей.
        """
        active = sp.get_active_profile()
        if active:
            folder = sp.profile_dir(active)
        else:
            folder = sp.output_paths()["samples"]
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception:
            pass
        try:
            os.startfile(folder)          # Windows
            return
        except Exception:
            pass
        try:
            import subprocess
            subprocess.Popen(["explorer", folder])
        except Exception as exc:
            self.samples_status.config(
                text=f"Не открыть папку: {exc}", fg=WARN)

    def _load_takes_meta(self) -> dict:
        path = self._takes_meta_path()
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            takes = data.get("takes")
            return takes if isinstance(takes, dict) else {}
        except Exception:
            return {}

    def _save_takes_meta(self, meta: dict):
        path = self._takes_meta_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"takes": meta}, fh, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def _take_files(self) -> list[str]:
        d = self._samples_dir()
        try:
            return sorted(f for f in os.listdir(d) if f.endswith(".wav"))
        except Exception:
            return []

    def _prompt_index_of_take(self, fname: str, meta: dict) -> int | None:
        entry = meta.get(fname)
        if isinstance(entry, dict) and entry.get("prompt_index") is not None:
            try:
                return int(entry["prompt_index"])
            except Exception:
                return None
        m = _TAKE_RE.match(fname)
        if m:
            return int(m.group(1)) - 1
        return None

    def _take_for_prompt(self, prompt_index: int) -> str | None:
        """Последняя запись для указанной подсказки."""
        meta = self._load_takes_meta()
        best = None
        for fname in self._take_files():
            if self._prompt_index_of_take(fname, meta) == prompt_index:
                best = fname
        if best:
            return os.path.join(self._samples_dir(), best)
        return None

    def _refresh_samples(self):
        if not hasattr(self, "take_table"):
            return
        try:
            self.take_table.winfo_exists()
        except Exception:
            return
        if not self.take_table.winfo_exists():
            return
        # фильтр источника: всё / общая папка / конкретный профиль
        flt = self._take_filter_code() if hasattr(self, "take_filter_var") else "all"

        entries = self._all_take_files()
        rows = []
        self._take_paths = {}   # rid -> полный путь
        for path, label in entries:
            # применяем фильтр
            if flt == "common" and label:
                continue
            if flt not in ("all", "common") and label != flt:
                continue

            fname = os.path.basename(path)
            dur, q = "—", "—"
            try:
                data, sr = sf.read(path, dtype="float32", always_2d=False)
                if getattr(data, "ndim", 1) > 1:
                    data = data.mean(axis=1)
                dur = f"{len(data) / sr:.1f} c"
                rep = core.quality_report(data, sr)
                q = "ок" if rep["ok"] else "!"
            except Exception:
                pass
            meta = self._load_takes_meta()
            idx = self._prompt_index_of_take(fname, meta)
            phrase = "—"
            if idx is not None:
                for it in plib.manifest():
                    if it.get("index") == idx:
                        phrase = self._prompt_text_ru(it)
                        break
            # метка источника: «общий» или имя профиля
            src = label if label else "общий"
            rid = f"{label}::{fname}" if label else fname
            self._take_paths[rid] = path
            rows.append({"_id": rid, "file": fname, "phrase": phrase,
                         "dur": dur, "q": q, "saved": src})

        # сортируем: по номеру фразы, затем по времени
        def _key(r):
            fname = r.get("file", "")
            m = _TAKE_RE.match(fname)
            num = int(m.group(1)) if m else 99
            return (num, fname)

        rows.sort(key=_key)
        self.take_table.set_rows(rows)
        self.samples_status.config(
            text=f"Показано: {len(rows)} из {len(entries)}", fg=TEXT_MUTED)

    def _on_take_select(self, rid: str = ""):
        if not rid:
            return
        self._selected_take = rid
        for b in (self.btn_take_play, self.btn_take_cmp, self.btn_del_take):
            b.config(state="normal")

    # ==================================================================
    # Воспроизведение
    # ==================================================================
    def _run_async(self, fn, *args):
        """Запустить воспроизведение в потоке (UI не должен замирать)."""

        def _wrapper():
            try:
                fn(*args)
            except Exception:
                pass

        threading.Thread(target=_wrapper, daemon=True).start()

    # ---------- единый плеер (играть/стоп, без наложения) ----------
    def _toggle_play_file(self, path: str, label: str = ""):
        """Играть файл или остановить, если он уже играет.

        Новый запуск всегда гасит предыдущий — два файла не звучат
        одновременно.
        """
        if not path or not os.path.exists(path):
            self.samples_status.config(text="Файл не найден", fg=WARN)
            return
        playing = ap.player_toggle_file(path, self.studio)
        self._sync_play_buttons()
        if playing:
            self.samples_status.config(text=f"▶  {label or os.path.basename(path)}",
                                       fg=ACCENT)
        else:
            self.samples_status.config(text="■  Остановлено", fg=TEXT_MUTED)

    def _stop_playback(self):
        """Остановить всё, что играет."""
        try:
            ap.player_stop()
        except Exception:
            pass
        self._sync_play_buttons()
        self.samples_status.config(text="■  Остановлено", fg=TEXT_MUTED)

    def _sync_play_buttons(self):
        """Обновить надписи кнопок: «▶ Прослушать» / «■ Стоп»."""
        try:
            playing = ap.player_is_playing()
        except Exception:
            playing = False
        # кнопка проигрывания выбранного дубля
        if hasattr(self, "btn_take_play"):
            self.btn_take_play.config(
                text="■  Стоп" if playing else "▶  Прослушать")
        # кнопка образца
        if hasattr(self, "btn_play_ref"):
            self.btn_play_ref.config(
                text="■  Стоп" if playing else "▶  Прослушать образец")

    def _play_current_prompt(self):
        idx = self._quick_index if self._quick_active else self._selected_prompt
        self._play_prompt_index(idx)

    def _play_prompt_index(self, index: int):
        path = plib.audio_path(index)
        if path:
            self._toggle_play_file(path, f"образец интонации {index + 1}")
            return
        # Запасной путь: синтез на лету
        self._play_prompt_synth(index)

    def _play_prompt_synth(self, index: int):
        """Синтез подсказки на лету (если готовых файлов нет)."""
        items = plib.manifest()
        item = next((i for i in items if i.get("index") == index), None)
        if not item:
            return
        self.quick_status.config(text="Готовлю образец…", fg=WARN)

        def _work():
            try:
                import voice_prompts as vp
                path = vp.synthesize_prompt(item.get("es", ""),
                                           item.get("emotion", ""))
                if path:
                    play_file(path, self.studio)
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True).start()

    def _play_selected_prompt(self):
        self._play_prompt_index(self._selected_prompt)

    def _play_all_prompts(self):
        items = plib.manifest()
        if not items:
            return
        self.btn_play_all.config(state="disabled")
        if self.prompt_table.rows:
            self.prompt_table.select(self.prompt_table.rows[0]["_id"])
        self.detail_status.config(text="Проигрываю все подсказки…", fg=ACCENT)

        def _work():
            for it in items:
                path = plib.audio_path(it.get("index", 0))
                if path:
                    play_file(path, self.studio)
                time.sleep(0.25)

        def _done():
            self.btn_play_all.config(state="normal")
            self.detail_status.config(text="Готово", fg=GOOD)

        def _wrapper():
            try:
                _work()
            finally:
                self.after(0, _done)

        threading.Thread(target=_wrapper, daemon=True).start()

    def _play_reference(self):
        try:
            ref = sp.active_reference()
        except Exception:
            ref = sp.output_paths()["reference"]
        if not os.path.exists(ref):
            self.ref_status.config(text="Образца ещё нет — запиши фразы",
                                   fg=WARN)
            return
        self._toggle_play_file(ref, "образец голоса")

    def _play_selected_take(self):
        if not self._selected_take:
            return
        paths = getattr(self, "_take_paths", {}) or {}
        path = paths.get(self._selected_take)
        if not path:
            path = os.path.join(self._samples_dir(), self._selected_take)
        if not os.path.exists(path):
            self.samples_status.config(
                text=f"Файл не найден: {self._selected_take}", fg=WARN)
            return
        self._toggle_play_file(path, os.path.basename(path))

    # ---------- сравнение ----------

    def _set_compare_mode(self, mode: str):
        self._compare_mode.set(mode)
        pairs = (("btn_cmp_together", "together"),
                 ("btn_cmp2_together", "together"),
                 ("btn_cmp_delay", "delay"),
                 ("btn_cmp2_delay", "delay"))
        for attr, key in pairs:
            btn = getattr(self, attr, None)
            if btn is None:
                continue
            active = (self._compare_mode.get() == key)
            btn.configure(bg=SURFACE_1 if active else SURFACE_2,
                          fg=TEXT_PRIMARY if active else TEXT_MUTED)

    def _compare_files(self, prompt_path: str | None, take_path: str | None,
                       label: str = ""):
        mode = self._compare_mode.get()
        if not take_path:
            return
        if not prompt_path:
            prompt_path = sp.output_paths()["reference"]
        if not prompt_path or not os.path.exists(prompt_path):
            self.quick_status.config(
                text="Нет образца для сравнения", fg=WARN)
            return
        what = "одновременно" if mode == "together" else "с задержкой"
        self.quick_status.config(
            text=f"▶  Сравниваю {what}{(' — ' + label) if label else ''}…",
            fg=ACCENT)
        self._run_async(play_compare, prompt_path, take_path, mode, self.studio)

    def _compare_current(self):
        """Сравнить текущий образец с только что записанной фразой."""
        if not self._last_take:
            self.quick_status.config(text="Сначала запиши фразу", fg=WARN)
            return
        path = plib.audio_path(self._quick_index)
        self._compare_files(path, self._last_take)

    def _compare_selected(self):
        take = self._take_for_prompt(self._selected_prompt)
        if not take:
            self.detail_status.config(
                text="Для этой подсказки ещё нет записи", fg=WARN)
            return
        path = plib.audio_path(self._selected_prompt)
        self._compare_files(path, take)
        self.detail_status.config(
            text="▶  Сравниваю образец с твоей записью…", fg=ACCENT)

    def _compare_selected_take(self):
        if not self._selected_take:
            return
        path = os.path.join(self._samples_dir(), self._selected_take)
        meta = self._load_takes_meta()
        idx = self._prompt_index_of_take(self._selected_take, meta)
        prompt = plib.audio_path(idx) if idx is not None else None
        self._compare_files(prompt, path, self._selected_take)
        self.samples_status.config(
            text="▶  Сравниваю образец с записью…", fg=ACCENT)

    # ==================================================================
    # Сценарий записи
    # ==================================================================
    def _quick_start(self):
        """Начать сценарий «Мой голос за 3 минуты»."""
        if self._quick_active:
            self._quick_advance()
            return
        self._quick_active = True
        self._quick_index = 0
        self._last_take = None
        self.btn_start.config(state="disabled")
        self.btn_next.config(state="disabled")
        self.btn_redo.config(state="disabled")
        self.btn_compare.config(state="disabled")
        self.final_row.pack_forget()
        self.quick_status.config(text="Готовлю микрофон…", fg=TEXT_MUTED)
        self._quick_next()

    def _quick_advance(self):
        """Перейти к следующей фразе."""
        if not self._quick_active:
            return
        self._quick_index += 1
        self._quick_next()

    def _quick_stop(self):
        """Остановить сценарий."""
        self._quick_active = False
        self._phase = "idle"
        self.btn_start.config(state="normal")
        self.btn_next.config(state="disabled")
        self.btn_redo.config(state="disabled")
        self.btn_compare.config(state="disabled")
        self.quick_status.config(text="Остановлено", fg=TEXT_MUTED)
        self._draw_level(0.0)

    def _current_prompt_text(self) -> str:
        items = plib.manifest()
        for it in items:
            if it.get("index") == self._quick_index:
                return self._prompt_text_ru(it)
        # запасной вариант — прямо из кода
        try:
            prompts = core.PROMPTS_RU
            if self._quick_index < len(prompts):
                return prompts[self._quick_index].replace(
                    "{name}", self._display_name())
        except Exception:
            pass
        return ""

    def _current_emotion_label(self) -> str:
        for it in plib.manifest():
            if it.get("index") == self._quick_index:
                return it.get("emotion_label", "")
        return ""

    def _quick_next(self):
        """Следующая фраза: показать, проиграть образец, записать."""
        if not self._quick_active:
            return
        items = plib.manifest()
        if not items:
            self.quick_status.config(text="Нет подсказок", fg=BAD)
            return
        if self._quick_index >= len(items):
            self._quick_finish()
            return

        self._phase = "playing"
        text = self._current_prompt_text()
        emo = self._current_emotion_label()

        self.prompt_text.config(text=text)
        self.prompt_emo.config(text=f"Интонация: {emo}")
        self.quick_step.config(text=f"Фраза {self._quick_index + 1} из {len(items)}")
        self._progress_value = self._quick_index / float(len(items))
        self._draw_progress()
        self.quick_status.config(text="Сейчас прозвучит образец интонации…",
                                 fg=WARN)
        self.btn_next.config(state="disabled")
        self.btn_redo.config(state="disabled")
        self.btn_compare.config(state="disabled")
        self._last_take = None

        # 1. Проигрываем готовый образец
        path = plib.audio_path(self._quick_index)
        self.after(350, lambda: self._play_then_record(path))

    def _play_then_record(self, prompt_path: str | None):
        """Проиграть образец и запустить запись."""
        state = {"error": ""}

        def _work():
            try:
                if prompt_path and os.path.exists(prompt_path):
                    play_file(prompt_path, self.studio)
                else:
                    item = next((i for i in plib.manifest()
                                 if i.get("index") == self._quick_index), None)
                    if item:
                        import voice_prompts as vp
                        p = vp.synthesize_prompt(item.get("es", ""),
                                                 item.get("emotion", ""))
                        if p:
                            play_file(p, self.studio)
                        else:
                            state["error"] = "нет готового образца"
                    else:
                        state["error"] = "подсказка не найдена"
            except Exception as exc:
                state["error"] = f"{type(exc).__name__}: {exc}"
                try:
                    import traceback
                    logs = os.path.join(sp.workspace(), "logs")
                    os.makedirs(logs, exist_ok=True)
                    with open(os.path.join(logs, "prompt_audio.log"), "a",
                              encoding="utf-8") as fh:
                        fh.write(f"\n[{time.strftime('%H:%M:%S')}] "
                                 f"prompt {self._quick_index}\n"
                                 f"{traceback.format_exc()}")
                except Exception:
                    pass

        t = threading.Thread(target=_work, daemon=True)
        t.start()

        def _after_play():
            if t.is_alive():
                self.after(200, _after_play)
                return
            if not self._quick_active:
                return
            if state["error"]:
                self.quick_status.config(
                    text=f"Образец не прозвучал ({state['error']}). "
                         f"Можно записать без него.", fg=BAD)
                self.btn_next.config(state="normal")
                self._phase = "review"
                return
            self._start_quick_record()

        self.after(300, _after_play)

    def _start_quick_record(self):
        """Начать запись одной фразы."""
        recorder = getattr(self.studio, "recorder", None)
        if recorder is None:
            self.quick_status.config(text="Рекуордер недоступен", fg=BAD)
            self._phase = "idle"
            self.btn_start.config(state="normal")
            return
        try:
            # Устройство НЕ подставляем руками: Recorder.start(None) сам
            # выберет рабочую частоту через best_rate(None) -> fallback
            # (44100). Если подставить конкретный индекс микрофона, best_rate
            # вернёт первую «открывшуюся» частоту (16000), на которой fifine
            # отдаёт почти тишину — отсюда битая запись.
            recorder.start(recorder.device)
        except Exception as exc:
            self.quick_status.config(text=f"Микрофон не открылся: {exc}", fg=BAD)
            self._phase = "idle"
            self.btn_start.config(state="normal")
            return

        self._phase = "recording"
        self._rec_started = time.time()
        # Лимит: длина образца + 2.5 с на ответ
        limit = 5.0
        for it in plib.manifest():
            if it.get("index") == self._quick_index:
                limit = max(4.0, float(it.get("duration") or 3.0) + 2.5)
                break
        self._rec_limit = limit
        self.quick_status.config(text="●  Записываю… говори!", fg=BAD)
        self.quick_timer.config(text="")
        self._tick_rec()

    def _tick_rec(self):
        """Обновление индикатора записи и авто-стоп по времени."""
        if self._phase != "recording":
            return
        elapsed = time.time() - self._rec_started
        recorder = getattr(self.studio, "recorder", None)
        level = float(getattr(recorder, "level", 0.0) or 0.0)
        self._draw_level(min(1.0, level * 3.0))
        self.quick_timer.config(text=f"{elapsed:4.1f} c / {self._rec_limit:.0f} c")
        if elapsed >= self._rec_limit:
            self._stop_quick_record()
            return
        self.after(100, self._tick_rec)

    def _stop_quick_record(self):
        """Остановить запись, проверить качество, показать результат."""
        if self._phase != "recording":
            return
        self._phase = "review"
        self._draw_level(0.0)
        recorder = getattr(self.studio, "recorder", None)
        raw = np.zeros(0, dtype=np.float32)
        if recorder is not None:
            try:
                raw = recorder.stop()
            except Exception:
                raw = np.zeros(0, dtype=np.float32)
        self.quick_timer.config(text="")

        if len(raw) == 0:
            self.quick_status.config(
                text="Звук не получен. Нажми «Перезаписать».", fg=BAD)
            self.btn_redo.config(state="normal")
            return

        sr = int(getattr(recorder, "sr", core.SR) or core.SR)
        trimmed = core.trim_by_energy(raw, sr)
        rep = core.quality_report(trimmed, sr)
        if not rep["ok"]:
            self.quick_status.config(
                text=f"✖  {rep.get('reason', '')} — нажми «Перезаписать».",
                fg=WARN)
            self.btn_redo.config(state="normal")
            return

        path = self._save_take(trimmed, self._quick_index, sr)
        self._last_take = path
        self.quick_status.config(
            text=f"✔  ок — запись нормальная ({rep['dur']:.1f} c). "
                 f"Сравни с образцом или жми «Дальше».",
            fg=GOOD)
        self.btn_next.config(state="normal")
        self.btn_redo.config(state="normal")
        self.btn_compare.config(state="normal" if path else "disabled")
        self._refresh_samples()
        self._update_detail_cmp_button()

    def _save_take(self, audio, prompt_index: int, sr: int | None = None) -> str | None:
        """Сохранить запись в voice_samples/ с привязкой к подсказке.

        ВАЖНО: старая запись ЭТОЙ ЖЕ фразы удаляется. Раньше при
        «Перезаписать» создавался новый файл, а старый оставался, и в
        reference попадали оба дубля (в т.ч. неудачный).

        sr — частота, на которой шла запись. Пишем файл именно с ней,
        иначе дубль с данными 16000 и меткой 44100 проигрывается
        в 2.75 раза быстрее («писк»).
        """
        d = self._samples_dir()
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            return None

        # убираем предыдущие дубли этой фразы — и файлы, и записи в meta
        meta = self._load_takes_meta()
        for fname in list(meta.keys()):
            entry = meta.get(fname)
            if not isinstance(entry, dict):
                continue
            try:
                same = int(entry.get("prompt_index", -1)) == int(prompt_index)
            except Exception:
                same = False
            if not same:
                continue
            try:
                p = os.path.join(d, fname)
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
            meta.pop(fname, None)
        self._save_takes_meta(meta)

        stamp = time.strftime("%H%M%S")
        fname = f"p{prompt_index + 1:02d}_take_{stamp}.wav"
        path = os.path.join(d, fname)
        i = 1
        while os.path.exists(path):
            fname = f"p{prompt_index + 1:02d}_take_{stamp}_{i}.wav"
            path = os.path.join(d, fname)
            i += 1
        try:
            sf.write(path, audio, int(sr or core.SR), subtype="PCM_16")
        except Exception:
            return None
        meta = self._load_takes_meta()
        meta[fname] = {"prompt_index": prompt_index, "saved": stamp}
        self._save_takes_meta(meta)
        return path

    def _redo_take(self):
        """Перезаписать текущую фразу."""
        if not self._quick_active:
            return
        self.btn_redo.config(state="disabled")
        self.btn_next.config(state="disabled")
        self.btn_compare.config(state="disabled")
        self._phase = "playing"
        self.quick_status.config(text="Перезаписываю…", fg=WARN)
        path = plib.audio_path(self._quick_index)
        self.after(250, lambda: self._play_then_record(path))

    def _quick_finish(self):
        """Все фразы записаны — собрать образец и предложить клонирование."""
        self._quick_active = False
        self._phase = "idle"
        self.prompt_text.config(text="Все фразы записаны — голос готов")
        self.prompt_emo.config(text="")
        self.quick_step.config(text="Готово")
        self._progress_value = 1.0
        self._draw_progress()
        self.btn_start.config(state="normal")
        self.btn_next.config(state="disabled")
        self.btn_redo.config(state="disabled")
        self.btn_compare.config(state="disabled")
        self.final_row.pack(fill="x", pady=(0, 0))

        self.quick_status.config(text="Собираю образец голоса…", fg=WARN)
        res = self._build_reference()
        if res:
            self.final_status.config(
                text="Образец собран. Можно клонировать голос и озвучить все "
                     "фразы.", fg=GOOD)
        else:
            self.final_status.config(
                text="Образец не собрался — проверь записи на вкладке «Образцы».",
                fg=WARN)

    # ==================================================================
    # Образец и клонирование
    # ==================================================================
    # ------------------------------------------------------------------
    # Профили голоса
    # ------------------------------------------------------------------
    def _refresh_profiles(self):
        """Обновить список профилей в комбобоксе «Образцы».

        ВАЖНО: не вызываем current() — он перезаписывает profile_var и
        сбивает выбор пользователя. Список значений обновляем, а текст
        и индекс ставим только если комбобокс реально пуст.
        """
        active = sp.get_active_profile()
        values = ["（общий）"] + sp.list_profiles()

        if hasattr(self, "profile_combo"):
            self.profile_combo.configure(values=values)
            cur = (self.profile_var.get() or "").strip()
            if not cur:
                # комбобокс пуст — ставим активный профиль
                self.profile_var.set(active if active in values else "（общий）")
                try:
                    idx = values.index(active) if active in values else 0
                    self.profile_combo.current(idx)
                except Exception:
                    pass

        if hasattr(self, "quick_profile_hint"):
            self._update_quick_profile_hint()

    def _refresh_profiles_force(self):
        """Принудительно выставить активный профиль в комбобоксе."""
        if not hasattr(self, "profile_combo"):
            return
        active = sp.get_active_profile()
        values = ["（общий）"] + sp.list_profiles()
        self.profile_combo.configure(values=values)
        self.profile_var.set(active if active in values else "（общий）")
        try:
            idx = values.index(active) if active in values else 0
            self.profile_combo.current(idx)
        except Exception:
            pass

    def _update_quick_profile_hint(self):
        """Подсказка под выбором профиля в «Мой голос»."""
        if not hasattr(self, "quick_profile_hint"):
            return
        active = sp.get_active_profile()
        if active:
            ref = sp.profile_reference(active)
            n = len(self._profile_takes(active))
            self.quick_profile_hint.config(
                text=f"Дубли и клон — в профиль «{active}». Записей: {n}."
                     + ("" if os.path.exists(ref) else " Reference ещё не собран."),
                fg=TEXT_MUTED)
        else:
            self.quick_profile_hint.config(
                text="Общий режим: записи в voice_samples/, "
                     "reference — общий reference.wav",
                fg=TEXT_MUTED)

    def _profile_takes(self, name: str) -> list[str]:
        """Список дублей в профиле."""
        d = os.path.join(sp.profile_dir(name), "takes")
        try:
            return [f for f in os.listdir(d) if f.lower().endswith(".wav")]
        except Exception:
            return []

    def _on_profile_change(self, _event=None):
        """Сменить активный профиль (из «Образцы»)."""
        choice = (self.profile_var.get() or "").strip()
        # варианты: «（общий）» / имя профиля
        name = "" if choice in ("", "（общий）", "(общий)") else choice
        sp.set_active_profile(name)
        # синхронизируем выбор на главной странице
        try:
            home = None
            # 1) через Studio (MainWindow кладёт туда ссылку)
            studio = getattr(self, "studio", None)
            if studio is not None:
                home = getattr(studio, "home_page", None)
            # 2) через корневое окно
            if home is None:
                top = self.winfo_toplevel()
                home = getattr(top, "home", None)
            if home is not None and hasattr(home, "home_profile_var"):
                home.home_profile_var.set(name if name else "（общий）")
        except Exception:
            pass
        if name:
            ref = sp.profile_reference(name)
            if os.path.exists(ref):
                self.profile_status.config(
                    text=f"Активный профиль: «{name}»", fg=GOOD)
            else:
                self.profile_status.config(
                    text=f"Профиль «{name}» выбран, но reference.wav нет — "
                         f"собери образец", fg=WARN)
        else:
            self.profile_status.config(
                text="Активный профиль: общий reference.wav", fg=GOOD)
        # обновляем отображение образца
        try:
            self._update_ref_status()
        except Exception:
            pass
        # согласуем фильтр источника с новым профилем
        try:
            self._sync_filter_after_profile_change()
        except Exception:
            pass
        # ВАЖНО: _refresh_profiles здесь НЕ вызываем — он перезаписывает
        # profile_var и сбрасывает выбор пользователя. Комбобокс уже
        # показывает то, что выбрал пользователь.

    def _sync_filter_after_profile_change(self):
        """Согласовать фильтр источника со сменой профиля.

        Если фильтр указывал на конкретный профиль, а он сменился —
        сбрасываем на «Все дубли», иначе таблица показывает файлы
        прежнего профиля и кажется, что записи исчезли.
        """
        if not hasattr(self, "take_filter_var"):
            return
        flt = self._take_filter_code()
        if flt in ("all", "common"):
            return
        # фильтр был на конкретном профиле
        if flt != sp.get_active_profile():
            self.take_filter_var.set("Все дубли")
            try:
                self.take_filter_combo.current(0)
            except Exception:
                pass
            self._refresh_samples()

    def _new_profile(self):
        """Создать профиль: спросить имя."""
        from tkinter import simpledialog
        name = simpledialog.askstring(
            "Новый профиль", "Название клона голоса:",
            parent=self)
        if not name or not name.strip():
            return
        ref, msg = sp.create_profile(name)
        # новый профиль сразу становится активным — иначе он «создан»,
        # но reference собирается не в него
        sp.set_active_profile(sp._safe_name(name))
        self._refresh_profiles()
        self.profile_var.set(sp._safe_name(name))
        try:
            vals = ["（общий）"] + sp.list_profiles()
            self.profile_combo.current(
                vals.index(sp._safe_name(name))
                if sp._safe_name(name) in vals else 0)
        except Exception:
            pass
        self.profile_status.config(text=msg, fg=GOOD)
        # сразу начинаем сборку образца в новый профиль
        self._set_status_where(
            f"Профиль «{name}» создан. Запиши фразы и собери образец.", GOOD)

    def _delete_profile(self):
        """Удалить активный профиль."""
        from tkinter import messagebox
        name = sp.get_active_profile()
        if not name:
            self.profile_status.config(
                text="Выбран общий reference — удалять нечего", fg=WARN)
            return
        if not messagebox.askyesno(
                "Удалить профиль",
                f"Удалить профиль «{name}» вместе с его reference.wav?"):
            return
        import shutil
        try:
            shutil.rmtree(sp.profile_dir(name), ignore_errors=True)
        except Exception as exc:
            self.profile_status.config(text=f"Ошибка: {exc}", fg=BAD)
            return
        sp.set_active_profile("")
        self._refresh_profiles()
        self.profile_status.config(text=f"Профиль «{name}» удалён", fg=GOOD)

    def _import_reference(self):
        """Импортировать готовый reference.wav в активный профиль.

        Удобно, когда reference уже собран (например, остался от прежней
        сессии или сделан другой программой) — не нужно собирать заново.
        """
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Выбери reference.wav",
            filetypes=[("WAV audio", "*.wav"), ("Все файлы", "*.*")],
            parent=self)
        if not path or not os.path.exists(path):
            return

        # куда кладём
        active = sp.get_active_profile()
        if active:
            dst = sp.profile_reference(active)
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
            except Exception:
                pass
        else:
            dst = sp.output_paths()["reference"]

        try:
            import shutil
            shutil.copy2(path, dst)
        except Exception as exc:
            self._set_status_where(f"Не удалось скопировать: {exc}", BAD)
            return

        # проверяем, что файл читается
        try:
            info = sf.info(dst)
            dur = info.duration
        except Exception as exc:
            self._set_status_where(f"Файл не читается как WAV: {exc}", BAD)
            return

        where = f"профиль «{active}»" if active else "общий"
        self._set_status_where(
            f"Импортирован reference ({where}): {dur:.1f} c, "
            f"{info.samplerate} Гц", GOOD)
        self._update_ref_status()
        try:
            self._refresh_samples()
        except Exception:
            pass

    def _build_reference(self) -> bool:
        """Собрать reference.wav из записей.

        Если выбран профиль — пишем в его папку, иначе в общий reference.wav.
        """
        d = self._samples_dir()
        files = [os.path.join(d, f) for f in self._take_files()]
        if not files:
            self._set_status_where("Нет записей подсказок", BAD)
            return False
        active = sp.get_active_profile()
        if active:
            ref = sp.profile_reference(active)
            try:
                os.makedirs(os.path.dirname(ref), exist_ok=True)
            except Exception:
                pass
        else:
            ref = sp.output_paths()["reference"]
        res = core.build_reference(files, ref)
        if not res.get("ok"):
            self._set_status_where(
                f"Не удалось собрать образец: {res.get('reason', res.get('error', ''))}",
                BAD)
            return False
        self._update_ref_status()
        where = f"профиль «{active}»" if active else "общий"
        self._set_status_where(
            f"Образец готов ({where}): {res['duration']:.1f} c "
            f"из {res['count']} записей", GOOD)
        return True

    def _set_status_where(self, text: str, color: str):
        self.quick_status.config(text=text, fg=color)
        self.ref_status.config(text=text, fg=color)
        self.samples_status.config(text=text, fg=color)

    def _clone_all(self):
        """Запустить клонирование всех реплик."""
        try:
            ref = sp.active_reference()
        except Exception:
            ref = sp.output_paths()["reference"]
        if not os.path.exists(ref):
            self._set_status_where("Нет образца голоса — запиши фразы", BAD)
            return
        studio = self.studio
        if hasattr(studio, "_voice_all"):
            self._clone_progress_show("Клонирование голоса")
            self._clone_log_line("Запуск движка XTTS…")
            studio._voice_all()
            self._clone_was_running = True
            self._set_status_where("Клонирование запущено…", GOOD)
        else:
            self._set_status_where("Функция клонирования недоступна", BAD)

    def _on_take_check(self, _rid: str, _val: bool):
        """Отметка дубля изменилась — обновить счётчик и кнопку."""
        try:
            n = len(self.take_table.checked_ids())
        except Exception:
            n = 0
        self.pick_count.config(text=f"отмечено: {n}")
        self.btn_add_to_profile.config(
            state="normal" if n else "disabled")

    def _pick_all_takes(self):
        """Отметить все дубли."""
        try:
            self.take_table._sel_all_var.set(True)
        except Exception:
            pass

    def _pick_no_takes(self):
        """Снять все отметки."""
        try:
            self.take_table.clear_checked()
        except Exception:
            pass

    def _add_selected_to_profile(self):
        """Создать профиль (спросить имя) и клонировать из отмеченных дублей.

        Логика:
          1. Проверяем, что дубли отмечены.
          2. Спрашиваем название профиля.
          3. Создаём профиль, копируем туда отмеченные дубли.
          4. Собираем reference из копий.
          5. Запускаем клонирование.
        """
        try:
            picked = self.take_table.checked_ids()
        except Exception:
            picked = []
        if not picked:
            self._set_status_where("Сначала отметь дубли галочками", BAD)
            return

        from tkinter import simpledialog
        name = simpledialog.askstring(
            "Новый профиль",
            "Название клона голоса.\nИз отмеченных дублей будет собран "
            "образец и запущено клонирование.",
            parent=self)
        if not name or not name.strip():
            return

        ref, msg = sp.create_profile(name)
        if not ref:
            self._set_status_where(msg, BAD)
            return
        # сразу делаем профиль активным
        safe = sp._safe_name(name)
        sp.set_active_profile(safe)

        # откуда читаем дубли: полные пути из таблицы
        src_paths = getattr(self, "_take_paths", {}) or {}
        # куда копируем
        dst_dir = os.path.join(sp.profile_dir(safe), "takes")
        try:
            os.makedirs(dst_dir, exist_ok=True)
        except Exception as exc:
            self._set_status_where(f"Не создать папку профиля: {exc}", BAD)
            return

        import shutil
        copied: list[str] = []
        missing = 0
        for rid in picked:
            src = src_paths.get(rid)
            if not src or not os.path.exists(src):
                src = os.path.join(self._samples_dir(), rid)
            if not os.path.exists(src):
                missing += 1
                continue
            dst = os.path.join(dst_dir, os.path.basename(src))
            try:
                if os.path.abspath(src) != os.path.abspath(dst):
                    shutil.copy2(src, dst)
                copied.append(dst)
            except Exception:
                missing += 1

        if not copied:
            self._set_status_where(
                f"Файлы отмеченных дублей не найдены (пропущено: {missing})",
                BAD)
            return

        self._register_copied_takes(copied)
        self._refresh_profiles()

        # собираем reference профиля из копий
        self._set_status_where(
            f"Профиль «{safe}»: собираю образец из {len(copied)} дублей…",
            WARN)
        res = core.build_reference(copied, sp.profile_reference(safe))
        if not res.get("ok"):
            self._set_status_where(
                f"Не удалось собрать образец: "
                f"{res.get('reason', res.get('error', ''))}", BAD)
            return

        self._set_status_where(
            f"Образец профиля «{safe}» готов: {res['duration']:.1f} c "
            f"из {res['count']} записей. Запускаю клонирование…", GOOD)
        self._update_ref_status()
        try:
            self._refresh_samples()
        except Exception:
            pass

        # запускаем модель клонирования
        self._clone_all()

    def _register_copied_takes(self, copied: list[str]) -> None:
        """Добавить скопированные дубли в takes.json активного профиля."""
        active = sp.get_active_profile()
        meta_path = os.path.join(sp.profile_dir(active), "takes", "takes.json")
        meta = {}
        try:
            with open(meta_path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data.get("takes"), dict):
                meta = data["takes"]
        except Exception:
            pass

        for dst in copied:
            fname = os.path.basename(dst)
            if fname in meta:
                continue
            # prompt_index определяем по имени файла (p01_take_...wav)
            idx = None
            m = _TAKE_RE.match(fname)
            if m:
                idx = int(m.group(1)) - 1
            meta[fname] = {"prompt_index": idx,
                           "saved": time.strftime("%H%M%S"),
                           "copied_from": fname}

        try:
            os.makedirs(os.path.dirname(meta_path), exist_ok=True)
            with open(meta_path, "w", encoding="utf-8") as fh:
                json.dump({"takes": meta}, fh, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def _delete_selected_take(self):
        if not self._selected_take:
            return
        paths = getattr(self, "_take_paths", {}) or {}
        path = paths.get(self._selected_take)
        if not path:
            path = os.path.join(self._samples_dir(), self._selected_take)
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        # убираем запись из той папки, где файл лежал
        try:
            folder = os.path.dirname(path) if path else ""
            meta_path = os.path.join(folder, "takes.json")
            if os.path.exists(meta_path):
                with open(meta_path, encoding="utf-8") as fh:
                    data = json.load(fh)
                takes = data.get("takes") if isinstance(data, dict) else None
                if isinstance(takes, dict):
                    takes.pop(os.path.basename(path), None)
                    with open(meta_path, "w", encoding="utf-8") as fh:
                        json.dump({"takes": takes}, fh,
                                  ensure_ascii=False, indent=1)
        except Exception:
            pass
        self._selected_take = None
        for b in (self.btn_take_play, self.btn_take_cmp, self.btn_del_take):
            b.config(state="disabled")
        self._refresh_samples()
        self._update_ref_status()

    # ==================================================================
    # Отрисовка
    # ==================================================================
    def _draw_progress(self):
        if not hasattr(self, "progress"):
            return
        c = self.progress
        try:
            w = c.winfo_width()
            h = c.winfo_height()
            c.delete("all")
            if w <= 1:
                return
            c.create_rectangle(0, 0, w, h, fill=SURFACE_2, outline="")
            fill = int(w * max(0.0, min(1.0, self._progress_value)))
            if fill > 0:
                c.create_rectangle(0, 0, fill, h, fill=ACCENT, outline="")
        except tk.TclError:
            pass

    def _draw_clone_bar(self):
        """Полоса прогресса клонирования."""
        if not hasattr(self, "clone_bar"):
            return
        c = self.clone_bar
        try:
            w = c.winfo_width()
            h = c.winfo_height()
            c.delete("all")
            if w <= 1:
                return
            c.create_rectangle(0, 0, w, h, fill=SURFACE_1, outline="")
            fill = int(w * max(0.0, min(1.0, self._clone_value)))
            if fill > 0:
                c.create_rectangle(0, 0, fill, h, fill=GREEN, outline="")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Прогресс клонирования: показываем этапы, а не «запущено»
    # ------------------------------------------------------------------
    def _clone_progress_show(self, title: str):
        """Показать панель прогресса и сбросить её."""
        self.clone_box.pack(fill="x", pady=(SPACE_M, 0))
        self.clone_title.config(text=title)
        self.clone_stage.config(text="подготовка…")
        self.clone_count.config(text="")
        self._clone_value = 0.0
        self._draw_clone_bar()
        self.clone_log.configure(state="normal")
        self.clone_log.delete("1.0", "end")
        self.clone_log.configure(state="disabled")

    def _clone_log_line(self, text: str):
        """Добавить строку в журнал клонирования."""
        if not hasattr(self, "clone_log"):
            return
        try:
            self.clone_log.configure(state="normal")
            self.clone_log.insert("end", text.rstrip() + "\n")
            # держим не больше 200 строк
            if int(self.clone_log.index("end-1c").split(".")[0]) > 200:
                self.clone_log.delete("1.0", "3.0")
            self.clone_log.see("end")
            self.clone_log.configure(state="disabled")
        except tk.TclError:
            pass

    def _clone_progress_tick(self):
        """Опрос состояния задачи клонирования (главный поток).

        Studio._run_job кладёт строки в log_queue и обновляет task_panel.
        Здесь мы вытягиваем прогресс и показываем его в «Мой голос».
        """
        if not hasattr(self, "clone_box"):
            return
        studio = self.studio
        # панель задачи (может быть _StubPanel в новом UI)
        panel = getattr(studio, "_current_panel", None)
        if panel is not None:
            steps = getattr(panel, "_steps", None)
            if isinstance(steps, list):
                # шаги: [{"text":..., "status": "todo|doing|done|fail"}]
                for st in steps:
                    if not isinstance(st, dict):
                        continue
                    if st.get("status") == "doing":
                        self.clone_stage.config(text=st.get("text", ""))
                        break
            # прогресс по числу готовых фраз
            total = getattr(studio, "_job_total", 0) or 0
            done = getattr(studio, "_done_ids", None)
            if total and isinstance(done, list):
                self._clone_value = min(1.0, len(done) / float(total))
                self.clone_count.config(
                    text=f"Готово {len(done)} из {total}")
                self._draw_clone_bar()
        # идёт ли задача
        busy = bool(getattr(studio, "busy", False))
        if not busy and getattr(self, "_clone_was_running", False):
            self._clone_finish()
        self._clone_was_running = busy
        self.after(400, self._clone_progress_tick)

    def _clone_finish(self):
        """Задача клонирования завершена."""
        self._clone_value = 1.0
        self._draw_clone_bar()
        self.clone_stage.config(text="готово", fg=GOOD)
        panel = getattr(self.studio, "_current_panel", None)
        lines = getattr(panel, "lines", None) if panel is not None else None
        if isinstance(lines, list):
            for kind, text in lines[-8:]:
                self._clone_log_line(text)
        self._set_status_where("Клонирование завершено", GOOD)
        # обновляем списки
        try:
            self._refresh_samples()
        except Exception:
            pass

    def _draw_level(self, level: float):
        if not hasattr(self, "level_bar"):
            return
        c = self.level_bar
        try:
            w = c.winfo_width()
            h = c.winfo_height()
            c.delete("all")
            if w <= 1:
                return
            c.create_rectangle(0, 0, w, h, fill=SURFACE_2, outline="")
            fill = int(w * max(0.0, min(1.0, level)))
            if fill > 0:
                color = GOOD if level < 0.85 else BAD
                c.create_rectangle(0, 0, fill, h, fill=color, outline="")
        except tk.TclError:
            pass


# backward-compatible alias (старые вызовы могут использовать VoicesPage)
Records = VoicesPage
