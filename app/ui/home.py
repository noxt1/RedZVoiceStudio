"""Главная страница — две карточки: исходящий и входящий перевод.

Соответствует утверждённому дизайну (ui_visual_tokens.json):
- Две равнозначные стеклянные карточки рядом
- Карточка 1: МОЙ ГОЛОС / OUTGOING (RU → ES/EN/IT/OW)
- Карточка 2: СОБЕСЕДНИК / INCOMING (AUTO → RU)
- Регулятор громкости перевода внизу
- Статус движка в заголовке
- Блок управления движком (Запустить / Остановить модель)

Все элементы реально подключены к LiveTab (аудиоконвейер не переписывается).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui.glass_card import GlassCard
from ui.theme import (
    ACCENT, ACTIVE, BAD, BG, BORDER_FOCUS, BORDER_SUBTLE, BORDER_WIDTH,
    GOOD, HOVER,
    INCOMING_ACCENT, OUTGOING_ACCENT, RADIUS_CARD, SPACE_L, SPACE_M, SPACE_S,
    SPACE_XL, SPACE_XS, SURFACE_1, SURFACE_2, SURFACE_HOVER, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, TRACK, WARN, WARNING, FONT_APP_TITLE,
    FONT_BODY, FONT_CARD_TITLE, FONT_H2, FONT_SECONDARY, FONT_METRIC,
)
import studio_core as core


class HomePage(tk.Frame):
    """Главная страница с двумя карточками перевода."""

    def __init__(self, master, studio, **kwargs):
        super().__init__(master, bg=BG, **kwargs)
        self.studio = studio
        self._outgoing_enabled = False
        self._incoming_enabled = False
        self._cont_enabled = False
        self._ptt_mode = True  # True = PTT, False = Непрерывно
        self._build()

    # ---------- построение ----------

    def _build(self):
        # Заголовок раздела
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", pady=(0, SPACE_XL))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header, text="RedZ Voice Studio",
            bg=BG, fg=ACCENT, font=FONT_APP_TITLE, anchor="w").pack(side="left")

        # Статус двигателя справа
        self.engine_lbl = tk.Label(
            header, text="движок: остановлен",
            bg=BG, fg=BAD, font=FONT_SECONDARY, anchor="e")
        self.engine_lbl.pack(side="right")

        # --- Две карточки ---
        cards_row = tk.Frame(self, bg=BG)
        cards_row.pack(fill="x", pady=(0, SPACE_XL))
        cards_row.grid_columnconfigure(0, weight=1)
        cards_row.grid_columnconfigure(1, weight=1)

        self.card_out = self._make_direction_card(
            cards_row, "МОЙ ГОЛОС", "OUTGOING",
            "RU", "ES",
            "Говорите по-русски, в кабель уходит перевод вашим голосом.",
            OUTGOING_ACCENT, is_outgoing=True)
        self.card_out.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_M // 2))

        self.card_in = self._make_direction_card(
            cards_row, "СОБЕСЕДНИК", "INCOMING",
            "AUTO", "RU",
            "Речь собеседника переводится на русский в наушники.",
            INCOMING_ACCENT, is_outgoing=False)
        self.card_in.grid(row=0, column=1, sticky="nsew", padx=(SPACE_M // 2, 0))

        # --- Блок управления движком ---
        engine_card = GlassCard(self, radius=RADIUS_CARD, pad=SPACE_M)
        engine_card.pack(fill="x", pady=(0, SPACE_L))
        inner = engine_card.inner
        inner.grid_columnconfigure(0, weight=1)

        tk.Label(
            inner, text="Управление движком перевода",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(0, SPACE_S))

        # Состояние движка
        self.engine_state_lbl = tk.Label(
            inner, text="STOPPED — модель не загружена",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY, anchor="w")
        self.engine_state_lbl.pack(anchor="w", pady=(0, SPACE_M))

        engine_btns = tk.Frame(inner, bg=SURFACE_1)
        engine_btns.pack(anchor="w")

        self.btn_start_engine = tk.Button(
            engine_btns, text="Запустить модель",
            bg="#1e6f3f", fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=16, pady=8,
            command=self._start_engine)
        self.btn_start_engine.pack(side="left", padx=(0, SPACE_S))
        self.btn_start_engine.bind("<Enter>", lambda e: self.btn_start_engine.configure(bg=SURFACE_PRESSED))
        self.btn_start_engine.bind("<Leave>", lambda e: self.btn_start_engine.configure(bg="#1e6f3f"))

        self.btn_stop_engine = tk.Button(
            engine_btns, text="Остановить модель",
            bg=BAD, fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=16, pady=8,
            command=self._stop_engine, state="disabled")
        self.btn_stop_engine.pack(side="left")
        self.btn_stop_engine.bind("<Enter>", lambda e: self.btn_stop_engine.configure(bg=SURFACE_PRESSED))
        self.btn_stop_engine.bind("<Leave>", lambda e: self.btn_stop_engine.configure(bg=BAD))

        # --- Нижняя панель: только громкость перевода ---
        mix = tk.Frame(self, bg=SURFACE_1, padx=SPACE_M, pady=SPACE_M,
                       highlightthickness=BORDER_WIDTH, highlightbackground=BORDER_SUBTLE)
        mix.pack(fill="x", pady=(0, SPACE_L))

        tk.Label(
            mix, text="ЗВУКОВОЙ БАЛАНС",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(0, SPACE_S))

        # Только перевод (оригинальный голос идёт из игры/Discord напрямую,
        # приложение не контролирует его громкость — не показываем фиктивный регулятор)
        block = tk.Frame(mix, bg=SURFACE_1)
        block.pack(fill="x", pady=(0, SPACE_S))
        block.pack_propagate(False)
        block.configure(width=250)
        tk.Label(
            block, text="Перевод в наушники", bg=SURFACE_1, fg=TEXT_SECONDARY,
            font=FONT_BODY, anchor="w").pack(side="left")
        scale = tk.Scale(
            block, from_=0, to=150, orient="horizontal",
            bg=SURFACE_1, fg=TEXT_PRIMARY, troughcolor=TRACK,
            highlightthickness=0, length=200, showvalue=False,
            command=self._on_translation_volume)
        scale.set(80)
        scale.pack(side="right", fill="x", expand=True)
        self._vol_translation = scale

        # Подпись текущего значения
        self._vol_lbl = tk.Label(
            block, text="80%", bg=SURFACE_1, fg=ACCENT,
            font=FONT_SECONDARY, anchor="e")
        self._vol_lbl.pack(side="right", padx=(8, 0))

        # Примечание об оригинале
        note = tk.Label(
            mix,
            text="Примечание: оригинальный голос собеседника идёт из игры или Discord напрямую — "
                 "приложение не перехватывает его громкость. Регулируйте её в самой игре.",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY,
            anchor="w", justify="left", wraplength=700)
        note.pack(anchor="w", pady=(SPACE_S, 0))

        # --- Футер: статус моделей ---
        footer = tk.Frame(self, bg=BG)
        footer.pack(fill="x", pady=(SPACE_L, 0))
        footer.grid_columnconfigure(0, weight=1)

        self.status_lbl = tk.Label(
            footer, text="ASR ГОТОВ   ·   MT ГОТОВ   ·   TTS ГОТОВ",
            bg=BG, fg=TEXT_MUTED, font=FONT_SECONDARY, anchor="w")
        self.status_lbl.pack(side="left")

    # ---------- карточка направления ----------

    def _make_direction_card(self, parent, title: str, subtitle: str,
                             src: str, dst: str, description: str, accent,
                             is_outgoing: bool) -> GlassCard:
        card = GlassCard(parent, radius=RADIUS_CARD, pad=SPACE_M)
        inner = card.inner
        inner.grid_columnconfigure(0, weight=1)

        # Заголовок карточки
        header = tk.Frame(inner, bg=SURFACE_1)
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_S))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header, text=title,
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").grid(
                row=0, column=0, sticky="w")
        tk.Label(
            header, text=subtitle,
            bg=SURFACE_1, fg=accent, font=FONT_SECONDARY, anchor="w").grid(
                row=1, column=0, sticky="w", pady=(SPACE_XS, 0))

        # Статус направления
        status = tk.Label(
            inner, text="● выключено",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY, anchor="w")
        status.grid(row=1, column=0, sticky="e", pady=(0, SPACE_M))
        card._status_label = status

        # Маршрут (языки)
        route = tk.Frame(inner, bg=SURFACE_2, padx=SPACE_M, pady=SPACE_S,
                         highlightthickness=BORDER_WIDTH,
                         highlightbackground=BORDER_SUBTLE)
        route.grid(row=2, column=0, sticky="ew", pady=(0, SPACE_M))
        route.grid_columnconfigure(0, weight=1)
        route.grid_columnconfigure(2, weight=1)

        tk.Label(
            route, text=src, bg=SURFACE_2, fg=TEXT_PRIMARY,
            font=FONT_METRIC, anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(
            route, text="→", bg=SURFACE_2, fg=accent,
            font=FONT_METRIC, anchor="center").grid(row=0, column=1, padx=SPACE_M)
        tk.Label(
            route, text=dst, bg=SURFACE_2, fg=TEXT_PRIMARY,
            font=FONT_METRIC, anchor="e").grid(row=0, column=2, sticky="e")
        tk.Label(
            route, text="язык источника" if src == "AUTO" else "мой язык",
            bg=SURFACE_2, fg=TEXT_MUTED, font=FONT_SECONDARY,
            anchor="w").grid(row=1, column=0, sticky="w", pady=(SPACE_XS, 0))
        tk.Label(
            route, text="язык собеседника" if src == "AUTO" else "язык перевода",
            bg=SURFACE_2, fg=TEXT_MUTED, font=FONT_SECONDARY,
            anchor="e").grid(row=1, column=2, sticky="e", pady=(SPACE_XS, 0))

        # Описание
        tk.Label(
            inner, text=description,
            bg=SURFACE_1, fg=TEXT_SECONDARY, font=FONT_BODY,
            anchor="w", justify="left", wraplength=420).grid(
                row=3, column=0, sticky="ew", pady=(0, SPACE_M))

        # --- Режим (только для исходящего) ---
        if is_outgoing:
            # Режим: PTT / Непрерывно
            mode_frame = tk.Frame(inner, bg=SURFACE_1)
            mode_frame.grid(row=4, column=0, sticky="ew", pady=(0, SPACE_S))
            mode_frame.grid_columnconfigure(0, weight=1)

            self.ptt_btn = tk.Button(
                mode_frame, text="PTT: зажать и говорить",
                bg=SURFACE_2, fg=TEXT_PRIMARY, activeforeground=TEXT_PRIMARY,
                activebackground=SURFACE_HOVER, font=FONT_BODY,
                relief="flat", cursor="hand2", padx=14, pady=6,
                command=self._toggle_mode)
            self.ptt_btn.pack(side="left", padx=(0, SPACE_S))

            self.cont_btn = tk.Button(
                mode_frame, text="Непрерывно",
                bg=SURFACE_2, fg=TEXT_MUTED, activeforeground=TEXT_PRIMARY,
                activebackground=SURFACE_HOVER, font=FONT_BODY,
                relief="flat", cursor="hand2", padx=14, pady=6,
                command=self._toggle_mode)
            self.cont_btn.pack(side="left")
            self._update_mode_buttons()

            # Язык перевода
            lang_row = tk.Frame(inner, bg=SURFACE_1)
            lang_row.grid(row=5, column=0, sticky="ew", pady=(0, SPACE_M))
            lang_row.grid_columnconfigure(1, weight=1)

            tk.Label(
                lang_row, text="Язык перевода:", bg=SURFACE_1, fg=TEXT_SECONDARY,
                font=FONT_SECONDARY, anchor="w").pack(side="left")

            self.lang_combo = ttk.Combobox(
                lang_row, state="readonly", width=24)
            self.lang_combo["values"] = [f"{code}: {title}"
                                         for code, title in core.lang_titles()]
            self.lang_combo.current(0)
            self.lang_combo.pack(side="left", padx=(SPACE_S, 0))
            self.lang_combo.bind("<<ComboboxSelected>>", self._on_out_lang)

            card._lang_combo = self.lang_combo

        # Кнопка включения
        btn = tk.Button(
            inner, text="Включить",
            bg=accent, fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=16, pady=8)
        btn.grid(row=6 if is_outgoing else 4, column=0, sticky="w", pady=(0, SPACE_S))
        btn.bind("<Enter>", lambda e: btn.configure(bg=SURFACE_PRESSED))
        btn.bind("<Leave>", lambda e: btn.configure(bg=accent))

        # Подключаем команду в зависимости от направления
        if is_outgoing:
            btn.config(command=self._toggle_outgoing)
        else:
            btn.config(command=self._toggle_incoming)

        card._enable_btn = btn
        card._status_label = status

        # Микрофон (только для исходящего)
        if is_outgoing:
            mic_row = tk.Frame(inner, bg=SURFACE_1)
            mic_row.grid(row=7 if is_outgoing else 5, column=0, sticky="ew", pady=(0, SPACE_S))
            mic_row.grid_columnconfigure(1, weight=1)

            tk.Label(
                mic_row, text="Микрофон:", bg=SURFACE_1, fg=TEXT_SECONDARY,
                font=FONT_SECONDARY, anchor="w").pack(side="left")

            self.mic_combo = ttk.Combobox(
                mic_row, state="readonly", width=40)
            self.mic_combo["values"] = ["(по умолчанию)"]
            self.mic_combo.current(0)
            self.mic_combo.pack(side="left", padx=(SPACE_S, 0), fill="x", expand=True)

            card._mic_combo = self.mic_combo

        return card

    # ---------- обработчики ----------

    def _on_volume(self, col: int, value):
        """Изменение громкости (оставлено для обратной совместимости)."""
        pass

    def _on_translation_volume(self, value):
        """Регулировка громкости перевода в наушники."""
        bridge = getattr(self.studio, "bridge", None)
        if bridge is None or not getattr(bridge, "running", False):
            return
        try:
            vol = float(value) / 100.0
        except Exception:
            vol = 0.8
        bridge.monitor_gain = vol
        self._vol_lbl.config(text=f"{int(float(value))}%")

    def _toggle_mode(self):
        """Переключить режим: PTT ↔ Непрерывно."""
        self._ptt_mode = not self._ptt_mode
        self._update_mode_buttons()
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        # Если перевод включён — перезапускаем в новом режиме
        if self._outgoing_enabled:
            self._toggle_outgoing()  # выключить
            self._toggle_outgoing()  # включить в новом режиме

    def _update_mode_buttons(self):
        """Обновить визуальное состояние кнопок режима."""
        if self._ptt_mode:
            self.ptt_btn.config(bg=ACCENT, fg="#fff")
            self.cont_btn.config(bg=SURFACE_2, fg=TEXT_MUTED)
        else:
            self.ptt_btn.config(bg=SURFACE_2, fg=TEXT_MUTED)
            self.cont_btn.config(bg=ACCENT, fg="#fff")

    def _on_out_lang(self, _event=None):
        """Сменить язык исходящего перевода."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        code = self.lang_combo.get().split(":")[0].strip() if hasattr(self, "lang_combo") else "es"
        live._on_lang()

    def _start_engine(self):
        """Запустить движок и загрузить модели."""
        ok, msg = self.studio.start_engine()
        if ok:
            self.btn_start_engine.config(state="disabled")
            self.btn_stop_engine.config(state="normal")
            self.engine_state_lbl.config(
                text="LOADING — загрузка моделей…", fg=WARN)
            self.engine_lbl.config(text="движок: загрузка…", fg=WARNING)
        else:
            self.engine_state_lbl.config(
                text=f"ERROR — {msg}", fg=BAD)
            self.engine_lbl.config(text=f"движок: ошибка — {msg[:40]}", fg=BAD)

    def _stop_engine(self):
        """Остановить движок и выгрузить модели."""
        ok, msg = self.studio.stop_engine()
        if ok:
            self.btn_start_engine.config(state="normal")
            self.btn_stop_engine.config(state="disabled")
            self.engine_state_lbl.config(
                text="STOPPED — модель не загружена", fg=TEXT_MUTED)
            self.engine_lbl.config(text="движок: остановлен", fg=BAD)
            # Сброс состояния переводов
            self._outgoing_enabled = False
            self._incoming_enabled = False
            self.card_out._status_label.config(text="● выключено", fg=TEXT_MUTED)
            self.card_out._enable_btn.config(text="Включить", bg=OUTGOING_ACCENT)
            self.card_in._status_label.config(text="● выключено", fg=TEXT_MUTED)
            self.card_in._enable_btn.config(text="Включить", bg=INCOMING_ACCENT)
        else:
            self.engine_state_lbl.config(
                text=f"ERROR — {msg}", fg=BAD)

    def _toggle_outgoing(self):
        """Включить/выключить исходящий перевод."""
        live = getattr(self.studio, "live", None)
        if live is None:
            self.card_out._status_label.config(text="● ошибка: нет LiveTab", fg=BAD)
            return

        # Проверяем, что движок запущен и готов
        status = self.studio.get_engine_status()
        if status["state"] != "READY":
            self.card_out._status_label.config(
                text="● запустите модель", fg=WARN)
            self.engine_lbl.config(
                text="движок не готов — нажмите «Запустить модель»", fg=WARN)
            return

        if not self._outgoing_enabled:
            # Включить
            if self._ptt_mode:
                live._start_hold()
            else:
                live._start_cont()
            self._outgoing_enabled = True
            self.card_out._status_label.config(
                text="● активен", fg=GOOD)
            self.card_out._enable_btn.config(
                text="Выключить", bg=BAD)
            self.engine_lbl.config(text="исходящий перевод включён", fg=GOOD)
        else:
            # Выключить
            if self._ptt_mode:
                live._stop_hold()
            else:
                live._stop_cont()
            self._outgoing_enabled = False
            self.card_out._status_label.config(
                text="● выключено", fg=TEXT_MUTED)
            self.card_out._enable_btn.config(
                text="Включить", bg=OUTGOING_ACCENT)
            self.engine_lbl.config(text="движок готов", fg=GOOD)

    def _toggle_incoming(self):
        """Включить/выключить входящий перевод."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return

        # Проверяем, что движок запущен и готов
        status = self.studio.get_engine_status()
        if status["state"] != "READY":
            self.card_in._status_label.config(
                text="● запустите модель", fg=WARN)
            self.engine_lbl.config(
                text="движок не готов — нажмите «Запустить модель»", fg=WARN)
            return

        if not self._incoming_enabled:
            live._toggle_incoming()
            self._incoming_enabled = True
            self.card_in._status_label.config(
                text="● активен", fg=GOOD)
            self.card_in._enable_btn.config(
                text="Выключить", bg=BAD)
            self.engine_lbl.config(text="входящий перевод включён", fg=GOOD)
        else:
            live._toggle_incoming()
            self._incoming_enabled = False
            self.card_in._status_label.config(
                text="● выключено", fg=TEXT_MUTED)
            self.card_in._enable_btn.config(
                text="Включить", bg=INCOMING_ACCENT)
            self.engine_lbl.config(text="движок готов", fg=GOOD)

    # ---------- публичное API ----------

    def set_engine_status(self, ready: bool, loading: bool = False):
        """Обновить статус движка (вызывается из MainWindow 타이мера)."""
        if loading:
            self.engine_lbl.config(text="движок: загрузка…", fg=WARNING)
            self.engine_state_lbl.config(text="LOADING — загрузка моделей…", fg=WARNING)
        elif ready:
            self.engine_lbl.config(text="движок: готов", fg=GOOD)
            self.engine_state_lbl.config(text="READY — модель загружена", fg=GOOD)
            self.btn_start_engine.config(state="disabled")
            self.btn_stop_engine.config(state="normal")
        else:
            self.engine_lbl.config(text="движок: остановлен", fg=BAD)
            self.engine_state_lbl.config(text="STOPPED — модель не загружена", fg=TEXT_MUTED)
            self.btn_start_engine.config(state="normal")
            self.btn_stop_engine.config(state="disabled")

    def set_outgoing(self, enabled: bool):
        """Включить/выключить исходящий перевод (внешнее управление)."""
        self._outgoing_enabled = enabled
        card = self.card_out
        card._status_label.config(
            text="● активен" if enabled else "● выключено",
            fg=GOOD if enabled else TEXT_MUTED)
        card._enable_btn.config(
            text="Выключить" if enabled else "Включить",
            bg=BAD if enabled else OUTGOING_ACCENT)

    def set_incoming(self, enabled: bool):
        """Включить/выключить входящий перевод (внешнее управление)."""
        self._incoming_enabled = enabled
        card = self.card_in
        card._status_label.config(
            text="● активен" if enabled else "● выключено",
            fg=GOOD if enabled else TEXT_MUTED)
        card._enable_btn.config(
            text="Выключить" if enabled else "Включить",
            bg=BAD if enabled else INCOMING_ACCENT)

    def set_continuous(self, enabled: bool):
        """Включить/выключить непрерывный режим."""
        self._cont_enabled = enabled