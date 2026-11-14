"""Страница «Голоса» — управление голосовыми профилями.

Реальная функциональность:
- Отображение существующего образца голоса (reference.wav)
- Список записей подсказок из samples/
- Запись нового образца через studio.recorder
- Клонирование голоса (XTTS) через core.build_reference / core.clone_*
- Прослушивание образца голоса
- Выбор профиля для входящего перевода
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

import soundfile as sf

from ui.glass_card import GlassCard
from ui.theme import (
    ACCENT, ACTIVE, BAD, BG, BORDER_FOCUS, BORDER_SUBTLE, GOOD, HOVER,
    RADIUS_CARD, SPACE_L, SPACE_M, SPACE_S, SPACE_XL, SPACE_XS,
    SURFACE_1, SURFACE_2, SURFACE_HOVER, SURFACE_PRESSED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY,
    WARN, FONT_APP_TITLE, FONT_BODY, FONT_CARD_TITLE, FONT_H2,
    FONT_SECONDARY,
)
import studio_core as core
import studio_paths as sp
import studio_paths as sp


class VoicesPage(tk.Frame):
    """Страница управления голосовыми профилями."""

    def __init__(self, master, studio, **kwargs):
        super().__init__(master, bg=BG, **kwargs)
        self.studio = studio
        self._recording = False
        self._build()
        self._refresh()

    def _build(self):
        # Заголовок
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", pady=(0, SPACE_XL))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header, text="Голоса",
            bg=BG, fg=TEXT_PRIMARY, font=FONT_APP_TITLE, anchor="w").pack(
                side="left")

        # --- Текущий образец голоса ---
        ref_card = GlassCard(self, radius=RADIUS_CARD, pad=SPACE_M)
        ref_card.pack(fill="x", pady=SPACE_L)
        inner = ref_card.inner
        inner.grid_columnconfigure(0, weight=1)

        tk.Label(
            inner, text="Образец голоса (референс для XTTS)",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(0, SPACE_S))

        self.ref_status = tk.Label(
            inner, text="Проверяю…", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_BODY, anchor="w")
        self.ref_status.pack(anchor="w", pady=(0, SPACE_M))

        ref_btns = tk.Frame(inner, bg=SURFACE_1)
        ref_btns.pack(anchor="w")

        self.btn_play_ref = tk.Button(
            ref_btns, text="▶ Прослушать образец",
            bg=BORDER_SUBTLE, fg=TEXT_PRIMARY, activeforeground=TEXT_PRIMARY,
            activebackground=SURFACE_PRESSED, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=14, pady=6,
            command=self._play_reference)
        self.btn_play_ref.pack(side="left", padx=(0, SPACE_S))
        self.btn_play_ref.bind("<Enter>", lambda e: self.btn_play_ref.configure(bg=SURFACE_PRESSED))
        self.btn_play_ref.bind("<Leave>", lambda e: self.btn_play_ref.configure(bg=BORDER_SUBTLE))

        self.btn_build_ref = tk.Button(
            ref_btns, text="★ Собрать образец из записей",
            bg=ACCENT, fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=14, pady=6,
            command=self._build_reference)
        self.btn_build_ref.pack(side="left")
        self.btn_build_ref.bind("<Enter>", lambda e: self.btn_build_ref.configure(bg=SURFACE_PRESSED))
        self.btn_build_ref.bind("<Leave>", lambda e: self.btn_build_ref.configure(bg=ACCENT))

        # --- Запись подсказок ---
        rec_card = GlassCard(self, radius=RADIUS_CARD, pad=SPACE_M)
        rec_card.pack(fill="x", pady=SPACE_L)
        inner2 = rec_card.inner
        inner2.grid_columnconfigure(0, weight=1)

        tk.Label(
            inner2, text="Запись подсказок для клонирования",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(0, SPACE_S))

        tk.Label(
            inner2, text="Запишите 5–8 коротких фраз — XTTS клонирует ваш голос по ним.",
            bg=SURFACE_1, fg=TEXT_SECONDARY, font=FONT_BODY,
            anchor="w", justify="left").pack(anchor="w", pady=(0, SPACE_M))

        rec_btns = tk.Frame(inner2, bg=SURFACE_1)
        rec_btns.pack(anchor="w", pady=(0, SPACE_S))

        self.btn_rec = tk.Button(
            rec_btns, text="● Начать запись",
            bg=ACCENT, fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=16, pady=8,
            command=self._toggle_recording)
        self.btn_rec.pack(side="left", padx=(0, SPACE_S))
        self.btn_rec.bind("<Enter>", lambda e: self.btn_rec.configure(bg=SURFACE_PRESSED))
        self.btn_rec.bind("<Leave>", lambda e: self.btn_rec.configure(bg=ACCENT))

        self.btn_stop_rec = tk.Button(
            rec_btns, text="■ Стоп",
            bg=SURFACE_2, fg=TEXT_MUTED, activeforeground=TEXT_PRIMARY,
            activebackground=SURFACE_PRESSED, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=14, pady=8,
            command=self._stop_recording, state="disabled")
        self.btn_stop_rec.pack(side="left", padx=(0, SPACE_S))
        self.btn_stop_rec.bind("<Enter>", lambda e: self.btn_stop_rec.configure(bg=SURFACE_PRESSED))
        self.btn_stop_rec.bind("<Leave>", lambda e: self.btn_stop_rec.configure(bg=SURFACE_2))

        self.btn_test_mic = tk.Button(
            rec_btns, text="♪ Тест микрофона",
            bg=BORDER_SUBTLE, fg=TEXT_PRIMARY, activeforeground=TEXT_PRIMARY,
            activebackground=SURFACE_PRESSED, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=14, pady=8,
            command=self._test_microphone)
        self.btn_test_mic.pack(side="left")
        self.btn_test_mic.bind("<Enter>", lambda e: self.btn_test_mic.configure(bg=SURFACE_PRESSED))
        self.btn_test_mic.bind("<Leave>", lambda e: self.btn_test_mic.configure(bg=BORDER_SUBTLE))

        self.rec_status = tk.Label(
            inner2, text="", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w")
        self.rec_status.pack(anchor="w", pady=(SPACE_S, 0))

        # --- Список записей ---
        list_card = GlassCard(self, radius=RADIUS_CARD, pad=SPACE_M)
        list_card.pack(fill="both", expand=True, pady=SPACE_L)
        inner3 = list_card.inner
        inner3.grid_columnconfigure(0, weight=1)

        tk.Label(
            inner3, text="Записи подсказок",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(0, SPACE_S))

        self.tree = ttk.Treeview(
            inner3, columns=("n", "text", "dur", "q"), show="headings",
            height=6)
        for col, title, width in (("n", "#", 40), ("text", "Подсказка", 400),
                                  ("dur", "Длина", 80), ("q", "Качество", 100)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width,
                             anchor="center" if col != "text" else "w")
        self.tree.pack(fill="both", expand=True, pady=(0, SPACE_M))

        # --- Клонирование (XTTS) ---
        clone_card = GlassCard(self, radius=RADIUS_CARD, pad=SPACE_M)
        clone_card.pack(fill="x", pady=SPACE_L)
        inner4 = clone_card.inner
        inner4.grid_columnconfigure(0, weight=1)

        tk.Label(
            inner4, text="Клонирование голоса (XTTS)",
            bg=SURFACE_1, fg=TEXT_PRIMARY, font=FONT_H2, anchor="w").pack(
                anchor="w", pady=(0, SPACE_S))

        tk.Label(
            inner4, text="Сгенерировать все реплики своим клонированным голосом. "
                         "Требуется образец голоса (reference.wav).",
            bg=SURFACE_1, fg=TEXT_SECONDARY, font=FONT_BODY,
            anchor="w", justify="left").pack(anchor="w", pady=(0, SPACE_M))

        clone_btns = tk.Frame(inner4, bg=SURFACE_1)
        clone_btns.pack(anchor="w")

        self.btn_clone = tk.Button(
            clone_btns, text="🎙 Клонировать и озвучить всё",
            bg="#1e6f3f", fg="#fff", activeforeground="#fff",
            activebackground=ACTIVE, font=FONT_BODY,
            relief="flat", cursor="hand2", padx=16, pady=8,
            command=self._clone_all)
        self.btn_clone.pack(side="left", padx=(0, SPACE_S))
        self.btn_clone.bind("<Enter>", lambda e: self.btn_clone.configure(bg=SURFACE_PRESSED))
        self.btn_clone.bind("<Leave>", lambda e: self.btn_clone.configure(bg="#1e6f3f"))

        self.clone_status = tk.Label(
            inner4, text="", bg=SURFACE_1, fg=TEXT_MUTED,
            font=FONT_SECONDARY, anchor="w")
        self.clone_status.pack(anchor="w", pady=(SPACE_S, 0))

    # ---------- обновление состояния ----------

    def _refresh(self):
        """Обновить статус образца и список записей."""
        self._update_ref_status()
        self._refresh_tree()

    def _update_ref_status(self):
        """Проверить, существует ли reference.wav."""
        ref_path = sp.output_paths()["reference"]
        if os.path.exists(ref_path):
            try:
                info = sf.info(ref_path)
                self.ref_status.config(
                    text=f"Образец есть: {ref_path} ({info.duration:.1f} c, "
                         f"{info.samplerate} Гц)",
                    fg=GOOD)
                self.btn_play_ref.config(state="normal")
                self.btn_build_ref.config(state="normal")
                self.btn_clone.config(state="normal")
            except Exception:
                self.ref_status.config(
                    text=f"Образец есть, но не удается прочитать: {ref_path}",
                    fg=WARN)
                self.btn_play_ref.config(state="disabled")
        else:
            self.ref_status.config(
                text="Образца голоса нет. Запишите подсказки и нажмите "
                     "«Собрать образец из записей».",
                fg=TEXT_MUTED)
            self.btn_play_ref.config(state="disabled")
            self.btn_build_ref.config(state="disabled")
            self.btn_clone.config(state="disabled")

    def _refresh_tree(self):
        """Обновить список записей подсказок."""
        samples = sp.output_paths()["samples"]
        self.tree.delete(*self.tree.get_children())
        if not os.path.exists(samples):
            return
        try:
            files = sorted(f for f in os.listdir(samples) if f.endswith(".wav"))
        except Exception:
            files = []
        import soundfile as sf
        for i, fname in enumerate(files):
            path = os.path.join(samples, fname)
            dur = q = "—"
            try:
                info = sf.info(path)
                dur = f"{info.duration:.1f} c"
                data, _ = sf.read(path, dtype="float32", always_2d=False)
                q = "ок" if core.quality_report(data)["ok"] else "!"
            except Exception:
                pass
            self.tree.insert("", "end", values=(i + 1, fname, dur, q))

    # ---------- действия ----------

    def _play_reference(self):
        """Прослушать образец голоса."""
        ref_path = sp.output_paths()["reference"]
        if not os.path.exists(ref_path):
            self.rec_status.config(text="Образца голоса нет")
            return
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            if bridge.play_phrase(ref_path):
                self.rec_status.config(text="Играю образец через мост…")
                return
        try:
            import hotkeys as hk
            out_device = getattr(self.studio, "out_device", None)
            hk.play_file(ref_path, out_device)
            self.rec_status.config(text="Играю образец…")
        except Exception as exc:
            self.rec_status.config(text=f"Ошибка воспроизведения: {exc}")

    def _build_reference(self):
        """Собрать образец из записей подсказок."""
        samples = sp.output_paths()["samples"]
        if not os.path.exists(samples):
            self.rec_status.config(text="Нет записей подсказок")
            return
        try:
            files = sorted(
                os.path.join(samples, f)
                for f in os.listdir(samples) if f.endswith(".wav"))
        except Exception:
            files = []
        if not files:
            self.rec_status.config(text="Нет записей подсказок")
            return
        res = core.build_reference(files, sp.output_paths()["reference"])
        if res["ok"]:
            self.rec_status.config(
                text=f"Образец готов: {res['duration']:.1f} c из {res['count']} записей")
            self._update_ref_status()
        else:
            self.rec_status.config(text=f"Не удалось собрать образец: {res.get('error', '')}")

    def _toggle_recording(self):
        """Включить/выключить запись микрофона."""
        recorder = getattr(self.studio, "recorder", None)
        if recorder is None:
            self.rec_status.config(text="Рекуордер недоступен")
            return
        if not self._recording:
            try:
                device = recorder.device
                if device is None:
                    import sounddevice as sd
                    device = sd.default.device[0]
                recorder.start(device)
                self._recording = True
                self.btn_rec.config(text="● Идёт запись…", bg=BAD)
                self.btn_stop_rec.config(state="normal")
                self.rec_status.config(text="Запись идёт — говорите!")
            except Exception as exc:
                self.rec_status.config(text=f"Ошибка записи: {exc}")
        else:
            self._stop_recording()

    def _stop_recording(self):
        """Остановить запись и сохранить файл."""
        recorder = getattr(self.studio, "recorder", None)
        if recorder is None or not recorder.recording:
            return
        try:
            raw = recorder.stop()
        except Exception:
            raw = b""
        self._recording = False
        self.btn_rec.config(text="● Начать запись", bg=ACCENT)
        self.btn_stop_rec.config(state="disabled")
        if len(raw) == 0:
            self.rec_status.config(text="Звук не получен")
            return
        trimmed = core.trim_by_energy(raw)
        rep = core.quality_report(trimmed)
        samples = sp.output_paths()["samples"]
        os.makedirs(samples, exist_ok=True)
        import time
        path = os.path.join(samples, f"take_{time.strftime('%H%M%S')}.wav")
        import soundfile as sf
        sf.write(path, trimmed, core.SR, subtype="PCM_16")
        self.records[len(getattr(self, "records", {}))] = path
        self._refresh_tree()
        self._update_ref_status()
        if rep["ok"]:
            self.rec_status.config(
                text=f"Записано: {rep['dur']:.1f} c — ок. "
                     f"Соберите образец кнопкой выше.")
        else:
            self.rec_status.config(
                text=f"Переделайте запись: {rep.get('reason', '')}")

    def _test_microphone(self):
        """Проверить микрофон."""
        self.rec_status.config(text="Проверяю микрофон…")

        def _work():
            dev, name = core.pick_input_device()
            if dev is None:
                self.rec_status.config(text="Микрофон не найден")
                return
            recorder = getattr(self.studio, "recorder", None)
            if recorder is not None:
                recorder.device = dev
            res = core.test_microphone(dev)
            self.rec_status.config(
                text=f"Микрофон «{name}»: пик {res['peak']:.3f}, RMS {res['rms']:.4f} — {res['verdict']}")

        import threading
        threading.Thread(target=_work, daemon=True).start()

    def _clone_all(self):
        """Запустить клонирование всех реплик."""
        ref = sp.output_paths()["reference"]
        if not os.path.exists(ref):
            self.clone_status.config(text="Нет образца голоса")
            return
        # Используем существующий механизм из Studio
        studio = self.studio
        if hasattr(studio, "_voice_all"):
            studio._voice_all()
            self.clone_status.config(text="Клонирование запущено…")
        else:
            self.clone_status.config(text="Функция клонирования недоступна")


# backward-compatible alias (старые вызовы pueden использовать VoicesPage)
Records = VoicesPage