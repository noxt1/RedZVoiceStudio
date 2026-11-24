"""Страница «Настройки» — реальные параметры приложения.

Группы:
- Аудиоустройства: микрофон, выход, источник захвата, режим Legacy/WASAPI
- Языки: исходящий перевод, язык собеседника
- Горячие клавиши: текущие назначения, включение/выключение
- Engine и диагностика: состояние движка, модели, аудиоустройства, логи
- Сохранение: изменения применяются и сохраняются
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui.glass_card import GlassCard
from ui.theme import (
    ACCENT, ACTIVE, BAD, BG, BORDER_FOCUS, BORDER_SUBTLE, GOOD, HOVER,
    RADIUS_CARD, SPACE_L, SPACE_M, SPACE_S, SPACE_XL, SPACE_XS,
    SURFACE_1, SURFACE_2, SURFACE_HOVER, SURFACE_PRESSED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY,
    WARN, FONT_APP_TITLE, FONT_BODY, FONT_CARD_TITLE, FONT_H2, FONT_SECONDARY,
)


class SettingsPage(tk.Frame):
    """Страница настроек с реальными элементами управления."""

    def __init__(self, master, studio, **kwargs):
        super().__init__(master, bg=BG, **kwargs)
        self.studio = studio
        self._build()
        self._refresh_devices()
        self._refresh_engine()

    def _build(self):
        # Заголовок
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", pady=(0, SPACE_XL))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header, text="Настройки",
            bg=BG, fg=TEXT_PRIMARY, font=FONT_APP_TITLE, anchor="w").pack(
                side="left")

        # Контейнер для карточек настроек (две колонки)
        grid = tk.Frame(self, bg=BG)
        grid.pack(fill="both", expand=True)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)

        # --- Карточка: Аудиоустройства ---
        self._build_audio_card(grid, 0, 0)

        # --- Карточка: Языки ---
        self._build_lang_card(grid, 0, 1)

        # --- Карточка: Микрофон и мост ---
        self._build_bridge_card(grid, 1, 0)

        # --- Карточка: Оверлей и горячие клавиши ---
        self._build_overlay_card(grid, 1, 1)

        # --- Карточка: Engine и диагностика ---
        self._build_engine_card(grid, 2, 0)

        # --- Карточка: Горячие клавиши ---
        self._build_hotkey_card(grid, 2, 1)

    # ---------- карточка: Оверлей ----------

    def _build_overlay_card(self, parent, row, col):
        card = GlassCard(parent, radius=RADIUS_CARD, pad=SPACE_M)
        card.grid(row=row, column=col, sticky="nsew", padx=(0, SPACE_M // 2) if col == 0 else 0,
                  pady=SPACE_M)
        inner = card.inner
        inner.grid_columnconfigure(0, weight=1)

        tk.Label(
            inner, text="Оверлей (текст поверх игры)",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(0, SPACE_S))

        tk.Label(
            inner, text="Показывает распознанный русский и перевод поверх игры — "
                        "чтобы видеть, что именно ты сказал.",
            bg=SURFACE_1, fg=TEXT_SECONDARY, font=FONT_BODY,
            anchor="w", justify="left").pack(anchor="w", pady=(0, SPACE_M))

        self.overlay_var = tk.BooleanVar(value=False)
        self.overlay_cb = tk.Checkbutton(
            inner, text="Включить оверлей",
            variable=self.overlay_var, command=self._toggle_overlay,
            bg=SURFACE_1, fg=TEXT_SECONDARY, selectcolor=SURFACE_2,
            activebackground=SURFACE_1, activeforeground=TEXT_PRIMARY,
            font=FONT_SECONDARY, relief="flat", cursor="hand2")
        self.overlay_cb.pack(anchor="w", pady=(0, SPACE_S))

        self.overlay_status = tk.Label(
            inner, text="оверлей выключен", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w")
        self.overlay_status.pack(anchor="w", pady=(0, SPACE_M))

    def _toggle_overlay(self):
        """Включить/выключить оверлей с текстом поверх игры."""
        on = bool(self.overlay_var.get())
        try:
            status = self.studio.toggle_overlay(on)
        except Exception as exc:  # noqa: BLE001
            status = f"ошибка: {exc}"
        self.overlay_status.config(text=status, fg=GOOD if on else TEXT_MUTED)
        if not on:
            self.overlay_var.set(False)
        # Синхронизируем с LiveTab
        live = getattr(self.studio, "live", None)
        if live is not None:
            try:
                live.overlay_on.set(on)
            except Exception:
                pass

    # ---------- карточка: Аудиоустройства ----------

    def _build_audio_card(self, parent, row, col):
        card = GlassCard(parent, radius=RADIUS_CARD, pad=SPACE_M)
        card.grid(row=row, column=col, sticky="nsew", padx=(0, SPACE_M // 2) if col == 0 else 0,
                  pady=SPACE_M)
        inner = card.inner
        inner.grid_columnconfigure(0, weight=1)

        tk.Label(
            inner, text="Аудиоустройства",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(0, SPACE_S))

        # Микрофон
        mic_row = tk.Frame(inner, bg=SURFACE_1)
        mic_row.pack(fill="x", pady=(0, SPACE_S))
        mic_row.grid_columnconfigure(1, weight=1)
        tk.Label(
            mic_row, text="Микрофон:", bg=SURFACE_1, fg=TEXT_SECONDARY,
            font=FONT_SECONDARY, anchor="w").pack(side="left")
        self.mic_combo = ttk.Combobox(mic_row, state="readonly", width=40)
        self.mic_combo.pack(side="left", padx=(SPACE_S, 0), fill="x", expand=True)

        # Устройство вывода
        out_row = tk.Frame(inner, bg=SURFACE_1)
        out_row.pack(fill="x", pady=(0, SPACE_S))
        out_row.grid_columnconfigure(1, weight=1)
        tk.Label(
            out_row, text="Вывод (перевод в кабель):", bg=SURFACE_1, fg=TEXT_SECONDARY,
            font=FONT_SECONDARY, anchor="w").pack(side="left")
        self.out_combo = ttk.Combobox(out_row, state="readonly", width=40)
        self.out_combo.pack(side="left", padx=(SPACE_S, 0), fill="x", expand=True)

        # Источник захвата собеседника
        cap_row = tk.Frame(inner, bg=SURFACE_1)
        cap_row.pack(fill="x", pady=(0, SPACE_S))
        cap_row.grid_columnconfigure(1, weight=1)
        tk.Label(
            cap_row, text="Захват голоса собеседника:", bg=SURFACE_1, fg=TEXT_SECONDARY,
            font=FONT_SECONDARY, anchor="w").pack(side="left")
        self.capture_combo = ttk.Combobox(cap_row, state="readonly", width=40)
        self.capture_combo.pack(side="left", padx=(SPACE_S, 0), fill="x", expand=True)

        # Режим захвата
        mode_row = tk.Frame(inner, bg=SURFACE_1)
        mode_row.pack(fill="x", pady=(0, SPACE_S))
        mode_row.grid_columnconfigure(1, weight=1)
        tk.Label(
            mode_row, text="Режим захвата:", bg=SURFACE_1, fg=TEXT_SECONDARY,
            font=FONT_SECONDARY, anchor="w").pack(side="left")
        self.capture_mode_var = tk.StringVar(value="Legacy Input")
        self.capture_mode_combo = ttk.Combobox(
            mode_row, state="readonly", width=20,
            textvariable=self.capture_mode_var)
        self.capture_mode_combo["values"] = ["Legacy Input (Stereo Mix / CABLE Output)",
                                            "WASAPI Endpoint Loopback"]
        self.capture_mode_combo.pack(side="left", padx=(SPACE_S, 0))
        self.capture_mode_combo.bind("<<ComboboxSelected>>", self._on_capture_mode_change)

        # Мост
        bridge_row = tk.Frame(inner, bg=SURFACE_1)
        bridge_row.pack(fill="x", pady=(0, SPACE_S))
        self.bridge_btn = tk.Button(
            bridge_row, text="▶ Включить мост",
            bg="#1e6f3f", fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=14, pady=6,
            command=self._toggle_bridge)
        self.bridge_btn.pack(side="left")
        self.bridge_btn.bind("<Enter>", lambda e: self.bridge_btn.configure(bg=SURFACE_PRESSED))
        self.bridge_btn.bind("<Leave>", lambda e: self.bridge_btn.configure(bg="#1e6f3f"))

        self.bridge_status = tk.Label(
            inner, text="мост выключен", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w")
        self.bridge_status.pack(anchor="w", pady=(SPACE_S, SPACE_M))

        # Диагностика
        diag_row = tk.Frame(inner, bg=SURFACE_1)
        diag_row.pack(fill="x", pady=(0, SPACE_S))
        tk.Button(
            diag_row, text="🔍 Диагностика устройств",
            bg=SURFACE_2, fg=TEXT_PRIMARY, activeforeground=TEXT_PRIMARY,
            activebackground=SURFACE_PRESSED, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=14, pady=6,
            command=self._diag_devices).pack(side="left", padx=(0, SPACE_S))
        tk.Button(
            diag_row, text="🔄 Обновить списки",
            bg=SURFACE_2, fg=TEXT_PRIMARY, activeforeground=TEXT_PRIMARY,
            activebackground=SURFACE_PRESSED, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=14, pady=6,
            command=self._refresh_devices).pack(side="left")

    def _build_bridge_card(self, parent, row, col):
        card = GlassCard(parent, radius=RADIUS_CARD, pad=SPACE_M)
        card.grid(row=row, column=col, sticky="nsew", padx=(0, SPACE_M // 2) if col == 0 else 0,
                  pady=SPACE_M)
        inner = card.inner
        inner.grid_columnconfigure(0, weight=1)

        tk.Label(
            inner, text="Микрофон и мост (вещание в игру / Discord)",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(0, SPACE_S))

        # Выбор микрофона
        mic_row = tk.Frame(inner, bg=SURFACE_1)
        mic_row.pack(fill="x", pady=(0, SPACE_S))
        mic_row.grid_columnconfigure(1, weight=1)
        tk.Label(
            mic_row, text="Микрофон:", bg=SURFACE_1, fg=TEXT_SECONDARY,
            font=FONT_SECONDARY, anchor="w").pack(side="left")
        self.bridge_mic_combo = ttk.Combobox(mic_row, state="readonly", width=34)
        self.bridge_mic_combo.pack(side="left", padx=(SPACE_S, 0), fill="x", expand=True)

        # Выбор устройства вывода (виртуальный кабель / наушники)
        out_row = tk.Frame(inner, bg=SURFACE_1)
        out_row.pack(fill="x", pady=(0, SPACE_S))
        out_row.grid_columnconfigure(1, weight=1)
        tk.Label(
            out_row, text="Вывод (кабель в игру):", bg=SURFACE_1, fg=TEXT_SECONDARY,
            font=FONT_SECONDARY, anchor="w").pack(side="left")
        self.bridge_out_combo = ttk.Combobox(out_row, state="readonly", width=34)
        self.bridge_out_combo.pack(side="left", padx=(SPACE_S, 0), fill="x", expand=True)

        # Кнопки: авто-настройка маршрута + мост + проверка
        btn_row = tk.Frame(inner, bg=SURFACE_1)
        btn_row.pack(fill="x", pady=(SPACE_S, SPACE_M))
        self.auto_cable_btn = tk.Button(
            btn_row, text="⚡ Настроить под кабель",
            bg="#1e6f3f", fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY, relief="flat",
            cursor="hand2", padx=14, pady=6, command=self._auto_setup_cable)
        self.auto_cable_btn.pack(side="left", padx=(0, SPACE_S))
        self.bridge_btn = tk.Button(
            btn_row, text="▶ Включить мост",
            bg=SURFACE_2, fg=TEXT_PRIMARY, activeforeground=TEXT_PRIMARY,
            activebackground=SURFACE_PRESSED, font=FONT_BODY, relief="flat",
            cursor="hand2", padx=14, pady=6, command=self._toggle_bridge)
        self.bridge_btn.pack(side="left", padx=(0, SPACE_S))
        tk.Button(
            btn_row, text="◎ Проверить мост",
            bg=SURFACE_2, fg=TEXT_PRIMARY, activeforeground=TEXT_PRIMARY,
            activebackground=SURFACE_PRESSED, font=FONT_BODY, relief="flat",
            cursor="hand2", padx=14, pady=6,
            command=self._check_bridge).pack(side="left")

        self.bridge_status = tk.Label(
            inner, text="мост выключен", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w")
        self.bridge_status.pack(anchor="w", pady=(0, SPACE_M))

        # Галочка: заглушить русский в кабеле
        duck_row = tk.Frame(inner, bg=SURFACE_1)
        duck_row.pack(fill="x", pady=(0, SPACE_M))
        self.duck_var = tk.BooleanVar(value=False)
        self.duck_cb = tk.Checkbutton(
            duck_row, text="Заглушить русский в кабеле (только перевод)",
            variable=self.duck_var, command=self._toggle_duck,
            bg=SURFACE_1, fg=TEXT_SECONDARY, selectcolor=SURFACE_2,
            activebackground=SURFACE_1, activeforeground=TEXT_PRIMARY,
            font=FONT_SECONDARY, relief="flat", cursor="hand2")
        self.duck_cb.pack(side="left")
        tk.Label(
            duck_row, text="— русский голос не идёт в кабель, слышен только перевод",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY, anchor="w").pack(
                side="left", padx=(SPACE_S, 0))

        note = tk.Label(
            inner,
            text="В игре или Discorde выбери микрофоном устройство вывода (CABLE Output / "
                 "мост RedZ), чтобы слышали и твою речь, и перевод.",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY,
            anchor="w", justify="left")
        note.pack(anchor="w", pady=(SPACE_M, 0))

    # ---------- карточка: Языки ----------

    def _build_lang_card(self, parent, row, col):
        card = GlassCard(parent, radius=RADIUS_CARD, pad=SPACE_M)
        card.grid(row=row, column=col, sticky="nsew", padx=(SPACE_M // 2, 0) if col == 1 else 0,
                  pady=SPACE_M)
        inner = card.inner
        inner.grid_columnconfigure(0, weight=1)

        tk.Label(
            inner, text="Языки перевода",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(0, SPACE_S))

        # Исходящий язык
        out_lang_row = tk.Frame(inner, bg=SURFACE_1)
        out_lang_row.pack(fill="x", pady=(0, SPACE_S))
        out_lang_row.grid_columnconfigure(1, weight=1)
        tk.Label(
            out_lang_row, text="Исходящий (RU →):", bg=SURFACE_1, fg=TEXT_SECONDARY,
            font=FONT_SECONDARY, anchor="w").pack(side="left")
        self.out_lang_combo = ttk.Combobox(out_lang_row, state="readonly", width=30)
        self.out_lang_combo["values"] = ["es: Испанский", "en: Английский",
                                          "ow: Old West", "it: Итальянский"]
        self.out_lang_combo.current(0)
        self.out_lang_combo.pack(side="left", padx=(SPACE_S, 0), fill="x", expand=True)
        self.out_lang_combo.bind("<<ComboboxSelected>>", self._on_out_lang)

        # Язык собеседника
        peer_lang_row = tk.Frame(inner, bg=SURFACE_1)
        peer_lang_row.pack(fill="x", pady=(0, SPACE_S))
        peer_lang_row.grid_columnconfigure(1, weight=1)
        tk.Label(
            peer_lang_row, text="Язык собеседника:", bg=SURFACE_1, fg=TEXT_SECONDARY,
            font=FONT_SECONDARY, anchor="w").pack(side="left")
        self.peer_lang_combo = ttk.Combobox(peer_lang_row, state="readonly", width=30)
        self.peer_lang_combo["values"] = ["авто", "es: Испанский", "en: Английский", "it: Итальянский"]
        self.peer_lang_combo.current(0)
        self.peer_lang_combo.pack(side="left", padx=(SPACE_S, 0), fill="x", expand=True)

        # Примечание
        note = tk.Label(
            inner,
            text="Итальянский переводится цепочкой RU → ES → IT (прямой модели RU → IT нет).\n"
                 "Old West — английский перевод со 스타лем Дикого Запада (словарная замена).",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY,
            anchor="w", justify="left")
        note.pack(anchor="w", pady=(SPACE_S, SPACE_M))

    # ---------- карточка: Горячие клавиши ----------

    def _build_hotkey_card(self, parent, row, col):
        card = GlassCard(parent, radius=RADIUS_CARD, pad=SPACE_M)
        card.grid(row=row, column=col, sticky="nsew", padx=(0, SPACE_M // 2) if col == 0 else 0,
                  pady=SPACE_M)
        inner = card.inner
        inner.grid_columnconfigure(0, weight=1)

        tk.Label(
            inner, text="Горячие клавиши",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(0, SPACE_S))

        # Текущие назначения + кнопки «изменить»
        hk_row1 = tk.Frame(inner, bg=SURFACE_1)
        hk_row1.pack(fill="x", pady=(0, SPACE_XS))
        self.hk_talk_lbl = tk.Label(
            hk_row1, text="Говорить (зажать): загружается…",
            bg=SURFACE_1, fg=TEXT_SECONDARY, font=FONT_SECONDARY, anchor="w")
        self.hk_talk_lbl.pack(side="left")
        self.hk_talk_btn = tk.Button(
            hk_row1, text="изменить", bg=SURFACE_2, fg=TEXT_PRIMARY,
            activeforeground=TEXT_PRIMARY, activebackground=SURFACE_PRESSED,
            font=FONT_SECONDARY, relief="flat", cursor="hand2", padx=10, pady=3,
            command=lambda: self._capture_hotkey("live:talk"))
        self.hk_talk_btn.pack(side="right")

        hk_row2 = tk.Frame(inner, bg=SURFACE_1)
        hk_row2.pack(fill="x", pady=(0, SPACE_M))
        self.hk_cont_lbl = tk.Label(
            hk_row2, text="Непрерывно: загружается…",
            bg=SURFACE_1, fg=TEXT_SECONDARY, font=FONT_SECONDARY, anchor="w")
        self.hk_cont_lbl.pack(side="left")
        self.hk_cont_btn = tk.Button(
            hk_row2, text="изменить", bg=SURFACE_2, fg=TEXT_PRIMARY,
            activeforeground=TEXT_PRIMARY, activebackground=SURFACE_PRESSED,
            font=FONT_SECONDARY, relief="flat", cursor="hand2", padx=10, pady=3,
            command=lambda: self._capture_hotkey("live:cont"))
        self.hk_cont_btn.pack(side="right")

        # Включение/выключение
        hk_btn_row = tk.Frame(inner, bg=SURFACE_1)
        hk_btn_row.pack(fill="x", pady=(0, SPACE_S))
        self.hk_enable_btn = tk.Button(
            hk_btn_row, text="⌨ Включить горячие клавиши",
            bg="#1e6f3f", fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=14, pady=6,
            command=self._toggle_hotkeys)
        self.hk_enable_btn.pack(side="left")
        self.hk_enable_btn.bind("<Enter>", lambda e: self.hk_enable_btn.configure(bg=SURFACE_PRESSED))
        self.hk_enable_btn.bind("<Leave>", lambda e: self.hk_enable_btn.configure(bg="#1e6f3f"))

        self.hk_status = tk.Label(
            inner, text="горячие клавиши выключены", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w")
        self.hk_status.pack(anchor="w", pady=(SPACE_S, SPACE_M))

        note = tk.Label(
            inner,
            text="Горячие клавиши работают, когда приложение свёрнуто и игра в фокусе.\n"
                 "Нажми «изменить» и нажми новую комбинацию — Esc отменяет.",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY,
            anchor="w", justify="left")
        note.pack(anchor="w", pady=(0, SPACE_M))

    def _capture_hotkey(self, action: str):
        """Захватить новую комбинацию клавиш для действия."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        self.hk_status.config(text="нажми комбинацию… (Esc — отмена)", fg=WARN)
        self._hk_capture_action = action

        def _on_key(event):
            self.root.unbind("<Key>", _on_key)
            key = event.keysym
            if key == "Escape":
                self.hk_status.config(text="назначение отменено", fg=TEXT_MUTED)
                return
            if key in ("Control_L", "Control_R", "Alt_L", "Alt_R",
                       "Shift_L", "Shift_R", "Super_L", "Super_R"):
                return  # ждём обычную клавишу
            mods = []
            if event.state & 0x0004:
                mods.append("ctrl")
            if event.state & 0x0001:
                mods.append("shift")
            if event.state & 0x20000:
                mods.append("alt")
            combo = "+".join(mods + [key.lower()])
            try:
                live._hotkeys[action] = combo
                live._save_hotkeys()
                self._refresh_hotkey_labels()
                self.hk_status.config(text=f"назначено: {combo}", fg=GOOD)
            except Exception as exc:
                self.hk_status.config(text=f"не удалось: {exc}", fg=BAD)

        self.root.bind("<Key>", _on_key)

    # ---------- карточка: Engine и диагностика ----------

    def _build_engine_card(self, parent, row, col):
        card = GlassCard(parent, radius=RADIUS_CARD, pad=SPACE_M)
        card.grid(row=row, column=col, sticky="nsew", padx=(SPACE_M // 2, 0) if col == 1 else 0,
                  pady=SPACE_M)
        inner = card.inner
        inner.grid_columnconfigure(0, weight=1)

        tk.Label(
            inner, text="Движок и диагностика",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(0, SPACE_S))

        self.engine_status_lbl = tk.Label(
            inner, text="движок: не запущен",
            bg=SURFACE_1, fg=BAD, font=FONT_SECONDARY, anchor="w")
        self.engine_status_lbl.pack(anchor="w", pady=(0, SPACE_XS))

        self.models_status_lbl = tk.Label(
            inner, text="модели: не загружены",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY, anchor="w")
        self.models_status_lbl.pack(anchor="w", pady=(0, SPACE_XS))

        self.devices_status_lbl = tk.Label(
            inner, text="устройства: не проверены",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY, anchor="w")
        self.devices_status_lbl.pack(anchor="w", pady=(0, SPACE_XS))

        # Живое состояние: хоткеи и мост (пользователь должен видеть, что включено)
        hk_row = tk.Frame(inner, bg=SURFACE_1)
        hk_row.pack(fill="x", pady=(0, SPACE_XS))
        self.hotkeys_state_lbl = tk.Label(
            hk_row, text="хоткеи: проверяю…",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY, anchor="w")
        self.hotkeys_state_lbl.pack(side="left")
        self.hk_toggle_btn = tk.Button(
            hk_row, text="Выключить", bg=SURFACE_2, fg=TEXT_PRIMARY,
            activeforeground=TEXT_PRIMARY, activebackground=SURFACE_PRESSED,
            font=FONT_SECONDARY, relief="flat", cursor="hand2", padx=10, pady=3,
            command=self._toggle_hotkeys_from_settings)
        self.hk_toggle_btn.pack(side="right")

        br_row = tk.Frame(inner, bg=SURFACE_1)
        br_row.pack(fill="x", pady=(0, SPACE_M))
        self.bridge_state_lbl = tk.Label(
            br_row, text="мост: проверяю…",
            bg=SURFACE_1, fg=TEXT_MUTED, font=FONT_SECONDARY, anchor="w")
        self.bridge_state_lbl.pack(side="left")
        self.bridge_toggle_btn = tk.Button(
            br_row, text="Включить", bg=SURFACE_2, fg=TEXT_PRIMARY,
            activeforeground=TEXT_PRIMARY, activebackground=SURFACE_PRESSED,
            font=FONT_SECONDARY, relief="flat", cursor="hand2", padx=10, pady=3,
            command=self._toggle_bridge_from_settings)
        self.bridge_toggle_btn.pack(side="right")

        btn_row = tk.Frame(inner, bg=SURFACE_1)
        btn_row.pack(fill="x", pady=(0, SPACE_S))
        tk.Button(
            btn_row, text="🔄 Проверить движок",
            bg=SURFACE_2, fg=TEXT_PRIMARY, activeforeground=TEXT_PRIMARY,
            activebackground=SURFACE_PRESSED, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=14, pady=6,
            command=self._refresh_all).pack(side="left", padx=(0, SPACE_S))
        tk.Button(
            btn_row, text="📂 Открыть папку данных",
            bg=SURFACE_2, fg=TEXT_PRIMARY, activeforeground=TEXT_PRIMARY,
            activebackground=SURFACE_PRESSED, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=14, pady=6,
            command=self._open_workspace).pack(side="left")

        # Автообновление состояния каждые 2 с, пока страница открыта
        self.after(2000, self._auto_refresh_state)

    # ---------- обновление данных ----------

    def _refresh_all(self):
        """Обновить всё: устройства, хоткеи, мост, движок."""
        try:
            self._refresh_devices()
        except Exception:
            pass
        self._refresh_engine()
        self._refresh_hotkeys_state()
        self._refresh_bridge_state()

    def _auto_refresh_state(self):
        """Периодически обновлять состояние хоткеев и моста."""
        try:
            if self.winfo_exists():
                self._refresh_hotkeys_state()
                self._refresh_bridge_state()
                self.after(2000, self._auto_refresh_state)
        except Exception:
            pass

    def _toggle_hotkeys_from_settings(self):
        """Включить/выключить хоткеи прямо из настроек."""
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        try:
            live._toggle_hotkeys()
        except Exception as exc:
            self.hotkeys_state_lbl.config(text=f"ошибка: {exc}", fg=BAD)
            return
        self._refresh_hotkeys_state()

    def _toggle_bridge_from_settings(self):
        """Включить/выключить мост прямо из настроек."""
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            try:
                bridge.stop()
            except Exception:
                pass
            self.studio.bridge = None
            self.bridge_state_lbl.config(text="мост: ВЫКЛЮЧЕН", fg=TEXT_MUTED)
            self.bridge_toggle_btn.config(text="Включить")
            return
        ok, msg = self.studio._auto_route()
        if ok:
            self.bridge_toggle_btn.config(text="Выключить")
        self._refresh_bridge_state()

    def _refresh_hotkeys_state(self):
        """Показать, включены ли хоткеи живого перевода."""
        live = getattr(self.studio, "live", None)
        if live is None:
            self.hotkeys_state_lbl.config(
                text="хоткеи: LiveTab не готов", fg=TEXT_MUTED)
            return
        on = bool(getattr(live, "hotkeys_on", False))
        talk = live._hotkeys.get("live:talk", "ctrl+alt+t")
        cont = live._hotkeys.get("live:cont", "ctrl+alt+l")
        if on:
            self.hotkeys_state_lbl.config(
                text=f"хоткеи: ВКЛЮЧЕНЫ  ({talk} / {cont})", fg=GOOD)
            try:
                self.hk_toggle_btn.config(text="Выключить")
            except Exception:
                pass
        else:
            self.hotkeys_state_lbl.config(
                text=f"хоткеи: ВЫКЛЮЧЕНЫ  ({talk} / {cont})", fg=TEXT_MUTED)
            try:
                self.hk_toggle_btn.config(text="Включить")
            except Exception:
                pass

    def _refresh_bridge_state(self):
        """Показать, включён ли мост и куда он играет."""
        bridge = getattr(self.studio, "bridge", None)
        running = bool(bridge is not None and getattr(bridge, "running", False))
        if running:
            try:
                dev = bridge.render_device
                name = ""
                try:
                    import sounddevice as sd
                    name = sd.query_devices(dev)["name"]
                except Exception:
                    pass
                txt = f"мост: ВКЛЮЧЁН → {name}" if name else f"мост: ВКЛЮЧЁН (idx {dev})"
                self.bridge_state_lbl.config(text=txt, fg=GOOD)
            except Exception:
                self.bridge_state_lbl.config(text="мост: ВКЛЮЧЁН", fg=GOOD)
        else:
            self.bridge_state_lbl.config(
                text="мост: ВЫКЛЮЧЕН (нажми «Настроить под кабель»)",
                fg=TEXT_MUTED)

    def _refresh_devices(self):
        """Обновить списки аудиоустройств."""
        # Приоритет — данные LiveTab (они реально используются переводом)
        live = getattr(self.studio, "live", None)
        inputs = outputs = None
        if live is not None:
            try:
                inputs = live.get_input_devices()
                outputs = live.get_output_devices()
            except Exception:
                inputs = outputs = None
        if not inputs or not outputs:
            try:
                import sounddevice as sd
                devices = sd.query_devices()
                inputs = [(i, d["name"]) for i, d in enumerate(devices)
                          if d["max_input_channels"] > 0]
                outputs = [(i, d["name"]) for i, d in enumerate(devices)
                           if d["max_output_channels"] > 0]
            except Exception as exc:
                self.devices_status_lbl.config(
                    text=f"устройства: ошибка — {exc}", fg=BAD)
                return

        mic_pool = [(i, n) for i, n in inputs
                    if not any(g in n.lower() for g in
                               ("стерео микшер", "stereo mix", "первичный драйвер",
                                "primary sound capture", "переназначение звуковых",
                                "cable output", "vb-audio"))]
        pool = mic_pool or inputs

        self.mic_combo["values"] = [f"{i}: {n}" for i, n in pool]
        self.out_combo["values"] = [f"{i}: {n}" for i, n in outputs]
        self.capture_combo["values"] = [f"{i}: {n}" for i, n in inputs]
        # Комбобоксы моста (те же списки)
        self.bridge_mic_combo["values"] = [f"{i}: {n}" for i, n in pool]
        self.bridge_out_combo["values"] = [f"{i}: {n}" for i, n in outputs]

        # Подставить текущие значения: сначала из LiveTab, потом из Studio
        studio = self.studio
        cur_in = live.get_selected_mic() if live is not None else None
        if cur_in is None:
            cur_in = studio.in_device
        cur_out = live.get_selected_out() if live is not None else None
        if cur_out is None:
            cur_out = studio.out_device

        if cur_in is not None:
            for idx, (i, _n) in enumerate(pool):
                if i == cur_in:
                    self.mic_combo.current(idx)
                    self.bridge_mic_combo.current(idx)
                    break
        if cur_out is not None:
            for idx, (i, _n) in enumerate(outputs):
                if i == cur_out:
                    self.out_combo.current(idx)
                    self.bridge_out_combo.current(idx)
                    break

        self.mic_combo.bind("<<ComboboxSelected>>", self._on_mic_change)
        self.out_combo.bind("<<ComboboxSelected>>", self._on_out_change)
        self.bridge_mic_combo.bind("<<ComboboxSelected>>", self._on_bridge_mic_change)
        self.bridge_out_combo.bind("<<ComboboxSelected>>", self._on_bridge_out_change)
        self.capture_combo.bind("<<ComboboxSelected>>", self._on_capture_change)

        # Обновить устройства захвата из LiveTab API
        self._refresh_capture_devices()

        self.devices_status_lbl.config(
            text=f"устройства: {len(pool)} входов, {len(outputs)} выходов", fg=GOOD)

    def _refresh_capture_devices(self) -> None:
        """Обновить список устройств захвата из LiveTab API."""
        live = getattr(self.studio, "live", None)
        if live is None:
            self.capture_combo["values"] = []
            self.capture_combo.set("")
            return
        mode = self.capture_mode_var.get()
        mode_map = {
            "Legacy Input (Stereo Mix / CABLE Output)": "legacy_input",
            "WASAPI Endpoint Loopback": "wasapi_endpoint",
        }
        code = mode_map.get(mode, "legacy_input")
        devices = live.get_capture_devices(code)
        self.capture_combo["values"] = [
            f"{d['index']}: {d['name']}"
            + (f" → Loopback [{d['loopback_index']}]"
               if d.get("loopback_index") is not None else "")
            for d in devices
        ]
        if self.capture_combo["values"]:
            self.capture_combo.current(0)
            # Применить выбранное устройство в контроллере
            try:
                first = self.capture_combo["values"][0]
                idx = int(first.split(":")[0])
                loopback_idx = None
                if "Loopback [" in first:
                    try:
                        lb_part = first.split("Loopback [")[1].split("]")[0]
                        loopback_idx = int(lb_part)
                    except Exception:
                        pass
                live.set_capture_device(idx, loopback_idx)
            except Exception:
                pass

    def _refresh_engine(self):
        """Обновить состояние движка."""
        status = self.studio.get_engine_status()
        if not status["engine_installed"]:
            self.engine_status_lbl.config(text="движок: не установлен", fg=BAD)
            self.models_status_lbl.config(text="модели: недоступны без движка", fg=TEXT_MUTED)
        elif status["translator_ready"]:
            self.engine_status_lbl.config(text="движок: готов", fg=GOOD)
            self.models_status_lbl.config(text="модели: загружены (ASR, MT, TTS)", fg=GOOD)
        elif status["translator_loading"]:
            self.engine_status_lbl.config(text="движок: загружает модели…", fg=WARN)
            self.models_status_lbl.config(text="модели: загрузка…", fg=WARN)
        elif status["state"] == "ERROR":
            self.engine_status_lbl.config(text=f"движок: ошибка — {status['error'][:40]}", fg=BAD)
            self.models_status_lbl.config(text="модели: ошибка", fg=BAD)
        else:
            self.engine_status_lbl.config(text="движок: остановлен", fg=TEXT_MUTED)
            self.models_status_lbl.config(text="модели: не загружены", fg=TEXT_MUTED)
        # Заодно обновляем состояние хоткеев и моста
        try:
            self._refresh_hotkeys_state()
            self._refresh_bridge_state()
        except Exception:
            pass

    # ---------- обработчики ----------

    def _on_mic_change(self, _event=None):
        val = self.mic_combo.get()
        if val:
            idx = int(val.split(":")[0])
            self.studio.in_device = idx
            live = getattr(self.studio, "live", None)
            if live is not None:
                live.set_mic_device(idx)

    def _on_out_change(self, _event=None):
        val = self.out_combo.get()
        if val:
            idx = int(val.split(":")[0])
            self.studio.out_device = idx
            live = getattr(self.studio, "live", None)
            if live is not None:
                live.set_out_device(idx)

    def _on_bridge_mic_change(self, _event=None):
        val = self.bridge_mic_combo.get()
        if val:
            idx = int(val.split(":")[0])
            self.studio.in_device = idx
            live = getattr(self.studio, "live", None)
            if live is not None:
                live.set_mic_device(idx)

    def _on_bridge_out_change(self, _event=None):
        val = self.bridge_out_combo.get()
        if val:
            idx = int(val.split(":")[0])
            self.studio.out_device = idx
            live = getattr(self.studio, "live", None)
            if live is not None:
                live.set_out_device(idx)

    def _on_mic_change(self, _event=None):
        val = self.mic_combo.get()
        if val:
            idx = int(val.split(":")[0])
            self.studio.in_device = idx
            live = getattr(self.studio, "live", None)
            if live is not None:
                live.set_mic_device(idx)

    def _on_out_change(self, _event=None):
        val = self.out_combo.get()
        if val:
            idx = int(val.split(":")[0])
            self.studio.out_device = idx
            live = getattr(self.studio, "live", None)
            if live is not None:
                live.set_out_device(idx)

    def _on_bridge_mic_change(self, _event=None):
        val = self.bridge_mic_combo.get()
        if val:
            idx = int(val.split(":")[0])
            self.studio.in_device = idx
            live = getattr(self.studio, "live", None)
            if live is not None:
                live.set_mic_device(idx)

    def _on_bridge_out_change(self, _event=None):
        val = self.bridge_out_combo.get()
        if val:
            idx = int(val.split(":")[0])
            self.studio.out_device = idx
            live = getattr(self.studio, "live", None)
            if live is not None:
                live.set_out_device(idx)

    def _on_capture_change(self, _event=None):
        """Сменилось устройство захвата — применить в контроллере."""
        val = self.capture_combo.get()
        if not val:
            return
        try:
            device_idx = int(val.split(":")[0])
        except Exception:
            return
        # Извлечь loopback индекс для WASAPI
        loopback_idx = None
        if "Loopback [" in val:
            try:
                lb_part = val.split("Loopback [")[1].split("]")[0]
                loopback_idx = int(lb_part)
            except Exception:
                pass
        live = getattr(self.studio, "live", None)
        if live is not None:
            live.set_capture_device(device_idx, loopback_idx)

    def _on_capture_mode_change(self, _event=None):
        """Сменился режим захвата — обновить список устройств."""
        val = self.capture_mode_var.get()
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        # Перевести отображаемое имя в код режима
        mode_map = {
            "Legacy Input (Stereo Mix / CABLE Output)": "legacy_input",
            "WASAPI Endpoint Loopback": "wasapi_endpoint",
        }
        mode = mode_map.get(val, "legacy_input")
        live.set_capture_mode(mode)
        # Обновить список устройств для нового режима
        self._refresh_capture_devices()

    def _on_out_lang(self, _event=None):
        val = self.out_lang_combo.get()
        code = val.split(":")[0].strip()
        live = getattr(self.studio, "live", None)
        if live is not None:
            live.lang_combo.set(f"{code}: {core.lang_title(code)}")
            live._on_lang()

    def _toggle_bridge(self):
        studio = self.studio
        bridge = getattr(studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            bridge.stop()
            studio.bridge = None
            self.bridge_btn.config(text="▶ Включить мост", bg="#1e6f3f")
            self.bridge_status.config(text="мост выключен", fg=TEXT_MUTED)
            return
        # Запуск через Studio (общая логика со старым UI)
        ok, msg = studio._start_bridge()
        if not ok:
            self.bridge_status.config(text=msg, fg=BAD)
            return
        self.bridge_btn.config(text="■ Выключить мост", bg="#8a2f2f")
        self.bridge_status.config(text=msg, fg=GOOD)
        self._refresh_devices()

    def _auto_setup_cable(self):
        """Авто-настройка маршрута под виртуальный кабель (одна кнопка).

        Использует Studio._auto_route — ту же логику, что и в Legacy.
        """
        studio = self.studio
        ok, msg = studio._auto_route()
        if not ok:
            self.bridge_status.config(text=msg, fg=BAD)
            return
        # Обновляем комбобоксы под новые значения
        self._refresh_devices()
        bridge = getattr(studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            self.bridge_btn.config(text="■ Выключить мост", bg="#8a2f2f")
            self.bridge_status.config(text=msg, fg=GOOD)
        else:
            self.bridge_status.config(text=msg, fg=BAD)

    def _check_bridge(self):
        """Проверить, что мост реально передаёт сигнал."""
        bridge = getattr(self.studio, "bridge", None)
        if bridge is None or not getattr(bridge, "running", False):
            self.bridge_status.config(text="мост не запущен", fg=BAD)
            return
        self.bridge_status.config(text="проверяю… говори что-нибудь…", fg=WARN)
        try:
            self.update_idletasks()
        except Exception:
            pass
        import time as _time
        _time.sleep(2.0)
        st = bridge.status()
        self.bridge_status.config(
            text=f"микрофон: {st['mic_peak']:.3f} | на выходе: {st['out_peak']:.3f} "
                 + ("— сигнал идёт" if st["out_peak"] > 0.005
                    else "— тишина, проверь микрофон"),
            fg=GOOD if st["out_peak"] > 0.005 else BAD)

    def _toggle_duck(self):
        """Галочка: заглушить русский в кабеле (только перевод)."""
        studio = self.studio
        bridge = getattr(studio, "bridge", None)
        if bridge is None:
            self.duck_var.set(False)
            return
        flag = bool(self.duck_var.get())
        bridge.set_duck(flag)
        # Также применим к LiveTab (исполняющий перевод знает про mute)
        live = getattr(studio, "live", None)
        if live is not None and hasattr(live, "_apply_mute"):
            live._apply_mute()

    def _toggle_hotkeys(self):
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        if live.hotkeys_on:
            live._toggle_hotkeys()
            self.hk_enable_btn.config(text="⌨ Включить горячие клавиши", bg="#1e6f3f")
            self.hk_status.config(text="горячие клавиши выключены", fg=TEXT_MUTED)
        else:
            live._toggle_hotkeys()
            self.hk_enable_btn.config(text="⌨ Выключить горячие клавиши", bg="#8a2f2f")
            self.hk_status.config(text="горячие клавиши включены", fg=GOOD)
        # Обновить метки клавиш
        self._refresh_hotkey_labels()

    def _refresh_hotkey_labels(self):
        live = getattr(self.studio, "live", None)
        if live is None:
            return
        talk = live._hotkeys.get("live:talk", "ctrl+alt+t")
        cont = live._hotkeys.get("live:cont", "ctrl+alt+l")
        import hotkeys as hk
        self.hk_talk_lbl.config(
            text=f"Говорить (зажать): {hk.pretty_combo(talk)}", fg=TEXT_SECONDARY)
        self.hk_cont_lbl.config(
            text=f"Непрерывно: {hk.pretty_combo(cont)}", fg=TEXT_SECONDARY)

    def _diag_devices(self):
        studio = self.studio
        if hasattr(studio, "_diag_devices"):
            studio._diag_devices()

    def _open_workspace(self):
        import os, subprocess
        path = sp.workspace() if 'sp' in dir() else None
        try:
            import studio_paths as sp
            path = sp.workspace()
        except Exception:
            path = ""
        if path and os.path.isdir(path):
            subprocess.Popen(f'explorer "{path}"')