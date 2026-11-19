"""Главная страница — две карточки перевода + управление движком + historia."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from ui.theme import (
    ACCENT, ACTIVE, BAD, BG, BORDER_SUBTLE, BORDER_WIDTH,
    GOOD, HOVER,
    INCOMING_ACCENT, OUTGOING_ACCENT, RADIUS_CARD, SPACE_L, SPACE_M, SPACE_S,
    SPACE_XL, SPACE_XS, SURFACE_1, SURFACE_2, SURFACE_HOVER, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, TRACK, WARN, WARNING, FONT_APP_TITLE,
    FONT_BODY, FONT_CARD_TITLE, FONT_H2, FONT_SECONDARY, FONT_METRIC,
)
import studio_core as core
import studio_paths as sp


class HomePage(tk.Frame):
    """Главная страница с двумя карточками перевода."""

    def __init__(self, master, studio, **kwargs):
        super().__init__(master, bg=BG, **kwargs)
        self.studio = studio
        self._outgoing_enabled = False
        self._incoming_enabled = False
        self._cont_enabled = False
        self._ptt_mode = True
        self._build()
        try:
            self.after(400, self._refresh_devices)
        except Exception:
            pass

    def _build(self):
        # --- Верхняя панель ---
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", pady=(0, SPACE_L))

        tk.Label(
            header, text="RedZ Voice Studio",
            bg=BG, fg="#ffffff", font=FONT_APP_TITLE, anchor="w").pack(side="left")

        eng_box = tk.Frame(header, bg=BG)
        eng_box.pack(side="right")

        self.engine_dot = tk.Label(
            eng_box, text="●", bg=BG, fg=BAD, font=("Segoe UI", 12, "bold"))
        self.engine_dot.pack(side="left", padx=(0, 4))
        self.engine_text = tk.Label(
            eng_box, text="Остановлен", bg=BG, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="e")
        self.engine_text.pack(side="left")

        # --- Две карточки ---
        cards_row = tk.Frame(self, bg=BG)
        cards_row.pack(fill="x", pady=(0, SPACE_L))
        cards_row.grid_columnconfigure(0, weight=1)
        cards_row.grid_columnconfigure(1, weight=1)

        self.card_out = self._make_card(
            cards_row, "МОЙ ГОЛОС", "Готов", OUTGOING_ACCENT,
            "Говорите по-русски, в кабель уходит перевод вашим голосом.",
            is_outgoing=True)
        self.card_out.grid(row=0, column=0, sticky="nsew",
                           padx=(0, SPACE_M // 2))

        self.card_in = self._make_card(
            cards_row, "СОБЕСЕДНИК", "Активно", INCOMING_ACCENT,
            "Речь собеседника переводится на русский в наушники.",
            is_outgoing=False)
        self.card_in.grid(row=0, column=1, sticky="nsew",
                          padx=(SPACE_M // 2, 0))

        # --- Блок управления движком ---
        engine_card = tk.Frame(self, bg=SURFACE_1, highlightthickness=0, bd=0)
        engine_card.pack(fill="x", pady=(0, SPACE_L))
        inner = engine_card

        tk.Label(
            inner, text="Управление моделью перевода",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(SPACE_S, SPACE_S))

        engine_row = tk.Frame(inner, bg=SURFACE_1)
        engine_row.pack(anchor="w", pady=(0, SPACE_M))

        self.engine_status_lbl = tk.Label(
            engine_row, text="Модель не загружена",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY, anchor="w")
        self.engine_status_lbl.pack(side="left", padx=(0, SPACE_M))

        self.btn_start_engine = tk.Button(
            engine_row, text="Запустить модель",
            bg="#1e6f3f", fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY, relief="flat",
            cursor="hand2", padx=16, pady=8, command=self._start_engine)
        self.btn_start_engine.pack(side="left", padx=(0, SPACE_S))

        self.btn_stop_engine = tk.Button(
            engine_row, text="Остановить модель",
            bg=BAD, fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY, relief="flat",
            cursor="hand2", padx=16, pady=8, command=self._stop_engine,
            state="disabled")
        self.btn_stop_engine.pack(side="left")

        # --- История переводов ---
        history_card = tk.Frame(self, bg=SURFACE_1, highlightthickness=0, bd=0)
        history_card.pack(fill="both", expand=True)
        inner2 = history_card

        tk.Label(
            inner2, text="Последние переводы",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(SPACE_S, SPACE_S))

        self.history_list = tk.Listbox(
            inner2, bg="#0f1216", fg=TEXT_PRIMARY, selectbackground=ACCENT,
            selectforeground="#ffffff", font=("Segoe UI", 10),
            borderwidth=0, highlightthickness=0, activestyle="none", height=7)
        self.history_list.pack(fill="both", expand=True, pady=(0, SPACE_S))

        footer_row = tk.Frame(inner2, bg=SURFACE_1)
        footer_row.pack(fill="x")
        tk.Button(
            footer_row, text="Все записи →",
            bg=SURFACE_2, fg=TEXT_PRIMARY,
            activeforeground=TEXT_PRIMARY, activebackground=SURFACE_HOVER,
            font=FONT_BODY, relief="flat", cursor="hand2", padx=12, pady=6,
            command=self._show_all_history).pack(side="right")

        # --- Нижний статус бар ---
        status_bar = tk.Frame(self, bg=SURFACE_1, height=34)
        status_bar.pack(fill="x", side="bottom", pady=(SPACE_L, 0))
        status_bar.pack_propagate(False)

        tk.Label(
            status_bar, text="Приложение готово",
            bg=SURFACE_1, fg=GOOD, font=FONT_SECONDARY, anchor="w").pack(
                side="left", padx=SPACE_M, pady=6)

        self.asr_dot = tk.Label(
            status_bar, text="●", bg=SURFACE_1, fg=TEXT_MUTED,
            font=("Segoe UI", 10, "bold"))
        self.asr_dot.pack(side="right", padx=(14, 3))
        tk.Label(status_bar, text="ASR", bg=SURFACE_1, fg=TEXT_MUTED,
                 font=FONT_SECONDARY).pack(side="right")

        self.mt_dot = tk.Label(
            status_bar, text="●", bg=SURFACE_1, fg=TEXT_MUTED,
            font=("Segoe UI", 10, "bold"))
        self.mt_dot.pack(side="right", padx=(14, 3))
        tk.Label(status_bar, text="MT", bg=SURFACE_1, fg=TEXT_MUTED,
                 font=FONT_SECONDARY).pack(side="right")

        self.tts_dot = tk.Label(
            status_bar, text="●", bg=SURFACE_1, fg=TEXT_MUTED,
            font=("Segoe UI", 10, "bold"))
        self.tts_dot.pack(side="right", padx=(14, 3))
        tk.Label(status_bar, text="TTS", bg=SURFACE_1, fg=TEXT_MUTED,
                 font=FONT_SECONDARY).pack(side="right")

    def _make_card(self, parent, title: str, status_text: str, accent,
                   description: str, is_outgoing: bool) -> tk.Frame:
        card = tk.Frame(parent, bg=SURFACE_1, highlightthickness=0, bd=0)
        inner = card
        inner.grid_columnconfigure(0, weight=1)

        header = tk.Frame(inner, bg=SURFACE_1)
        header.grid(row=0, column=0, sticky="ew", pady=(SPACE_S, SPACE_S))
        header.grid_columnconfigure(0, weight=1)

        icon = "🎤" if is_outgoing else "🔊"
        tk.Label(
            header, text=f"{icon}  {title}", bg=SURFACE_1, fg=TEXT_PRIMARY,
            font=FONT_CARD_TITLE, anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(
            header, text=status_text, bg=SURFACE_1, fg=accent,
            font=FONT_SECONDARY, anchor="e").grid(row=0, column=1, sticky="e")

        if is_outgoing:
            mic_row = tk.Frame(inner, bg=SURFACE_1)
            mic_row.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_S))
            mic_row.grid_columnconfigure(1, weight=1)
            tk.Label(
                mic_row, text="Микрофон:", bg=SURFACE_1, fg=TEXT_SECONDARY,
                font=FONT_SECONDARY).pack(side="left")
            self.out_mic_combo = ttk.Combobox(mic_row, state="readonly", width=28)
            self.out_mic_combo["values"] = ["Микрофон (Realtek Audio)"]
            self.out_mic_combo.current(0)
            self.out_mic_combo.pack(side="right")

            lang_row = tk.Frame(inner, bg=SURFACE_1)
            lang_row.grid(row=2, column=0, sticky="ew", pady=(0, SPACE_S))
            lang_row.grid_columnconfigure(1, weight=1)
            tk.Label(
                lang_row, text="Язык перевода:", bg=SURFACE_1, fg=TEXT_SECONDARY,
                font=FONT_SECONDARY).pack(side="left")
            self.out_lang_combo = ttk.Combobox(lang_row, state="readonly", width=28)
            # Заполняем сразу с кодами — иначе _on_lang_change получит
            # «Испанский» вместо «es» и ничего не применит.
            try:
                self.out_lang_combo["values"] = [
                    f"{code}: {title}" for code, title in core.lang_titles()]
            except Exception:
                self.out_lang_combo["values"] = ["es: Испанский"]
            self.out_lang_combo.current(0)
            self.out_lang_combo.pack(side="right")
            self.out_lang_combo.bind("<<ComboboxSelected>>", self._on_lang_change)

            # Устройство вывода (куда играет перевод)
            outdev_row = tk.Frame(inner, bg=SURFACE_1)
            outdev_row.grid(row=3, column=0, sticky="ew", pady=(0, SPACE_S))
            outdev_row.grid_columnconfigure(1, weight=1)
            tk.Label(
                outdev_row, text="Вывод (куда играет):", bg=SURFACE_1,
                fg=TEXT_SECONDARY, font=FONT_SECONDARY).pack(side="left")
            self.out_dev_combo = ttk.Combobox(outdev_row, state="readonly", width=28)
            self.out_dev_combo["values"] = ["(по умолчанию)"]
            self.out_dev_combo.current(0)
            self.out_dev_combo.pack(side="right")

            # Профиль клона: какой reference используется для озвучки
            # и живого перевода. Тот же выбор, что в «Голоса» — здесь он
            # под рукой, когда настраиваешь перевод.
            prof_row = tk.Frame(inner, bg=SURFACE_1)
            prof_row.grid(row=4, column=0, sticky="ew", pady=(0, SPACE_S))
            prof_row.grid_columnconfigure(1, weight=1)
            tk.Label(
                prof_row, text="Профиль клона:", bg=SURFACE_1,
                fg=TEXT_SECONDARY, font=FONT_SECONDARY).pack(side="left")
            self.home_profile_var = tk.StringVar(
                value=sp.get_active_profile() or "（общий）")
            self.home_profile_combo = ttk.Combobox(
                prof_row, state="readonly", width=28,
                textvariable=self.home_profile_var)
            self.home_profile_combo["values"] = ["（общий）"] + sp.list_profiles()
            self.home_profile_combo.pack(side="right")
            self.home_profile_combo.bind(
                "<<ComboboxSelected>>", self._on_home_profile_change)

            # подпись: какой профиль активен для клонирования
            self.home_profile_active_lbl = tk.Label(
                prof_row, text="", bg=SURFACE_1, fg=TEXT_MUTED,
                font=FONT_SECONDARY, anchor="w")
            self.home_profile_active_lbl.pack(side="left", padx=(SPACE_S, 0))
            self._update_home_profile_label()

            mode_frame = tk.Frame(inner, bg=SURFACE_1)
            mode_frame.grid(row=5, column=0, sticky="ew", pady=(0, SPACE_S))
            mode_frame.grid_columnconfigure(0, weight=1)

            self.ptt_btn = tk.Button(
                mode_frame, text="Push-to-Talk", bg=ACCENT, fg="#fff",
                activeforeground="#fff", activebackground=SURFACE_HOVER,
                font=FONT_BODY, relief="flat", cursor="hand2", padx=14, pady=6,
                command=self._toggle_mode)
            self.ptt_btn.pack(side="left", padx=(0, SPACE_S))

            self.cont_btn = tk.Button(
                mode_frame, text="Непрерывный режим", bg=SURFACE_2, fg=TEXT_MUTED,
                activeforeground=TEXT_PRIMARY, activebackground=SURFACE_HOVER,
                font=FONT_BODY, relief="flat", cursor="hand2", padx=14, pady=6,
                command=self._toggle_mode)
            self.cont_btn.pack(side="left")

            # Громкость в наушниках (что слышу я)
            vol_row = tk.Frame(inner, bg=SURFACE_1)
            vol_row.grid(row=6, column=0, sticky="ew", pady=(0, SPACE_XS))
            vol_row.grid_columnconfigure(1, weight=1)

            tk.Label(
                vol_row, text="🔊 Слышу в наушниках:", bg=SURFACE_1,
                fg=TEXT_SECONDARY, font=FONT_SECONDARY).pack(side="left")
            self._vol_scale = tk.Scale(
                vol_row, from_=0, to=150, orient="horizontal",
                bg=SURFACE_1, fg=TEXT_PRIMARY, troughcolor=TRACK,
                highlightthickness=0, length=110, showvalue=True,
                resolution=5, command=self._on_monitor_vol)
            self._vol_scale.set(80)
            self._vol_scale.pack(side="left", fill="x", expand=True,
                                 padx=(SPACE_S, 4))

            # Общая громкость в кабеле (что слышат они)
            vol2_row = tk.Frame(inner, bg=SURFACE_1)
            vol2_row.grid(row=7, column=0, sticky="ew", pady=(0, SPACE_XS))
            vol2_row.grid_columnconfigure(1, weight=1)

            tk.Label(
                vol2_row, text="📢 Слышат в кабеле:", bg=SURFACE_1,
                fg=TEXT_SECONDARY, font=FONT_SECONDARY).pack(side="left")
            self._out_vol_scale = tk.Scale(
                vol2_row, from_=0, to=150, orient="horizontal",
                bg=SURFACE_1, fg=TEXT_PRIMARY, troughcolor=TRACK,
                highlightthickness=0, length=110, showvalue=True,
                resolution=5, command=self._on_out_vol)
            self._out_vol_scale.set(100)
            self._out_vol_scale.pack(side="left", fill="x", expand=True,
                                     padx=(SPACE_S, 4))

            # Перевод относительно своей речи + заглушить русский
            vol3_row = tk.Frame(inner, bg=SURFACE_1)
            vol3_row.grid(row=8, column=0, sticky="ew", pady=(0, SPACE_S))
            vol3_row.grid_columnconfigure(1, weight=1)

            tk.Label(
                vol3_row, text="🎙 Перевод vs речь:", bg=SURFACE_1,
                fg=TEXT_SECONDARY, font=FONT_SECONDARY).pack(side="left")
            self._phrase_vol_scale = tk.Scale(
                vol3_row, from_=0, to=150, orient="horizontal",
                bg=SURFACE_1, fg=TEXT_PRIMARY, troughcolor=TRACK,
                highlightthickness=0, length=110, showvalue=True,
                resolution=5, command=self._on_phrase_vol)
            self._phrase_vol_scale.set(100)
            self._phrase_vol_scale.pack(side="left", fill="x", expand=True,
                                        padx=(SPACE_S, 4))
            self.out_duck_var = tk.BooleanVar(value=False)
            self.out_duck_cb = tk.Checkbutton(
                vol3_row, text="Заглушить русский",
                variable=self.out_duck_var, command=self._toggle_outgoing_duck,
                bg=SURFACE_1, fg=TEXT_SECONDARY, selectcolor=SURFACE_2,
                activebackground=SURFACE_1, activeforeground=TEXT_PRIMARY,
                font=FONT_SECONDARY, relief="flat", cursor="hand2")
            self.out_duck_cb.pack(side="left", padx=(SPACE_S, 0))

            # Живой индикатор уровня на выходе в кабель
            meter_row = tk.Frame(inner, bg=SURFACE_1)
            meter_row.grid(row=9, column=0, sticky="ew", pady=(0, SPACE_S))
            meter_row.grid_columnconfigure(1, weight=1)

            tk.Label(
                meter_row, text="Уровень в кабеле:", bg=SURFACE_1,
                fg=TEXT_SECONDARY, font=FONT_SECONDARY).pack(side="left")
            self._meter = tk.Canvas(
                meter_row, height=16, bg="#0f1216", highlightthickness=0,
                bd=0)
            self._meter.pack(side="left", fill="x", expand=True,
                             padx=(SPACE_S, 4))
            self._meter_val = tk.Label(
                meter_row, text="—", bg=SURFACE_1, fg=TEXT_MUTED,
                font=FONT_SECONDARY, anchor="e", width=8)
            self._meter_val.pack(side="left")
            self._meter_w = 100
            self.after(120, self._poll_level_meter)
        else:
            src_row = tk.Frame(inner, bg=SURFACE_1)
            src_row.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_S))
            src_row.grid_columnconfigure(1, weight=1)
            tk.Label(
                src_row, text="Источник речи:", bg=SURFACE_1, fg=TEXT_SECONDARY,
                font=FONT_SECONDARY).pack(side="left")
            self.in_src_combo = ttk.Combobox(src_row, state="readonly", width=28)
            self.in_src_combo["values"] = ["Игра / Discord"]
            self.in_src_combo.current(0)
            self.in_src_combo.pack(side="right")

            peer_row = tk.Frame(inner, bg=SURFACE_1)
            peer_row.grid(row=2, column=0, sticky="ew", pady=(0, SPACE_S))
            peer_row.grid_columnconfigure(1, weight=1)
            tk.Label(
                peer_row, text="Язык собеседника:", bg=SURFACE_1, fg=TEXT_SECONDARY,
                font=FONT_SECONDARY).pack(side="left")
            self.in_peer_lang_combo = ttk.Combobox(peer_row, state="readonly", width=28)
            try:
                self.in_peer_lang_combo["values"] = [
                    f"{code}: {title}" for code, title in core.peer_lang_titles()]
            except Exception:
                self.in_peer_lang_combo["values"] = ["auto: авто (определить самому)"]
            self.in_peer_lang_combo.current(0)
            self.in_peer_lang_combo.pack(side="right")
            self.in_peer_lang_combo.bind("<<ComboboxSelected>>",
                                         self._on_peer_lang_change)

            voice_row = tk.Frame(inner, bg=SURFACE_1)
            voice_row.grid(row=3, column=0, sticky="ew", pady=(0, SPACE_S))
            voice_row.grid_columnconfigure(1, weight=1)
            tk.Label(
                voice_row, text="Голос:", bg=SURFACE_1, fg=TEXT_SECONDARY,
                font=FONT_SECONDARY).pack(side="left")
            self.in_voice_combo = ttk.Combobox(voice_row, state="readonly", width=28)
            self.in_voice_combo["values"] = ["Maria (ES)"]
            self.in_voice_combo.current(0)
            self.in_voice_combo.pack(side="right")

        tk.Label(
            inner, text=description, bg=SURFACE_1, fg=TEXT_SECONDARY,
            font=FONT_BODY, anchor="w", justify="left", wraplength=420).grid(
                row=9 if is_outgoing else 5, column=0, sticky="ew",
                pady=(SPACE_M, SPACE_M))

        btn_text = "Говорить (PTT)" if is_outgoing else "Включить перевод"
        btn = tk.Button(
            inner, text=btn_text, bg=accent, fg="#fff",
            activeforeground="#fff", activebackground=ACTIVE,
            font=FONT_BODY, relief="flat", cursor="hand2", padx=16, pady=10)
        btn.grid(row=10 if is_outgoing else 6, column=0, sticky="ew",
                 pady=(SPACE_S, 0))
        btn.bind("<Enter>", lambda e: btn.configure(bg=SURFACE_HOVER))
        btn.bind("<Leave>", lambda e: btn.configure(bg=accent))

        if is_outgoing:
            # PTT: зажать и говорить (не toggle)
            btn.config(command=self._toggle_outgoing)
            btn.bind("<ButtonPress-1>", self._ptt_press)
            btn.bind("<ButtonRelease-1>", self._ptt_release)
            card._out_btn = btn
        else:
            btn.config(command=self._toggle_incoming)
            card._in_btn = btn

        card._enable_btn = btn

        # Галочка "Заглушить русский в кабеле" (только для входящего)
        if not is_outgoing:
            self.in_duck_var = tk.BooleanVar(value=False)
            self.in_duck_cb = tk.Checkbutton(
                inner, text="Заглушить русский в кабеле",
                variable=self.in_duck_var, command=self._toggle_incoming_duck,
                bg=SURFACE_1, fg=TEXT_SECONDARY, selectcolor=SURFACE_2,
                activebackground=SURFACE_1, activeforeground=TEXT_PRIMARY,
                font=FONT_SECONDARY, relief="flat", cursor="hand2")
            self.in_duck_cb.grid(row=7, column=0, sticky="w", pady=(SPACE_S, 0))
            card._in_duck_cb = self.in_duck_cb

        status_lbl = tk.Label(
            inner, text="● выключено", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w")
        status_lbl.grid(row=11 if is_outgoing else 8, column=0, sticky="w",
                        pady=(SPACE_S, 0))
        card._status_label = status_lbl

        return card

    # ---------- профиль клона ----------

    def _on_home_profile_change(self, _event=None):
        """Сменить активный профиль клона прямо с главной.

        Тот же эффект, что выбор в «Голоса»: меняется reference,
        который используется для озвучки и живого перевода.
        """
        choice = (self.home_profile_var.get() or "").strip()
        name = "" if choice in ("", "（общий）", "(общий)") else choice
        try:
            sp.set_active_profile(name)
        except Exception:
            pass
        self._update_home_profile_label()
        # синхронизируем выбор в «Голоса», если страница уже построена
        try:
            voices = None
            studio = getattr(self, "studio", None)
            if studio is not None:
                voices = getattr(studio, "voices_page", None)
            if voices is None:
                voices = getattr(self.winfo_toplevel(), "voices", None)
            if voices is not None and hasattr(voices, "profile_var"):
                voices.profile_var.set(name if name else "（общий）")
                try:
                    vals = ["（общий）"] + sp.list_profiles()
                    voices.profile_combo.current(
                        vals.index(name) if name in vals else 0)
                except Exception:
                    pass
                if hasattr(voices, "_update_ref_status"):
                    voices._update_ref_status()
                if hasattr(voices, "_sync_filter_after_profile_change"):
                    voices._sync_filter_after_profile_change()
        except Exception:
            pass

    def _update_home_profile_label(self):
        """Подпись: какой профиль активен для клонирования."""
        if not hasattr(self, "home_profile_active_lbl"):
            return
        active = sp.get_active_profile()
        if active:
            ref = sp.profile_reference(active)
            ok = os.path.exists(ref)
            self.home_profile_active_lbl.config(
                text=f"активен: «{active}»" + ("" if ok else " (нет reference)"),
                fg=GOOD if ok else WARN)
        else:
            self.home_profile_active_lbl.config(
                text="активен: общий", fg=TEXT_MUTED)

    def _refresh_profile_combo(self):
        """Обновить список профилей в комбобоксе главной."""
        if not hasattr(self, "home_profile_combo"):
            return
        values = ["（общий）"] + sp.list_profiles()
        self.home_profile_combo["values"] = values
        active = sp.get_active_profile()
        if active and active in values:
            self.home_profile_var.set(active)
            try:
                self.home_profile_combo.current(values.index(active))
            except Exception:
                pass
        elif not active:
            self.home_profile_var.set("（общий）")
            try:
                self.home_profile_combo.current(0)
            except Exception:
                pass
        self._update_home_profile_label()

    # ---------- устройства (синхронизация с LiveTab) ----------

    def _refresh_devices(self):
        """Заполнить комбобоксы реальными устройствами из LiveTab."""
        # список профилей обновляем всегда (не зависит от LiveTab)
        try:
            self._refresh_profile_combo()
        except Exception:
            pass
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        try:
            inputs = live.get_input_devices()
            outputs = live.get_output_devices()
        except Exception:
            return
        if not inputs or not outputs:
            # LiveTab ещё не опросил устройства — пробуем позже
            try:
                self.after(500, self._refresh_devices)
            except Exception:
                pass
            return

        # Микрофон
        self.out_mic_combo["values"] = [f"{i}: {n}" for i, n in inputs]
        if inputs:
            cur = live.get_selected_mic()
            for idx, (i, _n) in enumerate(inputs):
                if i == cur:
                    self.out_mic_combo.current(idx)
                    break
            else:
                self.out_mic_combo.current(0)

        # Устройство вывода (перевод в кабель / наушники)
        self.out_dev_combo["values"] = [f"{i}: {n}" for i, n in outputs]
        if outputs:
            cur = live.get_selected_out()
            for idx, (i, _n) in enumerate(outputs):
                if i == cur:
                    self.out_dev_combo.current(idx)
                    break
            else:
                self.out_dev_combo.current(0)

        # Язык перевода — из LiveTab
        try:
            values = list(live.lang_combo["values"])
            if values:
                self.out_lang_combo["values"] = values
                live.lang_combo.bind("<<ComboboxSelected>>",
                                     self._sync_lang_from_live)
                self.out_lang_combo.current(live.lang_combo.current() or 0)
        except Exception:
            pass

        # Язык собеседника — из LiveTab (коды) + названия из core
        try:
            if hasattr(live, "peer_lang_combo"):
                codes = list(live.peer_lang_combo["values"])
                titles = dict(core.peer_lang_titles())
                self.in_peer_lang_combo["values"] = [
                    f"{c}: {titles.get(c, c)}" for c in codes]
                cur = live.peer_lang_combo.current()
                if 0 <= cur < len(codes):
                    self.in_peer_lang_combo.current(cur)
                live.peer_lang_combo.bind("<<ComboboxSelected>>",
                                          self._sync_peer_lang_from_live)
        except Exception:
            pass

        # Привязываем обработчики
        self.out_mic_combo.bind("<<ComboboxSelected>>", self._on_mic_change)
        self.out_dev_combo.bind("<<ComboboxSelected>>", self._on_out_change)
        self.out_lang_combo.bind("<<ComboboxSelected>>", self._on_lang_change)

    def _on_mic_change(self, _event=None):
        """Микрофон выбран в новом UI — применяем в LiveTab."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        val = self.out_mic_combo.get()
        if not val:
            return
        try:
            idx = int(val.split(":")[0])
        except Exception:
            return
        live.set_mic_device(idx)
        self.studio.in_device = idx

    def _on_out_change(self, _event=None):
        """Устройство вывода выбрано — применяем в LiveTab."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        val = self.out_dev_combo.get()
        if not val:
            return
        try:
            idx = int(val.split(":")[0])
        except Exception:
            return
        live.set_out_device(idx)
        self.studio.out_device = idx

    def _on_lang_change(self, _event=None):
        """Язык перевода выбран в новом UI — применяем в LiveTab."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        val = self.out_lang_combo.get()
        if not val:
            return
        code = val.split(":")[0].strip()
        live.set_lang_code(code)

    def _on_peer_lang_change(self, _event=None):
        """Язык собеседника выбран в новом UI — применяем в LiveTab."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        val = self.in_peer_lang_combo.get()
        if not val:
            return
        code = val.split(":")[0].strip()
        if code == "авто":
            code = "auto"
        try:
            if hasattr(live, "peer_lang_combo"):
                codes = list(live.peer_lang_combo["values"])
                if code in codes:
                    live.peer_lang_combo.current(codes.index(code))
                else:
                    live.peer_lang_combo.set(code)
                live._on_peer_lang()
        except Exception:
            pass

    def _sync_lang_from_live(self, _event=None):
        """Язык изменён в LiveTab — обновляем комбобокс нового UI."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        try:
            cur = live.lang_combo.current()
            if cur >= 0:
                self.out_lang_combo.current(cur)
        except Exception:
            pass

    def _sync_peer_lang_from_live(self, _event=None):
        """Язык собеседника изменён в LiveTab — обновляем комбобокс."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        try:
            cur = live.peer_lang_combo.current()
            if cur >= 0:
                self.in_peer_lang_combo.current(cur)
        except Exception:
            pass

    def _toggle_mode(self):
        """Переключить режим: PTT ↔ Непрерывно."""
        self._ptt_mode = not self._ptt_mode
        if self._ptt_mode:
            self.ptt_btn.config(bg=ACCENT, fg="#fff")
            self.cont_btn.config(bg=SURFACE_2, fg=TEXT_MUTED)
            self.card_out._out_btn.config(text="🎤  Говорить (PTT)")
        else:
            self.ptt_btn.config(bg=SURFACE_2, fg=TEXT_MUTED)
            self.cont_btn.config(bg=ACCENT, fg="#fff")
            self.card_out._out_btn.config(text="▶  Говорить (непрерывно)")

        # Если перевод уже шёл — перезапускаем в новом режиме
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        if self._outgoing_enabled:
            live._stop_hold()
            live._stop_cont()
            self._outgoing_enabled = False
            if not self._ptt_mode:
                live._start_cont()
                self._outgoing_enabled = True
                self.card_out._status_label.config(text="● активно", fg=GOOD)

    def _toggle_outgoing(self):
        """Переключатель исходящего перевода (для непрерывного режима)."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return

        status = self.studio.get_engine_status()
        if status["state"] != "READY":
            self.card_out._status_label.config(
                text="● запустите модель", fg=WARN)
            return

        if not self._outgoing_enabled:
            live._start_cont()
            self._outgoing_enabled = True
            self.card_out._status_label.config(text="● активно", fg=GOOD)
        else:
            live._stop_cont()
            self._outgoing_enabled = False
            self.card_out._status_label.config(text="● выключено", fg=TEXT_MUTED)

    # ---------- PTT: зажать и говорить ----------

    def _ptt_press(self, _event=None):
        """Кнопка нажата.

        В режиме PTT — зажал и говоришь (перевод идёт, пока зажата кнопка).
        В непрерывном режиме — переключатель вкл/выкл.
        """
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        status = self.studio.get_engine_status()
        if status["state"] != "READY":
            self.card_out._status_label.config(
                text="● запустите модель", fg=WARN)
            return

        if not self._ptt_mode:
            # Непрерывный режим: кнопка — переключатель
            self._toggle_outgoing()
            return

        if self._outgoing_enabled:
            return
        live._start_hold()
        self._outgoing_enabled = True
        self.card_out._status_label.config(text="● говори…", fg=GOOD)

    def _ptt_release(self, _event=None):
        """Кнопка отпущена — в режиме PTT останавливаем перевод."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        if not self._ptt_mode:
            return  # в непрерывном режиме отпускание ничего не делает
        if not self._outgoing_enabled:
            return
        live._stop_hold()
        self._outgoing_enabled = False
        self.card_out._status_label.config(text="● выключено", fg=TEXT_MUTED)

    def _toggle_incoming(self):
        live = getattr(self.studio, "live", None)
        if live is None:
            return

        status = self.studio.get_engine_status()
        if status["state"] != "READY":
            self.card_in._status_label.config(
                text="● запустите модель", fg=WARN)
            return

        if not self._incoming_enabled:
            # Применяем язык собеседника перед запуском
            self._apply_peer_lang()
            ok, msg = live.start_capture()
            if not ok:
                self.card_in._status_label.config(
                    text=f"● ошибка: {msg[:40]}", fg=BAD)
                return
            try:
                live._toggle_incoming()
            except Exception as exc:
                live.stop_capture()
                self.card_in._status_label.config(
                    text=f"● ошибка: {str(exc)[:40]}", fg=BAD)
                return
            self._incoming_enabled = True
            self.card_in._status_label.config(text="● активно", fg=GOOD)
            self.card_in._in_btn.config(text="Выключить перевод", bg=BAD)
        else:
            live._toggle_incoming()
            live.stop_capture()
            self._incoming_enabled = False
            self.card_in._status_label.config(text="● выключено", fg=TEXT_MUTED)
            self.card_in._in_btn.config(text="Включить перевод", bg=INCOMING_ACCENT)

    def _apply_peer_lang(self):
        """Передать выбранный язык собеседника в LiveTab."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        val = self.in_peer_lang_combo.get()
        if not val:
            return
        code = val.split(":")[0].strip().lower()
        if code == "авто":
            code = "auto"
        try:
            if hasattr(live, "peer_lang_combo"):
                # ставим по коду, а не по тексту
                codes = list(live.peer_lang_combo["values"])
                if code in codes:
                    live.peer_lang_combo.current(codes.index(code))
                else:
                    live.peer_lang_combo.set(code)
                live._on_peer_lang()
        except Exception:
            pass

    def _toggle_incoming_duck(self):
        """Галочка «Заглушить русский в кабеле» для входящего перевода."""
        live = getattr(self.studio, "live", None)
        if live is None:
            self.in_duck_var.set(False)
            return
        flag = bool(self.in_duck_var.get())
        try:
            live._mute_ru = flag
            live._apply_mute()
        except Exception as exc:  # noqa: BLE001
            self.card_in._status_label.config(
                text=f"● ошибка: {str(exc)[:40]}", fg=BAD)
            return
        if flag:
            self.card_in._status_label.config(
                text="● русский заглушён в кабеле", fg=GOOD)

    def _poll_level_meter(self):
        """Живой индикатор уровня на выходе в кабель.

        Показывает, насколько громко сейчас звучит то, что уходит
        в игру/Discord — чтобы регулировка была наглядной.
        """
        try:
            bridge = getattr(self.studio, "bridge", None)
            peak = 0.0
            if bridge is not None and getattr(bridge, "running", False):
                try:
                    peak = float(bridge.status().get("out_peak", 0.0))
                except Exception:
                    peak = 0.0
            w = max(1, self._meter.winfo_width())
            self._meter.delete("all")
            # шкала
            self._meter.create_rectangle(
                0, 4, w, 12, fill="#1a1d24", outline="")
            # заполнение
            frac = min(1.0, max(0.0, peak))
            if frac > 0.001:
                col = "#55D6A2" if frac < 0.7 else (
                    "#E9BD72" if frac < 0.9 else "#F07878")
                self._meter.create_rectangle(
                    0, 4, int(w * frac), 12, fill=col, outline="")
            self._meter_val.config(
                text=f"{int(frac * 100)}%" if peak > 0.001 else "тишина")
        except Exception:
            pass
        try:
            self.after(120, self._poll_level_meter)
        except Exception:
            pass

    def _toggle_outgoing_duck(self):
        """Галочка «Заглушить русский в кабеле» для исходящего перевода.

        Единственный источник истины — LiveTab._mute_ru: его же читает
        _apply_mute(), который реально управляет мостом. Раньше галочка
        ставила bridge.set_duck() напрямую, а _restore_voice() после PTT
        перезаписывал её значением _mute_ru — и русский возвращался.
        """
        live = getattr(self.studio, "live", None)
        if live is None:
            self.out_duck_var.set(False)
            return
        flag = bool(self.out_duck_var.get())
        try:
            live._mute_ru = flag
            live._apply_mute()
        except Exception as exc:  # noqa: BLE001
            self.card_out._status_label.config(
                text=f"● ошибка: {str(exc)[:40]}", fg=BAD)
            return
        if flag:
            self.card_out._status_label.config(
                text="● русский заглушён в кабеле", fg=GOOD)
        else:
            self.card_out._status_label.config(
                text="● выключено", fg=TEXT_MUTED)

    def _on_monitor_vol(self, value=None):
        """Громкость перевода в наушники (что слышу я)."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        try:
            val = float(value)
        except Exception:
            val = float(self._vol_scale.get())
        try:
            live.monitor_vol.set(val)
        except Exception:
            pass
        # Применить к активному мосту
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            try:
                bridge.set_gains(monitor_gain=val / 100.0)
            except Exception:
                pass

    def _on_out_vol(self, value=None):
        """Общая громкость в кабеле (что слышат абоненты)."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        try:
            val = float(value)
        except Exception:
            val = float(self._out_vol_scale.get())
        try:
            live.bridge_out_vol.set(val)
        except Exception:
            pass
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            try:
                bridge.set_gains(out_gain=val / 100.0)
            except Exception:
                pass

    def _on_phrase_vol(self, value=None):
        """Громкость перевода относительно своей речи."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        try:
            val = float(value)
        except Exception:
            val = float(self._phrase_vol_scale.get())
        try:
            live.bridge_phrase_vol.set(val)
        except Exception:
            pass
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            try:
                bridge.set_gains(phrase_gain=val / 100.0)
            except Exception:
                pass

    def _start_engine(self):
        ok, msg = self.studio.start_engine()
        if ok:
            self.btn_start_engine.config(state="disabled")
            self.btn_stop_engine.config(state="normal")
            self.engine_dot.config(fg=GOOD)
            self.engine_text.config(text="Готов к работе", fg=GOOD)
            self.engine_status_lbl.config(text="Модели загружены", fg=GOOD)
        else:
            self.engine_status_lbl.config(text=f"Ошибка: {msg}", fg=BAD)

    def _stop_engine(self):
        ok, msg = self.studio.stop_engine()
        if ok:
            self.btn_start_engine.config(state="normal")
            self.btn_stop_engine.config(state="disabled")
            self.engine_dot.config(fg=BAD)
            self.engine_text.config(text="Остановлен", fg=BAD)
            self.engine_status_lbl.config(text="Модель не загружена", fg=TEXT_MUTED)
            self._outgoing_enabled = False
            self._incoming_enabled = False
            self.card_out._status_label.config(text="● выключено", fg=TEXT_MUTED)
            self.card_out._out_btn.config(text="Говорить (PTT)", bg=OUTGOING_ACCENT)
            self.card_in._status_label.config(text="● выключено", fg=TEXT_MUTED)
            self.card_in._in_btn.config(text="Включить перевод", bg=INCOMING_ACCENT)
        else:
            self.engine_status_lbl.config(text=f"Ошибка: {msg}", fg=BAD)

    def _show_all_history(self):
        pass

    def set_engine_status(self, ready: bool, loading: bool = False):
        if ready:
            self.engine_dot.config(fg=GOOD)
            self.engine_text.config(text="Готов к работе", fg=GOOD)
            self.engine_status_lbl.config(text="Модели загружены", fg=GOOD)
            self.btn_start_engine.config(state="disabled")
            self.btn_stop_engine.config(state="normal")
        elif loading:
            self.engine_dot.config(fg=WARNING)
            self.engine_text.config(text="Загрузка…", fg=WARNING)
            self.engine_status_lbl.config(text="Загрузка моделей…", fg=WARNING)
        else:
            self.engine_dot.config(fg=BAD)
            self.engine_text.config(text="Остановлен", fg=BAD)
            self.engine_status_lbl.config(text="Модель не загружена", fg=TEXT_MUTED)
            self.btn_start_engine.config(state="normal")
            self.btn_stop_engine.config(state="disabled")

    def add_history(self, entry: str):
        self.history_list.insert(0, entry)
        if self.history_list.size() > 100:
            self.history_list.delete(100)

    def set_outgoing(self, enabled: bool):
        self._outgoing_enabled = enabled

    def set_incoming(self, enabled: bool):
        self._incoming_enabled = enabled

    def set_continuous(self, enabled: bool):
        self._cont_enabled = enabled
