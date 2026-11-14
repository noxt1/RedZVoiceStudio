"""Вкладка «6. Живой перевод»: говоришь по-русски — слышишь себя на испанском.

Два режима:

  «Нажатием»      жмёшь «Говорить» -> говоришь -> отпускаешь -> перевод.
  «Непрерывно»    приложение слушает микрофон всё время и переводит каждую
                   завершённую фразу САМО, пока ты говоришь дальше. Останавливаться
                   не нужно: конец фразы определяется по паузе в речи.

Конвейер (в движке, отдельном процессе):
    аудио -> Whisper large-v3-turbo (RU) -> opus-mt-ru-es (RU->ES)
          -> XTTS-v2 inference_stream (ES, твоим голосом) -> устройство вывода

Модели живут в отдельном процессе (движке), потому что в EXE нет torch.
"""

from __future__ import annotations

import os
import threading
import time

import numpy as np
import tkinter as tk
from tkinter import ttk

import live_client as lc
import hotkeys as hk
import scrollframe
import studio_core as core
import studio_paths as sp
from incoming_tts import IncomingTTSProvider
from wasapi_loopback import LoopbackCapture, CaptureMode, list_input_devices, list_output_devices, list_running_processes

BG, FG, DIM, ACCENT, GOOD, WARN = "#14161a", "#e8e8e8", "#8b93a1", "#4a9eff", "#7bd88f", "#e8c07a"
BAD = "#e06c6c"

SR_REC = 44100        # частота записи
BLOCK_SEC = 0.05      # размер блока от микрофона
SILENCE_END = 0.55    # пауза, которая завершает фразу (с)
MIN_SPEECH = 0.35     # короче — не отправляем (с)
MAX_SEG = 14.0        # длиннее — режем на части (с)
TRIM_SIL = 0.18       # сколько тишины обрезать по краям (с)
SR_PEER = 44100       # частота записи звука игры (перехват игроков)

# действия для глобальных хоткеев
ACT_CONT = "live:cont"     # непрерывный режим (переключатель)
ACT_TALK = "live:talk"     # говорить (зажать): русский -> испанский
HOTKEY_FILE = "live_hotkeys.json"


class LiveTab:
    """Вкладка живого перевода. Собирается в Studio как self.live."""

    def __init__(self, studio) -> None:
        self.studio = studio
        self.tab = studio.tab_live
        self.translator: lc.LiveTranslator | None = None

        # --- поток микрофона (общий для режимов «зажать» и «Непрерывно») ---
        self._stream = None

        # --- непрерывный режим ---
        self._cont_on = False
        self._cont_buf: list[np.ndarray] = []
        self._cont_silence = 0.0
        self._cont_has_speech = False
        self._noise = 0.005
        self._rms_history: list[float] = []
        self._smooth: list[float] = []
        self._strong_blocks = 0

        # --- воспроизведение ---
        self._play_stream = None
        self._play_queue: list[np.ndarray] = []
        self._play_lock = threading.Lock()
        self._playing = False

        # --- очередь на перевод ---
        self._queue: list[tuple[np.ndarray, int]] = []
        self._queue_lock = threading.Lock()

        self._last_ru = ""
        self._last_es = ""
        self._last_engine_log = ""
        self._sample_files: list[str] = []
        self._inputs: list[tuple[int, str]] = []
        self._outputs: list[tuple[int, str]] = []
        self._mic_idx: int | None = None
        self._swap_busy = False
        self._swap_wait_play = False
        self._swap_sr = SR_REC
        # Разрешён ли вывод перевода в кабель. Когда перевод выключают,
        # уже отправленные чанки приходят ПОЗЖЕ — их надо отбросить,
        # иначе испанский доигрывает параллельно с русским.
        self._out_enabled = False
        # --- режим «ЗАЖАТЬ» (главный) ---
        # Зажал кнопку -> русский в кабеле заглушён, идёт испанский.
        # Отпустил -> русский возвращается.
        self._hold_on = False          # сейчас зажато
        self._hold_wait_play = False   # ждём, пока доиграет испанский
        self._hold_vk = 0              # VK клавиши-хоткея (для отслеживания отпускания)
        # Заглушать ли русский в кабеле в режиме «Непрерывно».
        # С зажатой кнопкой русский заглушается ВСЕГДА.
        self._mute_ru = False
        # Уровень «живости» синтеза (0 — ровно, 3 — максимум жизни).
        self._liveliness = 2

        # --- перехват речи других игроков ---
        self._peer_stream = None
        self._peer_devices: list[tuple[int, str]] = []
        self._peer_buf: list[np.ndarray] = []
        self._peer_silence = 0.0
        self._peer_has_speech = False
        self._peer_strong = 0
        self._peer_rms: list[float] = []
        self._peer_level = 0.0
        self._peer_rate = SR_PEER
        # Состояние перехвата: OFF / STARTING / ACTIVE / STOPPING / ERROR
        self._peer_state: str = "OFF"
        self._peer_state_ts: float = 0.0
        self._peer_pending_device: int | None = None  # устройство для повторного подключения

        # --- входящий перевод (TTS в наушники) ---
        self._incoming_tts: IncomingTTSProvider | None = None
        # --- захват входящего звука собеседника (Этап A) ---
        self._loopback_capture: LoopbackCapture | None = None

        # горячие клавиши: комбинации. Scroll_Lock как глобальный хоткей
        # НЕ доходит с настоящей клавиатуры (Windows обрабатывает его сама),
        # поэтому дефолт — комбинация.
        self._hotkeys: dict[str, str] = {ACT_CONT: "ctrl+alt+l",
                                         ACT_TALK: "ctrl+alt+t"}
        self._load_hotkeys()
        self.hotkeys_on = False
        self._build()

    # ---------- интерфейс ----------
    def _build(self) -> None:
        st = self.studio
        # Вкладка длинная (кнопка, настройки, хоткеи, «В игре», распознанное) —
        # на 1080p половина уезжала за нижний край. Поэтому прокручиваем.
        scroller = scrollframe.ScrollFrame(self.tab, bg=BG)
        scroller.pack(fill="both", expand=True)
        self.scroller = scroller
        self.tab = scroller.body
        intro = tk.LabelFrame(self.tab, text=" Как это работает ", bg=BG, fg=DIM,
                              font=("Segoe UI", 9), padx=14, pady=10)
        intro.pack(fill="x", padx=16, pady=(10, 4))
        tk.Label(
            intro,
            text=("Говоришь по-русски — в кабель уходит твой же голос, "
                  "но на испанском.\n"
                  "Простое правило: держишь кнопку «ЗАЖАТЬ И ГОВОРИТЬ» — "
                  "русский в кабеле заглушён, идёт испанский. "
                  "Отпустил — русский вернулся.\n"
                  "Чтобы это слышали другие (Discord, игра), устройство вывода "
                  "должно быть тем, которое у них стоит микрофоном."),
            bg=BG, fg=FG, font=("Segoe UI", 10), justify="left").pack(anchor="w")

        # --- ГЛАВНАЯ КНОПКА: зажал — русский пропал, идёт испанский ---
        hold_box = tk.LabelFrame(self.tab, text=" Говори в игру ", bg=BG, fg=DIM,
                                 font=("Segoe UI", 9), padx=14, pady=10)
        hold_box.pack(fill="x", padx=16, pady=(8, 4))

        self.hold_btn = tk.Button(
            hold_box,
            text="🎤  ЗАЖАТЬ И ГОВОРИТЬ",
            bg="#1e6f3f", fg="#fff", activebackground="#8a2f2f",
            font=("Segoe UI", 15, "bold"), relief="flat", cursor="hand2",
            padx=20, pady=14)
        self.hold_btn.pack(fill="x")
        self.hold_btn.bind("<ButtonPress-1>", self._hold_press)
        self.hold_btn.bind("<ButtonRelease-1>", self._hold_release)
        # чтобы кнопку можно было держать и пробелом (когда она в фокусе)
        self.hold_btn.bind("<KeyPress-space>", self._hold_press)
        self.hold_btn.bind("<KeyRelease-space>", self._hold_release)
        self.hold_btn.bind("<FocusIn>", lambda e: self.hold_btn.config(
            highlightthickness=2, highlightbackground=ACCENT))
        self.hold_btn.bind("<FocusOut>", lambda e: self.hold_btn.config(
            highlightthickness=0))

        tk.Label(
            hold_box,
            text=("Пока держишь — твой русский в кабеле заглушён, и в кабель "
                  "идёт испанский перевод.\n"
                  "Отпустил — испанский договорил, и русский снова пошёл "
                  "в кабель.\n"
                  "Кнопку можно держать мышкой; если окно приложения свёрнуто "
                  "и игра в фокусе — держи горячую клавишу «Говорить»."),
            bg=BG, fg=DIM, font=("Segoe UI", 10), justify="left").pack(
                anchor="w", pady=(8, 0))

        # --- управление ---
        box = tk.LabelFrame(self.tab, text=" Настройки ", bg=BG, fg=DIM,
                            font=("Segoe UI", 9), padx=14, pady=10)
        box.pack(fill="x", padx=16, pady=(4, 4))

        row = tk.Frame(box, bg=BG)
        row.pack(fill="x", pady=2)
        tk.Label(row, text="Микрофон:", bg=BG, fg=DIM,
                 font=("Segoe UI", 10)).pack(side="left")
        self.mic_combo = ttk.Combobox(row, state="readonly", width=52)
        self.mic_combo.pack(side="left", padx=(8, 0))

        row2 = tk.Frame(box, bg=BG)
        row2.pack(fill="x", pady=2)
        tk.Label(row2, text="Играть перевод в:", bg=BG, fg=DIM,
                 font=("Segoe UI", 10)).pack(side="left")
        self.out_combo = ttk.Combobox(row2, state="readonly", width=52)
        self.out_combo.pack(side="left", padx=(8, 0))

        row3 = tk.Frame(box, bg=BG)
        row3.pack(fill="x", pady=6)
        self.cont_btn = tk.Button(
            row3, text="🔴 Непрерывно: выкл", bg="#2b3a4d", fg="#fff",
            activebackground="#3a4d64", font=("Segoe UI", 11, "bold"),
            width=22, height=2, relief="flat", cursor="hand2",
            command=self._toggle_cont)
        self.cont_btn.pack(side="left", padx=(0, 8))

        self.state_lbl = tk.Label(row3, text="движок не запущен", bg=BG, fg=DIM,
                                  font=("Segoe UI", 10))
        self.state_lbl.pack(side="left", padx=(14, 0))

        row4 = tk.Frame(box, bg=BG)
        row4.pack(fill="x", pady=6)
        tk.Label(row4, text="Живость голоса:", bg=BG, fg=DIM,
                 font=("Segoe UI", 10)).pack(side="left")
        self.liveliness = tk.Scale(
            row4, from_=0, to=3, orient="horizontal", length=200,
            bg=BG, fg=FG, troughcolor="#1e2229", highlightthickness=0,
            activebackground=ACCENT, showvalue=True, resolution=1,
            command=self._on_liveliness)
        self.liveliness.set(2)
        self.liveliness.pack(side="left", padx=(8, 8))
        tk.Label(row4, text="0 — ровно, 3 — максимум жизни", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).pack(side="left")

        # --- язык перевода ---
        row_lang = tk.Frame(box, bg=BG)
        row_lang.pack(fill="x", pady=6)
        tk.Label(row_lang, text="Язык перевода:", bg=BG, fg=DIM,
                 font=("Segoe UI", 10)).pack(side="left")
        self.lang_combo = ttk.Combobox(row_lang, state="readonly", width=32)
        self.lang_combo["values"] = [f"{code}: {title}"
                                     for code, title in core.lang_titles()]
        self.lang_combo.current(0)
        self.lang_combo.pack(side="left", padx=(8, 8))
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_lang)
        tk.Label(row_lang, text="в кабель уйдёт голос на этом языке",
                 bg=BG, fg=DIM, font=("Segoe UI", 9)).pack(side="left")

        # проверка без микрофона: берём одну из записей образца
        row5 = tk.Frame(box, bg=BG)
        row5.pack(fill="x", pady=(4, 0))
        tk.Label(row5, text="Проверка без микрофона:", bg=BG, fg=DIM,
                 font=("Segoe UI", 10)).pack(side="left")
        self.test_combo = ttk.Combobox(row5, state="readonly", width=40)
        self.test_combo.pack(side="left", padx=(8, 0))
        self.test_btn = tk.Button(row5, text="▶ Проверить", bg="#2b3a4d", fg="#fff",                                  activebackground="#3a4d64", font=("Segoe UI", 10),
                                  relief="flat", command=self._test_with_sample)
        self.test_btn.pack(side="left", padx=(8, 0))

        # --- горячие клавиши (для игры, когда окно приложения свёрнуто) ---
        hk_box = tk.LabelFrame(self.tab, text=" Горячие клавиши (нужны, когда игра в фокусе) ",
                                bg=BG, fg=DIM, font=("Segoe UI", 9), padx=14, pady=10)
        hk_box.pack(fill="x", padx=16, pady=(4, 8))

        hk_row = tk.Frame(hk_box, bg=BG)
        hk_row.pack(fill="x", pady=3)
        tk.Label(hk_row, text="Говорить (зажать):", bg=BG, fg=DIM,
                 font=("Segoe UI", 10)).pack(side="left")
        self.hk_talk = self._hotkey_entry(hk_row, ACT_TALK, "ctrl+alt+t")
        tk.Label(hk_row, text="   Непрерывно:", bg=BG, fg=DIM,
                 font=("Segoe UI", 10)).pack(side="left")
        self.hk_cont = self._hotkey_entry(hk_row, ACT_CONT, "ctrl+alt+l")

        self.hk_help = tk.Label(
            hk_box,
            text=("«Говорить (зажать)» — то же, что кнопка наверху: держишь "
                  "клавишу — в кабель идёт испанский, отпустил — русский.\n"
                  "Назначить можно ЛЮБУЮ клавишу: нажми её в поле. Если клавиша "
                  "занята другой программой, приложение подберёт запасную "
                  "и покажет её."),
            bg=BG, fg=DIM, font=("Segoe UI", 9), justify="left")
        self.hk_help.pack(anchor="w", pady=(4, 0))

        hk_row2 = tk.Frame(hk_box, bg=BG)
        hk_row2.pack(fill="x", pady=(4, 0))
        self.hk_btn = tk.Button(hk_row2, text="⌨ Включить горячие клавиши", bg="#2c313a",
                                fg=FG, activebackground="#3a4d64", font=("Segoe UI", 10),
                                relief="flat", command=self._toggle_hotkeys)
        self.hk_btn.pack(side="left", padx=(0, 8))
        tk.Button(hk_row2, text="Сбросить", bg="#2c313a", fg=FG,
                  activebackground="#3a4d64", font=("Segoe UI", 10),
                  relief="flat", command=self._reset_hotkeys).pack(side="left")
        self.hk_status = tk.Label(hk_row2, text="", bg=BG, fg=DIM,
                                  font=("Segoe UI", 9))
        self.hk_status.pack(side="left", padx=(12, 0))

        # --- что слышат собеседники ---
        out_box = tk.LabelFrame(self.tab, text=" Что слышат в кабеле ", bg=BG, fg=DIM,
                                font=("Segoe UI", 9), padx=14, pady=10)
        out_box.pack(fill="x", padx=16, pady=(0, 8))
        self.only_es = tk.BooleanVar(value=False)
        tk.Checkbutton(
            out_box,
            text="В режиме «Непрерывно» — только испанский (русский заглушён)",
            variable=self.only_es, command=self._toggle_only_es,
            bg=BG, fg=FG, activebackground=BG, activeforeground=FG,
            selectcolor=BG, highlightthickness=0, anchor="w",
            font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(
            out_box,
            text=("С кнопкой «ЗАЖАТЬ» это не нужно: пока держишь кнопку, "
                  "русский и так заглушён, а отпустил — вернулся.\n"
                  "Галочка пригодится для режима «Непрерывно», где перевод "
                  "идёт сам, а русский без неё слышен вместе с испанским."),
            bg=BG, fg=DIM, font=("Segoe UI", 9), justify="left").pack(anchor="w")

        # --- что видно в игре ---
        game_box = tk.LabelFrame(self.tab, text=" В игре ", bg=BG, fg=DIM,
                                 font=("Segoe UI", 9), padx=14, pady=10)
        game_box.pack(fill="x", padx=16, pady=(0, 8))

        row_ov = tk.Frame(game_box, bg=BG)
        row_ov.pack(fill="x", pady=2)
        self.overlay_on = tk.BooleanVar(value=False)
        tk.Checkbutton(
            row_ov, text="Оверлей с текстом поверх игры",
            variable=self.overlay_on, command=self._toggle_overlay,
            bg=BG, fg=FG, activebackground=BG, activeforeground=FG,
            selectcolor=BG, highlightthickness=0, anchor="w",
            font=("Segoe UI", 10)).pack(side="left")
        self.overlay_lbl = tk.Label(row_ov, text="", bg=BG, fg=DIM,
                                    font=("Segoe UI", 9))
        self.overlay_lbl.pack(side="left", padx=(12, 0))

        row_vol = tk.Frame(game_box, bg=BG)
        row_vol.pack(fill="x", pady=2)
        tk.Label(row_vol, text="Слышимость перевода в наушниках:", bg=BG,
                 fg=DIM, font=("Segoe UI", 10)).pack(side="left")
        self.monitor_vol = tk.Scale(
            row_vol, from_=0, to=150, orient="horizontal", length=200,
            bg=BG, fg=FG, troughcolor="#1e2229", highlightthickness=0,
            activebackground=ACCENT, showvalue=True, resolution=5,
            command=self._on_monitor_vol)
        self.monitor_vol.set(80)
        self.monitor_vol.pack(side="left", padx=(8, 8))
        tk.Label(row_vol, text="0 — не слышно, 80 — как есть", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).pack(side="left")

        # --- захват входящего звука собеседника (Этап A) ---
        capture_box = tk.LabelFrame(game_box, text=" Захват голоса собеседника ", bg=BG, fg=DIM,
                                    font=("Segoe UI", 9), padx=14, pady=10)
        capture_box.pack(fill="x", padx=16, pady=(8, 4))

        # Режимы захвата
        mode_row = tk.Frame(capture_box, bg=BG)
        mode_row.pack(fill="x", pady=(0, 8))

        self.capture_mode = tk.StringVar(value=CaptureMode.LEGACY_INPUT.value)
        modes = [
            (CaptureMode.LEGACY_INPUT.value, "Устройство записи (Stereo Mix / CABLE Output)", "legacy"),
            (CaptureMode.WASAPI_ENDPOINT.value, "Устройство вывода (WASAPI Loopback)", "wasapi"),
            (CaptureMode.PROCESS_LOOPBACK.value, "Процесс (Discord, RedM/FiveM)", "process"),
        ]
        for value, label, _key in modes:
            rb = tk.Radiobutton(
                mode_row, text=label, variable=self.capture_mode, value=value,
                bg=BG, fg=FG, activebackground=BG, activeforeground=FG,
                selectcolor=BG, font=("Segoe UI", 9),
                command=self._on_capture_mode_change,
            )
            rb.pack(side="left", padx=(0, 14))

        # Выбор устройства / процесса
        self.capture_device_row = tk.Frame(capture_box, bg=BG)
        self.capture_device_row.pack(fill="x", pady=(0, 8))

        tk.Label(self.capture_device_row, text="Источник:", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).pack(side="left")
        self.capture_device_combo = ttk.Combobox(
            self.capture_device_row, state="readonly", width=52
        )
        self.capture_device_combo.pack(side="left", padx=(8, 8))

        self.capture_refresh_btn = tk.Button(
            self.capture_device_row, text="🔄", bg="#2c313a", fg=FG,
            activebackground="#3a4d64", activeforeground=FG,
            relief="flat", cursor="hand2", width=2,
            command=self._refresh_capture_devices,
        )
        self.capture_refresh_btn.pack(side="left")

        # Кнопки управления
        btn_row = tk.Frame(capture_box, bg=BG)
        btn_row.pack(fill="x", pady=(0, 4))

        self.capture_on = tk.BooleanVar(value=False)
        self.capture_btn = tk.Button(
            btn_row, text="Включить захват", command=self._toggle_capture,
            bg="#2b3a4d", fg=FG, activebackground="#3a4d64",
            activeforeground=FG, font=("Segoe UI", 10, "bold"),
            relief="flat", cursor="hand2", padx=16, pady=6,
        )
        self.capture_btn.pack(side="left")

        self.capture_test_btn = tk.Button(
            btn_row, text="Проверить захват", command=self._test_capture,
            bg="#2c313a", fg=FG, activebackground="#3a4d64",
            activeforeground=FG, font=("Segoe UI", 9),
            relief="flat", cursor="hand2", padx=10, pady=6,
        )
        self.capture_test_btn.pack(side="left", padx=(8, 0))

        # Статус и метр
        status_row = tk.Frame(capture_box, bg=BG)
        status_row.pack(fill="x", pady=(0, 4))

        self.capture_status = tk.Label(status_row, text="выключен", bg=BG, fg=DIM,
                                       font=("Segoe UI", 9))
        self.capture_status.pack(side="left")

        self.capture_meter = tk.Label(status_row, text="", bg=BG, fg=DIM,
                                      font=("Consolas", 9))
        self.capture_meter.pack(side="right")

        self.capture_info = tk.Label(
            capture_box, text="", bg=BG, fg=DIM, font=("Segoe UI", 8),
            justify="left",
        )
        self.capture_info.pack(fill="x", pady=(2, 0))

        # Язык чужой речи
        lang_row = tk.Frame(capture_box, bg=BG)
        lang_row.pack(fill="x", pady=(6, 0))
        tk.Label(lang_row, text="Язык:", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).pack(side="left")
        self.peer_lang_combo = ttk.Combobox(lang_row, state="readonly", width=12)
        self.peer_lang_combo["values"] = ["авто", "es", "en", "it"]
        self.peer_lang_combo.current(0)
        self.peer_lang_combo.pack(side="left", padx=(6, 0))
        self.peer_lang_combo.bind("<<ComboboxSelected>>", self._on_peer_lang)

        # --- входящий перевод: озвучка в наушники (P1) ---
        row_in_tts = tk.Frame(game_box, bg=BG)
        row_in_tts.pack(fill="x", pady=(8, 2))
        self.incoming_on = tk.BooleanVar(value=False)
        tk.Checkbutton(
            row_in_tts, text="Озвучивать перевод в наушники (входящий)",
            variable=self.incoming_on, command=self._toggle_incoming,
            bg=BG, fg=FG, activebackground=BG, activeforeground=FG,
            selectcolor=BG, highlightthickness=0, anchor="w",
            font=("Segoe UI", 10)).pack(side="left")
        self.incoming_status = tk.Label(row_in_tts, text="выключен", bg=BG, fg=DIM,
                                        font=("Segoe UI", 9))
        self.incoming_status.pack(side="left", padx=(12, 0))

        row_in_tts2 = tk.Frame(game_box, bg=BG)
        row_in_tts2.pack(fill="x", pady=2)
        tk.Label(row_in_tts2, text="Голос:", bg=BG, fg=DIM,
                 font=("Segoe UI", 10)).pack(side="left")
        self.incoming_voice_combo = ttk.Combobox(
            row_in_tts2, state="readonly", width=30,
            values=["Клонированный голос (RU)", "Нейтральный (RU)"])
        self.incoming_voice_combo.current(0)
        self.incoming_voice_combo.pack(side="left", padx=(8, 8))
        self.incoming_voice_combo.bind(
            "<<ComboboxSelected>>", self._on_incoming_voice)
        tk.Label(row_in_tts2, text="Громкость:", bg=BG, fg=DIM,
                 font=("Segoe UI", 10)).pack(side="left")
        self.incoming_vol = tk.Scale(
            row_in_tts2, from_=0, to=100, orient="horizontal", length=120,
            bg=BG, fg=FG, troughcolor="#1e2229", highlightthickness=0,
            activebackground=ACCENT, showvalue=True, resolution=1,
            command=self._on_incoming_vol)
        self.incoming_vol.set(80)
        self.incoming_vol.pack(side="left", padx=(8, 0))

        # --- что было сказано ---
        seen = tk.LabelFrame(self.tab, text=" Что распознано ", bg=BG, fg=DIM,
                             font=("Segoe UI", 9), padx=14, pady=10)
        seen.pack(fill="both", expand=True, padx=16, pady=(6, 10))
        tk.Label(seen, text="Ты сказал (RU):", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).pack(anchor="w")
        self.ru_lbl = tk.Label(seen, text="—", bg=BG, fg=FG,
                               font=("Segoe UI", 11), justify="left", wraplength=900)
        self.ru_lbl.pack(anchor="w", pady=(2, 8))
        self.es_cap = tk.Label(seen, text="Звучит (ES):", bg=BG, fg=DIM,
                               font=("Segoe UI", 9))
        self.es_cap.pack(anchor="w")
        self.es_lbl = tk.Label(seen, text="—", bg=BG, fg=ACCENT,
                               font=("Segoe UI", 11, "bold"), justify="left", wraplength=900)
        self.es_lbl.pack(anchor="w", pady=(2, 6))
        # что сказали ДРУГИЕ игроки (перехват) — отдельной строкой
        self.peer_cap = tk.Label(seen, text="", bg=BG, fg=DIM,
                                 font=("Segoe UI", 9))
        self.peer_cap.pack(anchor="w")
        self.peer_lbl = tk.Label(seen, text="", bg=BG, fg=WARN,
                                 font=("Segoe UI", 11), justify="left", wraplength=900)
        self.peer_lbl.pack(anchor="w", pady=(2, 6))
        self.tone_lbl = tk.Label(seen, text="", bg=BG, fg=WARN,
                                 font=("Segoe UI", 9, "bold"))
        self.tone_lbl.pack(anchor="w")
        self.time_lbl = tk.Label(seen, text="", bg=BG, fg=DIM,
                                 font=("Segoe UI", 9))
        self.time_lbl.pack(anchor="w")

        st.root.after(300, self._refresh_devices)
        st.root.after(300, self._refresh_samples)
        st.root.after(500, self._refresh_peer_devices)

    def _refresh_samples(self) -> None:
        """Список записей образца — для проверки без микрофона."""
        samples = sp.output_paths()["samples"]
        try:
            files = sorted(f for f in os.listdir(samples) if f.endswith(".wav"))
        except Exception:
            files = []
        self._sample_files = files
        self.test_combo["values"] = files
        if files:
            self.test_combo.current(0)

    def _refresh_devices(self) -> None:
        try:
            import sounddevice as sd
            inputs = [(i, d["name"]) for i, d in enumerate(sd.query_devices())
                       if d["max_input_channels"] > 0]
            outputs = [(i, d["name"]) for i, d in enumerate(sd.query_devices())
                       if d["max_output_channels"] > 0]
        except Exception as exc:  # noqa: BLE001
            self.state_lbl.config(text=f"устройства: {exc}")
            return

        mic_pool = [(i, n) for i, n in inputs
                    if not any(g in n.lower() for g in
                               ("стерео микшер", "stereo mix", "первичный драйвер",
                                "primary sound capture", "переназначение звуковых"))]
        self._inputs = mic_pool or inputs
        self._outputs = outputs
        self.mic_combo["values"] = [f"{i}: {n}" for i, n in self._inputs]
        self.out_combo["values"] = [f"{i}: {n}" for i, n in outputs]
        self.out_combo.bind("<<ComboboxSelected>>",
                            lambda _e: self._warn_if_cable_without_bridge())

        try:
            import sounddevice as sd
            cur_in = sd.default.device[0]
            cur_out = sd.default.device[1]
        except Exception:
            cur_in = cur_out = None

        for idx, (i, _n) in enumerate(self._inputs):
            if i == cur_in:
                self.mic_combo.current(idx)
                break
        for idx, (i, _n) in enumerate(outputs):
            if i == cur_out:
                self.out_combo.current(idx)
                break
        self._fill_combo_defaults()

    def _fill_combo_defaults(self) -> None:
        """Подставить устройства из вкладки «Микрофон», если там выбраны."""
        st = self.studio
        try:
            if st.in_device is not None:
                for idx, (i, _n) in enumerate(self._inputs):
                    if i == st.in_device:
                        self.mic_combo.current(idx)
                        break
            if st.out_device is not None:
                for idx, (i, _n) in enumerate(self._outputs):
                    if i == st.out_device:
                        self.out_combo.current(idx)
                        break
        except Exception:
            pass

    def _sel_mic(self) -> int | None:
        v = self.mic_combo.get()
        if not v:
            return None
        try:
            return int(v.split(":")[0])
        except Exception:
            return None

    def _sel_out(self) -> int | None:
        v = self.out_combo.get()
        if not v:
            # список пуст — берём устройство с вкладки «Микрофон»
            return getattr(self.studio, "out_device", None)
        try:
            return int(v.split(":")[0])
        except Exception:
            return getattr(self.studio, "out_device", None)

    def _warn_if_cable_without_bridge(self) -> None:
        """Предупредить: выбран кабель, но мост выключен.

        В этом случае в кабель попадает только перевод, а твоя собственная
        речь с микрофона — нет. В Discord/игре микрофоном выбран «CABLE Output»,
        поэтому тебя не слышно вовсе.
        """
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            return
        idx = self._sel_out()
        if idx is None:
            return
        try:
            import sounddevice as sd
            name = sd.query_devices(idx)["name"].lower()
        except Exception:
            return
        if "cable" in name or "vb-audio" in name:
            self.state_lbl.config(
                text="Внимание: играем в кабель, но мост выключен — в кабель "
                     "идёт только перевод, твою речь микрофон не передаёт. "
                     "Включи «Мост в микрофон» на вкладке 3.",
                fg=WARN)

    # ---------- движок ----------
    def _ensure_engine(self) -> bool:
        if self.translator is not None and self.translator.ready:
            return True
        if self.translator is None:
            script = os.path.join(sp.workspace_tools(), "live_translate.py")
            ref = sp.output_paths()["reference"]
            if not os.path.exists(ref):
                self.state_lbl.config(
                    text="Нет образца голоса — запиши его на вкладке «2. Голос»",
                    fg=BAD)
                return False
            self.translator = lc.LiveTranslator(
                sp.engine_python(), script, ref,
                on_event=self._on_engine_event, on_text=self._on_engine_text)
        ok = self.translator.start()
        if not ok:
            self.state_lbl.config(text=self.translator.error or "движок не запустился",
                                  fg=BAD)
            return False
        self.state_lbl.config(text="движок загружает модели… (15–30 с)", fg=WARN)
        # Создаём провайдер входящего TTS после запуска движка
        if self._incoming_tts is None:
            bridge = getattr(self.studio, "bridge", None)
            self._incoming_tts = IncomingTTSProvider(
                self.translator, bridge,
                on_status=lambda msg: self.state_lbl.config(text=msg, fg=WARN))
        # Создаём captura источник (Этап A)
        if self._loopback_capture is None:
            self._loopback_capture = LoopbackCapture(
                on_pcm=self._on_loopback_pcm,
                on_status=self._on_capture_status,
                on_level=self._on_capture_level,
            )
        # Связываем TTS с capture для защиты от аудиопетель (Этап A1)
        if self._incoming_tts is not None and self._loopback_capture is not None:
            self._incoming_tts.set_capture(self._loopback_capture)
        return True

    def _diag_log(self, text: str) -> None:
        """Записать IPC-диагностическую строку в лог движка."""
        try:
            logs = os.path.join(sp.workspace(), "logs")
            os.makedirs(logs, exist_ok=True)
            with open(os.path.join(logs, "live_engine.log"), "a",
                      encoding="utf-8") as fh:
                fh.write(f"[gui] {text}\n")
                fh.flush()
        except Exception:
            pass

    def _on_engine_event(self, kind: str, data) -> None:
        st = self.studio
        if kind == "chunk":
            # перевод могли выключить, пока шёл синтез — такой чанки
            # слышать не надо (иначе испанский лезет поверх русского)
            if not self._out_enabled:
                return
            try:
                import base64
                pcm = lc.pcm_to_float16(base64.b64decode(data["pcm"]))
                self._emit_audio(pcm)
            except Exception:
                pass
        elif kind == "done":
            st.root.after(0, self._on_done)
            self._pump_queue()
            # пауза между фразами — иначе речь идёт слитно, без «воздуха»
            try:
                self._pause_between()
            except Exception:
                pass
            # движок прислал все чанки, но они ещё играют. Русский вернём
            # только когда очередь воспроизведения опустеет.
            if self._swap_busy:
                self._swap_wait_play = True
        elif kind == "lang":
            st.root.after(0, lambda d=data: self.state_lbl.config(
                text=f"язык перевода: {d.get('title', data.get('code', ''))}",
                fg=GOOD))
        elif kind == "state":
            if data.get("ready"):
                st.root.after(0, lambda: self.state_lbl.config(
                    text="готов: говори и отпускай кнопку", fg=GOOD))
                self._pump_queue()
                # сообщаем движку выбранный уровень живости
                self._push_liveliness()
                # и язык перевода (он мог быть выбран до запуска движка)
                self._on_lang()
                self._on_peer_lang()
            elif data.get("error"):
                st.root.after(0, lambda e=data["error"]: self.state_lbl.config(
                    text=f"ошибка движка: {e}", fg=BAD))
        elif kind == "peer_text":
            # что сказали другие игроки (перехват)
            st.root.after(0, lambda d=data: self._show_peer(d))
            # Также запускаем синтез входящего перевода (если включён)
            ru = str(data.get("ru", "") or "")
            lang = str(data.get("lang", "") or "ru")
            if self._incoming_tts is not None and ru:
                st.root.after(0, lambda t=ru, l=lang: self._incoming_tts.speak(t, l))
        elif kind == "incoming_chunk":
            if self._incoming_tts is not None:
                st.root.after(0, lambda d=data: self._incoming_tts.on_incoming_chunk(d))
        elif kind == "incoming_done":
            if self._incoming_tts is not None:
                st.root.after(0, lambda d=data: self._incoming_tts.on_incoming_done(d))
        elif kind == "log":
            text = str(data)
            low = text.lower()
            if any(k in low for k in ("error", "traceback", "exception", "нет модели")):
                self.studio.root.after(
                    0, lambda t=text[:160]: self.state_lbl.config(
                        text=f"движок: {t}", fg=BAD))
            else:
                self._last_engine_log = text[:160]

    def _on_engine_text(self, ru: str, es: str, tone: str = "") -> None:
        st = self.studio
        st.root.after(0, lambda: self._show_text(ru, es, tone))

    def _on_done(self) -> None:
        pass

    def _show_text(self, ru: str, es: str, tone: str = "") -> None:
        self._last_ru = ru
        self._last_es = es
        self.ru_lbl.config(text=ru or "—")
        self.es_lbl.config(text=es or "—")
        # оверлей поверх игры: игрок видит, что говорит его персонаж
        try:
            self.studio.overlay_show(ru, es)
        except Exception:
            pass
        # добавляем в историю переводов (боковая панель)
        sidebar = getattr(self.studio, "sidebar", None)
        if sidebar is not None and ru:
            try:
                sidebar.add_translation(ru, es, direction="out")
            except Exception:
                pass
        # показываем распознанный тон — видно, что эмоция поймана
        names = {"aggressive": "злой", "friendly": "добрый",
                 "energetic": "энергичный", "neutral": "ровный"}
        if tone and tone != "neutral":
            self.tone_lbl.config(text=f"тон: {names.get(tone, tone)}",
                                 fg=WARN)
        else:
            self.tone_lbl.config(text="")

    # ---------- горячие клавиши ----------
    def _hotkey_entry(self, parent, action: str, default: str) -> tk.Entry:
        """Поле, в котором пользователь назначает клавишу (нажми её)."""
        var = tk.StringVar(value=hk.pretty_combo(self._hotkeys.get(action, default)))
        entry = tk.Entry(parent, textvariable=var, width=16, justify="center",
                         bg="#1e2229", fg=FG, insertbackground=FG,
                         relief="flat", font=("Consolas", 10),
                         highlightthickness=1, highlightbackground="#2c313a")
        entry.pack(side="left", padx=(8, 0))
        entry.bind("<KeyPress>", lambda e, a=action, v=var: self._capture_key(e, a, v))
        entry.bind("<FocusIn>", lambda e, v=var: v.set("нажми…"))
        setattr(self, f"_hk_var_{action.replace(':', '_')}", var)
        setattr(self, f"_hk_entry_{action.replace(':', '_')}", entry)
        return entry

    def _capture_key(self, event, action: str, var: tk.StringVar) -> None:
        """Пользователь нажал клавишу — запоминаем комбинацию."""
        combo = hk.combo_from_event(event.keysym, event.state)
        if not combo:
            var.set("не поддерживается")
            return
        if combo == "escape":
            var.set(hk.pretty_combo(self._hotkeys.get(action, "")))
            return
        # некоторые клавиши Windows обрабатывает сама — глобальный хоткей
        # на них не придёт. Предупреждаем сразу, а не после «не работает».
        if combo in self._BAD_KEYS:
            self._hotkeys[action] = combo
            var.set(hk.pretty_combo(combo))
            self._save_hotkeys()
            self.hk_status.config(
                text=f"{hk.pretty_combo(combo)} не работает как хоткей "
                     f"(Windows обрабатывает её сам) — выбери другую",
                fg=WARN)
            return
        self._hotkeys[action] = combo
        var.set(hk.pretty_combo(combo))
        self._save_hotkeys()
        self.hk_status.config(
            text=f"назначено: {hk.pretty_combo(combo)} — нажми «Включить горячие клавиши»",
            fg=DIM)

    @staticmethod
    def _pretty_key(key: str) -> str:
        return {"space": "Пробел", "enter": "Enter", "tab": "Tab",
                "escape": "Esc", "backspace": "Backspace"}.get(key, key.upper())

    def _hotkeys_path(self) -> str:
        return os.path.join(sp.workspace(), HOTKEY_FILE)

    def _load_hotkeys(self) -> None:
        import json
        path = self._hotkeys_path()
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            known = {ACT_CONT, ACT_TALK}
            if isinstance(data, dict):
                # берём только известные действия: в файле может лежать
                # что-то от прежней версии (например «live:swap»)
                self._hotkeys.update({k: v for k, v in data.items()
                                       if k in known
                                       and isinstance(v, str) and v})
        except Exception:
            pass

    def _save_hotkeys(self) -> None:
        import json
        try:
            with open(self._hotkeys_path(), "w", encoding="utf-8") as fh:
                json.dump(self._hotkeys, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _reset_hotkeys(self) -> None:
        self._hotkeys = {ACT_CONT: "ctrl+alt+l", ACT_TALK: "ctrl+alt+t"}
        for action, var_name in ((ACT_CONT, "_hk_var_live_cont"),
                                 (ACT_TALK, "_hk_var_live_talk")):
            var = getattr(self, var_name, None)
            if var is not None:
                var.set(hk.pretty_combo(self._hotkeys[action]))
        self._save_hotkeys()
        self.hk_status.config(text="сброшено: Ctrl+Alt+T, Ctrl+Alt+L")

    def _on_liveliness(self, value=None) -> None:
        """Ползунок «Живость голоса»: 0 — ровно, 3 — максимум жизни.

        Уровень передаётся движку и сдвигает параметры синтеза.
        """
        try:
            level = int(float(self.liveliness.get()))
        except Exception:
            level = 2
        self._liveliness = max(0, min(3, level))
        self.studio.root.after(0, self._push_liveliness)

    def _push_liveliness(self) -> None:
        """Передать уровень живости движку (через команду в stdin)."""
        t = self.translator
        if t is None or not t.ready:
            return
        try:
            t.set_liveliness(self._liveliness)
        except Exception:
            pass

    def _lang_code(self) -> str:
        """Код выбранного языка перевода (es по умолчанию)."""
        value = self.lang_combo.get() if hasattr(self, "lang_combo") else ""
        return value.split(":")[0].strip() if value else "es"

    def _on_lang(self, _event=None) -> None:
        """Сменили язык перевода: сообщаем движку и обновляем подписи."""
        code = self._lang_code()
        title = core.lang_title(code)
        self.es_cap.config(text=f"Звучит ({code.upper()}):")
        t = self.translator
        if t is None or not t.ready:
            self.state_lbl.config(text=f"язык: {title} — включи перевод, "
                                       f"чтобы заговорить", fg=DIM)
            return
        self.state_lbl.config(text=f"переключаю язык: {title}…", fg=WARN)
        if t.set_lang(code):
            self.state_lbl.config(text=f"язык перевода: {title}", fg=GOOD)

    # ---------- перехват речи других игроков ----------
    def _refresh_peer_devices(self) -> None:
        """Список устройств, с которых можно снять звук игры.

        Первым идёт «Стерео микшер» (Stereo Mix) — он пишет ВСЁ, что
        играет в наушниках, то есть ровно то, что нужно для перехвата
        речи игроков. CABLE Output пишет только то, что уходит в кабель,
        поэтому он ниже.
        """
        devs = []
        try:
            import sounddevice as sd
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] <= 0:
                    continue
                name = str(d["name"])
                low = name.lower()
                if "стерео микшер" in low or "stereo mix" in low:
                    rank = 0        # главный источник звука игры
                elif ("cable output" in low or "loopback" in low
                      or "what u hear" in low or "what you hear" in low
                      or "запись" in low or "monitor" in low):
                    rank = 1
                elif "virtual" in low or "point" in low:
                    rank = 2
                else:
                    continue
                devs.append((rank, i, name))
        except Exception:
            devs = []
        devs.sort(key=lambda x: (x[0], x[1]))
        self._peer_devices = [(i, n) for _r, i, n in devs]
        # peer_combo больше не используется в UI (заменён на capture_device_combo),
        # но метод вызывается из poll() — защищаем от AttributeError
        if hasattr(self, "peer_combo") and self.peer_combo is not None:
            self.peer_combo["values"] = [f"{i}: {n}" for i, n in self._peer_devices]
            if self._peer_devices:
                self.peer_combo.current(0)
            else:
                self.peer_combo["values"] = ["— нет устройства записи —"]
                self.peer_combo.current(0)

    def _peer_device(self) -> int | None:
        value = self.peer_combo.get()
        try:
            return int(value.split(":")[0])
        except Exception:
            return None

    def _toggle_peer(self) -> None:
        """Включить/выключить перехват речи других игроков.
        
        Состояния: OFF -> STARTING -> ACTIVE -> STOPPING -> OFF
                           \-> ERROR (на ошибку) -> OFF (после показа)
        """
        if self._peer_state == "OFF":
            self._start_peer()
        elif self._peer_state in ("ACTIVE", "STARTING"):
            self._stop_peer()
        elif self._peer_state == "ERROR":
            # Переход из ошибки: сброс и новая попытка
            self._peer_state = "OFF"
            self._peer_state_ts = 0.0
            self._start_peer()

    def _set_peer_state(self, state: str) -> None:
        """Установить состояние перехвата и обновить UI."""
        old = self._peer_state
        self._peer_state = state
        self._peer_state_ts = time.time()
        # Логируем смену состояния
        self._diag_log(f"peer_state: {old} -> {state}")
        # Обновляем чекбокс БЕЗ сброса пользовательского выбора
        if state == "ACTIVE":
            self.peer_on.set(True)
        elif state == "OFF":
            self.peer_on.set(False)
        # В состояниях STARTING/STOPPING/ERROR чекбокс оставляем как есть
        # (пользователь видит, что процесс идёт или была ошибка)

    def _start_peer(self) -> None:
        """Запуск перехвата: OFF -> STARTING -> ACTIVE или ERROR."""
        if self._peer_state in ("STARTING", "ACTIVE"):
            return
        if not self._ensure_engine():
            self._set_peer_state("ERROR")
            self.peer_status.config(
                text="движок не запущен — нажми «ЗАЖАТЬ И ГОВОРИТЬ»", fg=BAD)
            return
        idx = self._peer_device()
        if idx is None:
            self._set_peer_state("ERROR")
            self.peer_status.config(
                text="нет устройства записи (нужен Stereo Mix / CABLE Output)", fg=BAD)
            return
        self._peer_pending_device = idx
        self._set_peer_state("STARTING")
        self.peer_status.config(text="подключение…", fg=WARN)
        
        # Сброс буферов
        self._peer_buf = []
        self._peer_silence = 0.0
        self._peer_has_speech = False
        self._peer_strong = 0
        self._peer_rms = []
        
        # Частота записи
        rate = SR_PEER
        try:
            import sounddevice as sd
            native = int(sd.query_devices(idx)["default_samplerate"])
            if native > 0:
                rate = native
        except Exception:
            pass
        self._peer_rate = rate
        
        try:
            import sounddevice as sd
            self._peer_stream = sd.InputStream(
                device=idx, channels=1, samplerate=rate, dtype="float32",
                blocksize=int(rate * BLOCK_SEC), callback=self._peer_callback)
            self._peer_stream.start()
            # Engine confirmation: peer loop уже работает в движке (started on load)
            # Дополнительная диагностика: логируем старт
            self._diag_log(f"peer_started: device={idx}, rate={rate}")
            self._set_peer_state("ACTIVE")
            self.peer_status.config(text="слушаю игроков…", fg=GOOD)
            self.studio.root.after(400, self._peer_meter)
        except Exception as exc:  # noqa: BLE001
            self._peer_stream = None
            self._set_peer_state("ERROR")
            self.peer_status.config(text=f"не открылось: {exc}", fg=BAD)
            self._diag_log(f"peer_start_failed: {exc}")

    def _stop_peer(self) -> None:
        """Остановка перехвата: ACTIVE/STARTING -> STOPPING -> OFF."""
        if self._peer_state == "OFF":
            return
        self._set_peer_state("STOPPING")
        self.peer_status.config(text="остановка…", fg=WARN)
        
        stream = self._peer_stream
        self._peer_stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        
        self._peer_buf = []
        self._peer_pending_device = None
        self._diag_log("peer_stopped")
        self._set_peer_state("OFF")
        self.peer_status.config(text="выключен", fg=DIM)

    def _peer_meter(self) -> None:
        """Индикатор уровня захвата.
        
        Работает только в состоянии ACTIVE. Если уровень нулевой — источник
        не слышит игру (чаще всего игра идёт в USB-гарнитуру, у которой в
        Windows нет петли). Показываем это прямо, чтобы пользователь не гадал.
        """
        if self._peer_state != "ACTIVE" or self._peer_stream is None:
            return
        level = float(self._peer_level)
        bar = "█" * min(20, int(level * 400))
        if level > 0.01:
            self.peer_status.config(text=f"уровень {level:.3f} {bar}", fg=GOOD)
        elif level > 0.001:
            self.peer_status.config(text=f"уровень {level:.4f} (тихо)", fg=WARN)
        else:
            self.peer_status.config(
                text="уровень 0 — источник молчит (нужна петля: «Стерео микшер» "
                     "или CABLE)", fg=BAD)
        self.studio.root.after(400, self._peer_meter)

    def _peer_callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG001
        """Колбэк записи игры: режем на фрагменты по паузам.
        
        Работает только в состоянии ACTIVE. При потере устройства (stream
        закрылся) падает в ERROR и показывает причину.
        """
        if self._peer_state != "ACTIVE" or self._peer_stream is None:
            return
        try:
            block = indata[:, 0].copy()
        except Exception:
            return
        rms = float(np.sqrt((block.astype(np.float64) ** 2).mean()))
        self._peer_level = rms
        self._peer_rms.append(rms)
        if len(self._peer_rms) > 240:
            self._peer_rms.pop(0)
        floor = float(np.percentile(self._peer_rms, 20)) if self._peer_rms else 0.0
        thr = max(floor * 2.5, 0.01)
        if rms > thr:
            self._peer_has_speech = True
            self._peer_silence = 0.0
            if rms > thr * 1.4:
                self._peer_strong += 1
        else:
            self._peer_silence += BLOCK_SEC
        self._peer_buf.append(block)
        if self._peer_silence >= SILENCE_END and self._peer_has_speech:
            self._flush_peer()
            return
        if len(self._peer_buf) * BLOCK_SEC >= MAX_SEG:
            self._flush_peer()

    def _flush_peer(self) -> None:
        """Отдать фрагмент звука игры движку на разбор речи."""
        buf = self._peer_buf
        self._peer_buf = []
        had = self._peer_has_speech
        strong = self._peer_strong
        self._peer_has_speech = False
        self._peer_strong = 0
        self._peer_silence = 0.0
        if not buf or not had or strong < 3:
            return
        audio = np.concatenate(buf)
        dur = len(audio) / self._peer_rate
        if dur < 0.5:
            return
        # приводим к 16 кГц — так Whisper в движке работает точнее
        audio16 = lc.resample_to_16k(audio, self._peer_rate)
        t = self.translator
        if t is None or not t.ready:
            return
        try:
            t.send_peer_pcm(audio16, 16000)
        except Exception:
            pass

    def _on_peer_lang(self, _event=None) -> None:
        """Язык чужой речи: авто или конкретный."""
        code = self.peer_lang_combo.get().strip()
        code = "" if code == "авто" else code
        t = self.translator
        if t is not None and t.ready:
            t.set_peer_lang(code or "auto")

    def _show_peer(self, data: dict) -> None:
        """Показать, что сказали другие игроки (и перевод на русский)."""
        src = str(data.get("src", "") or "")
        ru = str(data.get("ru", "") or "")
        lang = str(data.get("lang", "") or "")
        if not src:
            return
        text = f"{src}" + (f"\n→ {ru}" if ru and ru != src else "")
        self.peer_lbl.config(text=text)
        self.peer_cap.config(text=f"Другие игроки ({lang.upper()}):")
        # и в оверлей поверх игры
        try:
            self.studio.overlay_peer(src, ru)
        except Exception:
            pass
        # добавляем в историю переводов (боковая панель)
        sidebar = getattr(self.studio, "sidebar", None)
        if sidebar is not None and src:
            try:
                sidebar.add_translation(src, ru, direction="in")
            except Exception:
                pass

    # ---------- захват входящего звука (Этап A) ----------

    def _on_capture_mode_change(self) -> None:
        """Сменился режим захвата — обновить список устройств."""
        self._refresh_capture_devices()

    def _refresh_capture_devices(self) -> None:
        """Обновить список устройств/процессов для выбранного режима захвата."""
        mode = CaptureMode(self.capture_mode.get())
        self.capture_device_combo["values"] = []
        self.capture_device_combo.set("")

        if mode == CaptureMode.LEGACY_INPUT:
            devices = list_input_devices()
            self.capture_device_combo["values"] = [
                f"{d['index']}: {d['name']}" for d in devices
            ]
            self.capture_info.config(
                text="Захват с реального input устройства (Stereo Mix, CABLE Output). "
                     "Оригинальный звук остаётся в наушниках."
            )
        elif mode == CaptureMode.WASAPI_ENDPOINT:
            devices = list_output_devices_with_loopback()
            self.capture_device_combo["values"] = [
                f"{d['index']}: {d['name']} → Loopback [{d['loopback_index']}]"
                if d["loopback_index"] is not None else
                f"{d['index']}: {d['name']} (нет loopback)"
                for d in devices
            ]
            self.capture_info.config(
                text="WASAPI Endpoint Loopback через PyAudioWPatch. "
                     "Захват копии звука с устройства вывода. "
                     "Оригинальный звук остаётся в наушниках."
            )
        elif mode == CaptureMode.PROCESS_LOOPBACK:
            procs = list_running_processes()
            self.capture_device_combo["values"] = [
                f"{p['name']} (PID {p['pid']})" for p in procs[:20]
            ]
            self.capture_info.config(
                text="Process Loopback для выбранного процесса. Требует нативного C++ helper. "
                     "Оригинальный звук остаётся в наушниках."
            )

        if self.capture_device_combo["values"]:
            self.capture_device_combo.current(0)

    def _toggle_capture(self) -> None:
        """Включить/выключить захват входящего звука."""
        if not self.capture_on.get():
            self._start_capture()
        else:
            self._stop_capture()

    def _start_capture(self) -> None:
        if self._loopback_capture is None:
            self.state_lbl.config(text="захват не инициализирован", fg=BAD)
            return

        mode = CaptureMode(self.capture_mode.get())

        # Получить индекс устройства из комбобокса
        value = self.capture_device_combo.get()
        device_idx = None
        loopback_idx = None
        if value:
            try:
                device_idx = int(value.split(":")[0])
            except Exception:
                device_idx = None
            # Для WASAPI_ENDPOINT извлечь loopback индекс из "[Loopback N]"
            if mode == CaptureMode.WASAPI_ENDPOINT:
                try:
                    lb_part = value.split("Loopback [")[1].split("]")[0]
                    loopback_idx = int(lb_part)
                except Exception:
                    loopback_idx = None

        self._loopback_capture.set_mode(mode)
        # WASAPI Endpoint использует loopback индекс, Legacy — физический
        capture_idx = loopback_idx if mode == CaptureMode.WASAPI_ENDPOINT else device_idx
        self._loopback_capture.set_device(capture_idx)

        if self._loopback_capture.start():
            self.capture_on.set(True)
            self.capture_btn.config(text="Выключить захват", bg="#8a2f2f")
            self._poll_capture_meter()
        else:
            self.state_lbl.config(
                text=f"захват не запущен: {self._loopback_capture.get_status_message()}",
                fg=BAD,
            )

    def _stop_capture(self) -> None:
        if self._loopback_capture is not None:
            self._loopback_capture.stop()
        self.capture_on.set(False)
        self.capture_btn.config(text="Включить захват", bg="#2b3a4d")
        self.capture_status.config(text="выключен", fg=DIM)
        self.capture_meter.config(text="")

    def _test_capture(self) -> None:
        """Проверка захвата без запуска連続ного режима."""
        if self._loopback_capture is None:
            self.state_lbl.config(text="захват не инициализирован", fg=BAD)
            return
        mode = CaptureMode(self.capture_mode.get())
        diag = {
            CaptureMode.LEGACY_INPUT: "Проверьте, что выбрано устройство со Stereo Mix / CABLE Output.",
            CaptureMode.WASAPI_ENDPOINT: "WASAPI Endpoint Loopback требует нативного helper (порт audio с loopback flag).",
            CaptureMode.PROCESS_LOOPBACK: "Process Loopback требует нативного C++ helper (WASAPI Process Loopback API).",
        }
        self.state_lbl.config(text=diag.get(mode, "неизвестный режим"), fg=WARN)

    def _on_loopback_pcm(self, pcm_bytes: bytes, sr: int) -> None:
        """PCM из захвата собеседника — отправить на ASR → MT → TTS."""
        t = self.translator
        if t is None or not t.ready:
            return
        try:
            t.send_peer_pcm(pcm_bytes, sr)
        except Exception:
            pass

    def _on_capture_status(self, status, message: str) -> None:
        """Callback изменения статуса захвата."""
        self.studio.root.after(0, lambda: self._update_capture_status(status, message))

    def _update_capture_status(self, status, message: str) -> None:
        self.capture_status.config(text=message,
                                   fg=GOOD if status == "active" else DIM)
        if status == "error":
            self.state_lbl.config(text=f"захват: {message}", fg=BAD)

    def _on_capture_level(self, level: float) -> None:
        """Callback уровня сигнала захвата."""
        self.studio.root.after(0, lambda: self._update_capture_meter(level))

    def _update_capture_meter(self, level: float) -> None:
        bar = "█" * min(20, int(level * 400))
        self.capture_meter.config(text=f"{level:.4f} {bar}")

    def _poll_capture_meter(self) -> None:
        """Опрос метра захвата."""
        if self._loopback_capture is not None and self._loopback_capture.is_running():
            self._update_capture_meter(self._loopback_capture.get_level())
            self.studio.root.after(200, self._poll_capture_meter)

    # ---------- API для нового UI (управление захватом) ----------

    def get_capture_modes(self) -> list[tuple[str, str, bool]]:
        """Вернуть доступные режимы захвата: (код, метка, доступен)."""
        modes = []
        for value, label, _key in [
            (CaptureMode.LEGACY_INPUT.value,
             "Устройство записи (Stereo Mix / CABLE Output)", True),
            (CaptureMode.WASAPI_ENDPOINT.value,
             "Устройство вывода (WASAPI Loopback)", True),
            (CaptureMode.PROCESS_LOOPBACK.value,
             "Процесс (Discord, RedM/FiveM)", False),
        ]:
            modes.append((value, label, _key))
        return modes

    def get_capture_devices(self, mode: str) -> list[dict]:
        """Вернуть устройства для указанного режима захвата.

        Каждый элемент: {"index": int, "name": str,
        "loopback_index": int | None}.
        """
        try:
            self.capture_mode.set(mode)
        except Exception:
            pass
        self._refresh_capture_devices()
        values = self.capture_device_combo["values"]
        result: list[dict] = []
        for v in values:
            try:
                idx = int(v.split(":")[0])
            except Exception:
                continue
            name = v.split(":", 1)[1].strip() if ":" in v else v
            loopback_idx = None
            if "Loopback [" in v:
                try:
                    lb_part = v.split("Loopback [")[1].split("]")[0]
                    loopback_idx = int(lb_part)
                except Exception:
                    pass
            result.append({
                "index": idx,
                "name": name,
                "loopback_index": loopback_idx,
            })
        return result

    def set_capture_mode(self, mode: str) -> None:
        """Установить режим захвата из настроек."""
        try:
            self.capture_mode.set(mode)
        except Exception:
            return
        self._on_capture_mode_change()

    def set_capture_device(self, device_index: int,
                           loopback_idx: int | None = None) -> None:
        """Установить устройство захвата из настроек."""
        mode = CaptureMode(self.capture_mode.get())
        self._loopback_capture.set_mode(mode)
        capture_idx = (loopback_idx
                       if mode == CaptureMode.WASAPI_ENDPOINT
                       else device_index)
        self._loopback_capture.set_device(capture_idx)
        # Обновить комбобокс
        try:
            for i in range(len(self.capture_device_combo["values"])):
                v = self.capture_device_combo["values"][i]
                if v.startswith(f"{device_index}:"):
                    self.capture_device_combo.current(i)
                    break
        except Exception:
            pass

    def start_capture(self) -> tuple[bool, str]:
        """Запустить захват входящего звука.

        Возвращает (ok, message).
        """
        if self.capture_on.get():
            return True, "захват уже запущен"
        if self._loopback_capture is None:
            self._ensure_engine()
            if self._loopback_capture is None:
                return False, "захват не инициализирован"
        ok = self._loopback_capture.start()
        if not ok:
            return False, self._loopback_capture.get_status_message()
        self.capture_on.set(True)
        return True, "захват запущен"

    def stop_capture(self) -> None:
        """Остановить захват входящего звука."""
        if self.capture_on.get():
            self._toggle_capture()

    def get_capture_status(self) -> dict:
        """Вернуть статус захвата для UI."""
        if self._loopback_capture is None:
            return {
                "state": "OFF",
                "error": "",
                "level": 0.0,
                "running": False,
                "mode": None,
            }
        return {
            "state": self._loopback_capture.get_status().value,
            "error": self._loopback_capture.get_status_message(),
            "level": self._loopback_capture.get_level(),
            "running": self._loopback_capture.is_running(),
            "mode": (self._loopback_capture._mode.value
                     if self._loopback_capture._mode else None),
        }

    def _toggle_incoming(self) -> None:
        """Включить/выключить входящий TTS (озвучка в наушники)."""
        on = bool(self.incoming_on.get())
        if self._incoming_tts is not None:
            # Обновляем ссылку на мост (мог быть создан после провайдера)
            bridge = getattr(self.studio, "bridge", None)
            self._incoming_tts.set_bridge(bridge)
            self._incoming_tts.set_enabled(on)
        self.incoming_status.config(
            text="вкл" if on else "выключен",
            fg=GOOD if on else DIM)
        if on:
            self.state_lbl.config(text="входящий перевод: озвучка в наушники", fg=GOOD)

    def _on_incoming_voice(self, _event=None) -> None:
        """Выбор голосового профиля для входящего перевода."""
        if self._incoming_tts is not None:
            profile = self.incoming_voice_combo.get()
            self._incoming_tts.set_voice_profile(profile if profile else None)

    def _on_incoming_vol(self, value=None) -> None:
        """Громкость входящего перевода в наушниках (0-100%)."""
        try:
            vol = float(self.incoming_vol.get()) / 100.0
        except Exception:
            vol = 0.8
        if self._incoming_tts is not None:
            self._incoming_tts.set_volume(vol)

    def _toggle_only_es(self) -> None:
        """Переключатель «только испанский в кабеле»."""
        self._mute_ru = bool(self.only_es.get())
        self._apply_mute()

    def _toggle_overlay(self) -> None:
        """Включить/выключить оверлей с текстом поверх игры."""
        on = bool(self.overlay_on.get())
        try:
            status = self.studio.toggle_overlay(on)
        except Exception as exc:  # noqa: BLE001
            status = f"ошибка: {exc}"
        self.overlay_lbl.config(text=status)
        if not on:
            self.overlay_on.set(False)

    def _on_monitor_vol(self, value=None) -> None:
        """Громкость перевода в наушниках."""
        try:
            vol = float(self.monitor_vol.get()) / 100.0
        except Exception:
            vol = 0.8
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            bridge.monitor_gain = vol

    def _toggle_hotkeys(self) -> None:
        """Включить/выключить глобальные хоткеи живого перевода."""
        if self.hotkeys_on:
            self.studio.hotkeys.unregister_prefix("live:")
            self.studio.hotkey_enabled = bool(
                self.studio.hotkeys.registered("phrase:"))
            self.hotkeys_on = False
            self.hk_btn.config(text="⌨ Включить горячие клавиши", bg="#2c313a", fg=FG)
            self.hk_status.config(text="выключены")
            return

        key_cont = self._hotkeys.get(ACT_CONT, "ctrl+alt+l")
        key_talk = self._hotkeys.get(ACT_TALK, "ctrl+alt+t")
        # снимаем ТОЛЬКО свои хоткеи — хоткеи фраз не трогаем
        self.studio.hotkeys.unregister_prefix("live:")
        # Регистрируем по очереди: если клавиша занята другой программой,
        # подбираем запасную (и говорим пользователю, какую именно).
        actual: dict[str, str] = {}
        failed: list[str] = []
        for action, key in ((ACT_TALK, key_talk), (ACT_CONT, key_cont)):
            if not key:
                failed.append(action)
                continue
            if self.studio.hotkeys.register(key, action, 0):
                actual[action] = key
                continue
            # клавиша занята — ищем запасную
            spare = self._find_spare_key(action)
            if spare:
                actual[action] = spare
            else:
                failed.append(action)
        self.studio.hotkeys.start()
        self.studio.hotkey_enabled = True
        self.hotkeys_on = True
        self.hk_btn.config(text="⌨ Выключить горячие клавиши", bg="#c0392b", fg="#fff")
        # показываем пользователю РЕАЛЬНЫЕ клавиши (а не запрошенные)
        for action, key in actual.items():
            if key != self._hotkeys.get(action):
                self._hotkeys[action] = key
                var = getattr(self, f"_hk_var_{action.replace(':', '_')}", None)
                if var is not None:
                    var.set(hk.pretty_combo(key))
        self._save_hotkeys()
        # запоминаем VK клавиши «Говорить» — по нему следим за отпусканием
        self._hold_vk = hk.vk_of(actual.get(ACT_TALK, key_talk))
        # пишем в журнал, какие клавиши реально зарегистрировались:
        # в EXE нет консоли, а по этой записи видно, занята клавиша или нет
        self._log_hotkeys(actual.get(ACT_CONT, key_cont),
                          actual.get(ACT_TALK, key_talk), failed)
        if failed:
            names = {"live:cont": "непрерывно", "live:talk": "говорить"}
            what = ", ".join(names.get(f, f) for f in failed)
            err = getattr(self.studio.hotkeys, "_last_error", 0)
            # 1409 = ERROR_HOTKEY_ALREADY_REGISTERED: клавишу держит другая
            # программа (Discord, Steam, игра). Пользователю нужно это знать.
            why = (" (занята другой программой)" if err == 1409
                   else f" (код Windows {err})" if err else "")
            self.hk_status.config(
                text=f"не сработала: {what}{why} — назначь другую клавишу",
                fg=BAD)
        else:
            parts = []
            for action, key in ((ACT_TALK, actual.get(ACT_TALK, key_talk)),
                                (ACT_CONT, actual.get(ACT_CONT, key_cont))):
                names = {"live:cont": "непрерывно", "live:talk": "говорить"}
                parts.append(f"{hk.pretty_combo(key)} {names[action]}")
            self.hk_status.config(text="включены: " + ", ".join(parts), fg=GOOD)

    # Клавиши, которые НЕЛЬЗЯ назначать: они не доходят до глобальных
    # хоткеев (Windows обрабатывает их сама) или ломают работу в игре.
    _BAD_KEYS = {"printscreen", "win", "tab", "escape", "f12"}

    # Запасные клавиши для автоподбора (проверены: доходят до WM_HOTKEY).
    _SPARE_KEYS = ("ctrl+alt+g", "ctrl+alt+b", "ctrl+alt+n", "ctrl+alt+v",
                   "f9", "f10", "f11", "pause", "insert", "home", "end",
                   "pageup", "pagedown", "up", "down", "left", "right")

    def _find_spare_key(self, action: str) -> str:
        """Найти свободную клавишу для действия (если назначенная занята)."""
        used = set(self._hotkeys.values())
        for cand in self._SPARE_KEYS:
            if cand in used or cand in self._BAD_KEYS:
                continue
            if self.studio.hotkeys.register(cand, action, 0):
                return cand
        return ""

    def _log_hotkeys(self, cont: str, talk: str, failed: list[str]) -> None:
        """Записать в журнал, какие горячие клавиши включились (а какие нет)."""
        try:
            import time as _time
            logs = os.path.join(sp.workspace(), "logs")
            os.makedirs(logs, exist_ok=True)
            names = {"live:cont": "непрерывно", "live:talk": "говорить"}
            ok = [f"{names.get(a, a)}={k}" for a, k in
                  (("live:cont", cont), ("live:talk", talk))
                  if a not in failed]
            bad = [names.get(f, f) for f in failed]
            with open(os.path.join(logs, "hotkey_events.log"), "a",
                      encoding="utf-8") as fh:
                err = getattr(self.studio.hotkeys, "_last_error", 0)
                fh.write(f"{_time.strftime('%H:%M:%S')} РЕГИСТРАЦИЯ: "
                         f"включены [{', '.join(ok)}]"
                         + (f"; НЕ Сработали [{', '.join(bad)}]" if bad else "")
                         + (f"; Win32 err={err}" if bad else "")
                         + "\n")
                fh.flush()
        except Exception:
            pass

    def on_hotkey(self, action: str) -> None:
        """Вызвано из глобального хоткея (в главном потоке GUI).

        «Говорить» работает как ЗАЖАТЬ: нажали — русский заглушён, идёт
        испанский; отпустили — русский вернулся. Отпускание ловим по
        GetAsyncKeyState в _check_hold().
        """
        if action == ACT_CONT:
            self._toggle_cont()
        elif action == ACT_TALK:
            if self._hold_on:
                self._stop_hold()
            else:
                self._start_hold()

    def _switch_language(self) -> None:
        """Переключатель языка: русский -> испанский.

        Оставлено для совместимости: новая схема — зажать кнопку
        «Говорить» (см. _start_hold/_stop_hold).
        """
        bridge = getattr(self.studio, "bridge", None)
        if bridge is None or not getattr(bridge, "running", False):
            self.state_lbl.config(
                text="Переключатель языка работает с мостом. Включи мост "
                     "(вкладка 3) — он приглушает микрофон и подставляет перевод.",
                fg=WARN)
            return

        if self._swap_busy:
            # повторное нажатие — отменяем озвучку
            self._stop_translation()
            self.state_lbl.config(text="перевод отменён", fg=DIM)
            return

        if not self._ensure_engine():
            return

        # что он сказал только что
        audio = bridge.recent_audio(8.0)
        if audio.size == 0:
            self.state_lbl.config(text="микрофон молчит — нечего переводить", fg=WARN)
            return
        # частота именно этого аудио (мост может работать на 48 кГц, а не 44.1)
        sr = self._mic_rate(audio)
        # переводим ТОЛЬКО последнюю фразу (по паузе) — иначе распознаётся
        # 6 секунд подряд и испанский приходит через 2 лишних секунды
        audio = self._last_phrase(audio, sr)
        if audio.size == 0:
            self.state_lbl.config(text="не расслышал последнюю фразу", fg=WARN)
            return

        # русский пропадает СЕЙЧАС, перевод будет через ~0.4 с
        self._swap_busy = True
        self._out_enabled = True
        self._apply_mute()
        self.state_lbl.config(text="перевожу на испанский…", fg=WARN)
        self._swap_sr = sr
        # floor=0: это заведомо речь (только что снято с микрофона) —
        # отсекать её по порогу шума не нужно
        self._queue_translate(audio, self._swap_sr, floor=0.0)
        # страховка: если движок не ответил — русский вернётся сам
        self.studio.root.after(8000, self._swap_timeout)

    def _swap_timeout(self) -> None:
        """Перевод не пришёл за 8 с — возвращаем русский голос."""
        if self._swap_busy and not self._swap_wait_play:
            self._swap_finished()

    def _mic_rate(self, audio: np.ndarray) -> int:
        """Частота микрофона моста (аудио пришло из него)."""
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            return getattr(bridge, "sr", SR_REC)
        return SR_REC

    @staticmethod
    def _last_phrase(audio: np.ndarray, sr: int = SR_REC) -> np.ndarray:
        """Оставить только последнюю фразу: обрезать по последней паузе.

        Без этого в перевод уходят все 8 секунд буфера, и испанский
        приходит на пару секунд позже, чем хочется.
        """
        if audio.size == 0:
            return audio
        win = max(1, int(sr * 0.03))
        n = len(audio) // win
        if n < 4:
            return audio
        frames = audio[:n * win].reshape(n, win)
        energy = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
        peak = float(energy.max())
        if peak <= 0:
            return audio
        thr = max(peak * 0.18, 0.004)
        loud = energy > thr
        if not loud.any():
            return audio
        # ищем последнюю паузу ДЛИННОЙ хотя бы 0.25 с перед последней фразой
        last_speech = int(np.where(loud)[0][-1])
        pause_min = max(1, int(0.25 / 0.03))
        cut = 0
        run = 0
        for i in range(last_speech - 1, -1, -1):
            if not loud[i]:
                run += 1
                if run >= pause_min:
                    cut = i + run
                    break
            else:
                run = 0
        if cut <= 0:
            return audio
        return audio[cut * win:]

    def _swap_finished(self) -> None:
        """Перевод дозвучал — возвращаем русский голос."""
        self._swap_busy = False
        self._out_enabled = False
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            # если включён режим «только испанский», русский не возвращаем
            bridge.set_duck(self._mute_ru)
        self.state_lbl.config(text="готов: говори по-русски", fg=GOOD)

    # ---------- очередь на перевод ----------
    def _queue_translate(self, pcm: np.ndarray, sr: int = SR_REC,
                         floor: float | None = None) -> None:
        """Отдать аудио на перевод.

        Вызывается из потока микрофона, поэтому ТОЛЬКО кладём в очередь:
        никаких обращений к tkinter отсюда (это не главный поток).
        """
        if self.translator is None:
            self.studio.root.after(
                0, lambda: self.state_lbl.config(text="движок не запущен", fg=BAD))
            return
        with self._queue_lock:
            self._queue.append((pcm, sr, floor))
        # отправку делаем в главном потоке
        self.studio.root.after(0, self._pump_queue)

    def _pump_queue(self) -> None:
        """Отправить следующий запрос, если движок свободен (главный поток)."""
        t = self.translator
        if t is None or not t.ready or t.busy:
            return
        with self._queue_lock:
            if not self._queue:
                return
            pcm, sr, floor = self._queue.pop(0)
        if floor is None:
            floor = self._noise
        if t.translate_pcm(pcm, sr, floor):
            self.state_lbl.config(text="перевожу…", fg=WARN)

    # ---------- ГЛАВНОЕ: ЗАЖАТЬ (русский -> испанский) ----------
    def _hold_press(self, event=None) -> None:
        """Кнопку нажали: русский заглушаем, начинаем говорить."""
        self._start_hold()

    def _hold_release(self, event=None) -> None:
        """Кнопку отпустили: досылаем последнюю фразу, русский вернётся."""
        self._stop_hold()

    def _start_hold(self) -> None:
        """Зажали: русский в кабеле заглушён, идёт испанский перевод.

        Фразы отправляются на лету (по паузам в речи), поэтому испанский
        появляется ещё пока кнопку держишь.
        """
        if self._hold_on:
            return
        if self._cont_on:
            self.state_lbl.config(text="сначала выключи «Непрерывно»", fg=WARN)
            return
        if not self._ensure_engine():
            return
        idx = self._sel_mic()
        if idx is None:
            self.state_lbl.config(text="выбери микрофон", fg=BAD)
            return

        self._hold_on = True
        self._out_enabled = True
        self._cont_buf = []
        self._cont_silence = 0.0
        self._cont_has_speech = False
        self._strong_blocks = 0
        self._noise = 0.005
        self.hold_btn.config(text="🎤  ГОВОРИ…  (отпусти)", bg="#8a2f2f")
        self.state_lbl.config(text="говорю — в кабель идёт испанский", fg=WARN)

        # русский глушим СРАЗУ, до первого слова перевода
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            bridge.set_duck(True)

        try:
            self._stream = self._open_input(idx, self._cont_callback)
            self._stream.start()
        except Exception as exc:  # noqa: BLE001
            self._hold_on = False
            self._out_enabled = False
            self.hold_btn.config(text="🎤  ЗАЖАТЬ И ГОВОРИТЬ", bg="#1e6f3f")
            self.state_lbl.config(text=f"микрофон не открылся: {exc}", fg=BAD)

    def _stop_hold(self) -> None:
        """Отпустили: досылаем последнюю фразу, русский вернётся.

        Русский возвращается не сразу, а когда испанский договорит —
        иначе русский наложился бы на испанский.
        """
        if not self._hold_on:
            return
        self._hold_on = False
        self.hold_btn.config(text="🎤  ЗАЖАТЬ И ГОВОРИТЬ", bg="#1e6f3f")
        self._close_input()
        # дослать последнюю фразу (то, что не успели разделить по паузам)
        self._flush_segment()
        self.state_lbl.config(text="договариваю по-испански…", fg=WARN)
        self._hold_wait_play = True

    def _hold_finished(self) -> None:
        """Испанский договорил — русский возвращается в кабель."""
        self._hold_wait_play = False
        self._restore_voice()
        self.state_lbl.config(text="готов: говори по-русски", fg=GOOD)

    def _restore_voice(self) -> None:
        """Вернуть русский голос в кабель (если никто не заглушил его)."""
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            want = self._mute_ru and self._cont_on
            bridge.set_duck(want)

    def _check_hold(self) -> None:
        """Проверить: кнопка/клавиша всё ещё зажата? И дождался ли испанский."""
        # 1) хоткей отпущен -> русский возвращается
        if self._hold_on and self._hold_vk:
            import ctypes
            if not (ctypes.windll.user32.GetAsyncKeyState(self._hold_vk) & 0x8000):
                self._stop_hold()
                return
        # 2) испанский договорил -> русский возвращается
        if self._hold_wait_play and not self._playback_busy():
            busy = self.translator is not None and self.translator.busy
            if not busy:
                self._hold_finished()

    # ---------- остановка перевода ----------
    def _stop_translation(self) -> None:
        """Остановить перевод: убрать недозвучавший испанский, вернуть русский.

        Без этого уже отправленные чанки испанского доигрывали ПАРАЛЛЕЛЬНО
        с живым русским голосом — собеседник слышал оба сразу.
        """
        self._out_enabled = False
        self._swap_busy = False
        self._swap_wait_play = False
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            bridge.clear_stream()
            bridge.set_duck(self._mute_ru and self._cont_on)
        with self._play_lock:
            self._play_queue.clear()

    # ---------- непрерывный режим ----------
    def _toggle_cont(self) -> None:
        if self._cont_on:
            self._stop_cont()
        else:
            self._start_cont()

    def _start_cont(self) -> None:
        if self._hold_on:
            self.state_lbl.config(text="сначала отпусти «ЗАЖАТЬ И ГОВОРИТЬ»", fg=WARN)
            return
        if not self._ensure_engine():
            return
        idx = self._sel_mic()
        if idx is None:
            self.state_lbl.config(text="выбери микрофон", fg=BAD)
            return

        self._cont_on = True
        self._out_enabled = True
        self._cont_buf = []
        self._cont_silence = 0.0
        self._cont_has_speech = False
        self._noise = 0.005
        self.cont_btn.config(text="⏹ Непрерывно: ВКЛ", bg="#8a2f2f")
        self.state_lbl.config(text="слушаю… говори свободно", fg=GOOD)

        try:
            self._stream = self._open_input(idx, self._cont_callback)
            self._stream.start()
        except Exception as exc:  # noqa: BLE001
            self._cont_on = False
            self.cont_btn.config(text="🔴 Непрерывно: выкл", bg="#2b3a4d")
            self.state_lbl.config(text=f"микрофон не открылся: {exc}", fg=BAD)

    def _stop_cont(self) -> None:
        self._cont_on = False
        self.cont_btn.config(text="🔴 Непрерывно: выкл", bg="#2b3a4d")
        self._close_input()
        # доотправить то, что не успели
        self._flush_segment()
        # и убрать недозвучавший испанский, чтобы он не играл
        # параллельно с русским
        self._stop_translation()
        self.state_lbl.config(text="непрерывный режим выключен", fg=DIM)

    def _cont_callback(self, indata, frames, time_info, status) -> None:
        """Колбэк микрофона: копим речь и режем её на фразы по паузам.

        Работает и в режиме «Непрерывно», и в режиме «ЗАЖАТЬ» — в обоих
        случаях фразы уходят на перевод на лету.
        """
        if not (self._cont_on or self._hold_on):
            return
        try:
            block = indata[:, 0].copy()
        except Exception:
            return
        rms = float(np.sqrt((block.astype(np.float64) ** 2).mean()))

        # Шумовой пол — ПРОЦЕНТИЛЬ по последним блокам, а не затухающая
        # средняя: иначе пол «уезжает» вниз и тихий шум начинает считаться
        # речью (приложение переводит шум и озвучивает мусор).
        self._rms_history.append(rms)
        if len(self._rms_history) > 240:      # ~12 секунд
            self._rms_history.pop(0)
        floor = float(np.percentile(self._rms_history, 20))
        self._noise = floor
        thr = max(floor * 3.0, 0.006)

        # Сглаженная энергия: одиночный щелчок (пик в шуме) не должен
        # считаться речью — иначе фраза из одного всплеска уходит в перевод.
        self._smooth.append(rms)
        if len(self._smooth) > 5:            # ~250 мс
            self._smooth.pop(0)
        smooth = sum(self._smooth) / len(self._smooth)

        if smooth > thr:
            self._cont_has_speech = True
            self._cont_silence = 0.0
            # «сильных» блоков (громких заметно выше порога) должно быть
            # несколько: настоящая речь длится, а щелчок — один блок
            if rms > thr * 1.5:
                self._strong_blocks += 1
        else:
            self._cont_silence += BLOCK_SEC

        self._cont_buf.append(block)

        # фраза закончилась (пауза) — отправляем
        if self._cont_silence >= SILENCE_END and self._cont_has_speech:
            self._flush_segment()
            return
        # фраза слишком длинная — режем
        if len(self._cont_buf) * BLOCK_SEC >= MAX_SEG:
            self._flush_segment()

    def _flush_segment(self) -> None:
        """Отдать накопленную фразу на перевод (может зваться из потока микрофона)."""
        buf = self._cont_buf
        self._cont_buf = []
        had_speech = self._cont_has_speech
        strong = self._strong_blocks
        self._cont_has_speech = False
        self._strong_blocks = 0
        self._cont_silence = 0.0
        if not buf or not had_speech:
            return
        # Речи должно быть не меньше ~150 мс (3 блока) — иначе это щелчок.
        if strong < 3:
            return
        audio = np.concatenate(buf)
        audio = self._trim_silence(audio)
        dur = len(audio) / SR_REC
        if dur < MIN_SPEECH:
            return

        # Проверяем, что это РЕАЛЬНО речь, а не шум: фраза должна быть
        # заметно громче шумового пола. Иначе Whisper на шуме выдаёт
        # «Я не знаю, что это» — и это озвучивается.
        seg_rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
        floor = self._noise if self._noise > 0 else 0.001
        if seg_rms < floor * 2.2:
            return
        self._queue_translate(audio, SR_REC)

    @staticmethod
    def _trim_silence(audio: np.ndarray) -> np.ndarray:
        """Убрать тишину по краям фразы (в т.ч. хвост после паузы)."""
        if audio.size == 0:
            return audio
        win = int(SR_REC * 0.02)
        n = len(audio) // win
        if n < 3:
            return audio
        frames = audio[:n * win].reshape(n, win)
        energy = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
        peak = float(energy.max())
        if peak <= 0:
            return audio
        thr = max(peak * 0.12, 0.002)
        loud = np.where(energy > thr)[0]
        if loud.size == 0:
            return audio
        start = max(0, (loud[0] - int(TRIM_SIL / 0.02)) * win)
        end = min(len(audio), (loud[-1] + 1 + int(TRIM_SIL / 0.02)) * win)
        return audio[start:end]

    # ---------- микрофон: общий код ----------
    def _open_input(self, idx: int, callback):
        import sounddevice as sd
        return sd.InputStream(device=idx, channels=1, samplerate=SR_REC,
                              dtype="float32", blocksize=int(SR_REC * BLOCK_SEC),
                              callback=callback)

    def _close_input(self) -> None:
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None

    # ---------- воспроизведение ----------
    def _emit_audio(self, pcm: np.ndarray) -> None:
        """Отдать аудио перевода туда, где его услышат.

        Если включён МОСТ (вкладка «3. Микрофон»), аудио подмешивается в
        него — тогда в кабель (или куда угодно) идёт И твоя речь, И перевод.
        Иначе — просто в выбранное устройство вывода.
        """
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            if bridge.push_pcm(pcm, lc.SR_TTS):
                self._apply_mute()
                return
        with self._play_lock:
            self._play_queue.append(pcm)
        self._ensure_playback()

    def _pause_between(self) -> None:
        """Короткая тишина между переведёнными фразами.

        Без неё фразы идут одна за другой без паузы, и речь звучит как
        непрерывный поток — «читает без паузы».
        """
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            silence = np.zeros(int(lc.SR_TTS * 0.22), dtype=np.float32)
            bridge.push_pcm(silence, lc.SR_TTS)
            return
        with self._play_lock:
            self._play_queue.append(
                np.zeros(int(lc.SR_TTS * 0.22), dtype=np.float32))
        self._ensure_playback()

    def _apply_mute(self) -> None:
        """Заглушить русский в кабеле, если включён режим «только испанский».

        Иначе собеседник слышит: сначала твой живой русский (прямой
        микрофон), потом через ~2 с испанский поверх него — перевод
        «наезжает» на голос и разбирается хуже.
        """
        bridge = getattr(self.studio, "bridge", None)
        if bridge is None or not getattr(bridge, "running", False):
            return
        want = (self._hold_on or self._swap_busy
                or (self._cont_on and self._mute_ru))
        if getattr(bridge, "ducked", False) != want:
            bridge.set_duck(want)

    def _ensure_playback(self) -> None:
        import sounddevice as sd
        with self._play_lock:
            if self._playing or not self._play_queue:
                return
            self._playing = True
            out = self._sel_out()
        try:
            self._play_stream = sd.OutputStream(
                device=out, channels=1, samplerate=lc.SR_TTS, dtype="float32",
                blocksize=int(lc.SR_TTS * 0.05), callback=self._play_callback)
            self._play_stream.start()
        except Exception:
            with self._play_lock:
                self._playing = False
            return
        threading.Thread(target=self._drain_play, daemon=True).start()

    def _play_callback(self, outdata, frames, time_info, status) -> None:
        # ВАЖНО: frames — это int (число кадров), а массив это outdata.
        need = outdata.shape[0]
        out = np.zeros(need, dtype=np.float32)
        with self._play_lock:
            while need > 0 and self._play_queue:
                chunk = self._play_queue[0]
                take = min(need, len(chunk))
                out[:take] = chunk[:take]
                if take < len(chunk):
                    self._play_queue[0] = chunk[take:]
                else:
                    self._play_queue.pop(0)
                need -= take
        outdata[:, 0] = out

    def _drain_play(self) -> None:
        """Когда очередь опустеет — закрыть поток воспроизведения."""
        while True:
            time.sleep(0.2)
            with self._play_lock:
                empty = not self._play_queue
            if empty:
                with self._play_lock:
                    if not self._play_queue:
                        self._playing = False
                        break
        try:
            if self._play_stream:
                self._play_stream.stop()
                self._play_stream.close()
        except Exception:
            pass
        self._play_stream = None
        # перевод по переключателю языка дозвучал -> возвращаем русский
        self._check_swap_done()

    def _playback_busy(self) -> bool:
        """Играет ли ещё что-то (перевод)? Учитывает и мост, и локальный плеер."""
        with self._play_lock:
            if self._play_queue:
                return True
        bridge = getattr(self.studio, "bridge", None)
        if bridge is not None and getattr(bridge, "running", False):
            return bridge.stream_pending()
        return False

    def _check_swap_done(self) -> None:
        """Перевод дозвучал — вернуть русский голос в кабель.

        ВАЖНО: при включённом мосте аудио уходит В МОСТ, а не в локальную
        очередь, поэтому _drain_play не запускается. Без этой проверки
        русский оставался заглушённым навсегда.
        """
        if not self._swap_wait_play:
            return
        if self._playback_busy():
            return
        self._swap_wait_play = False
        self._swap_finished()

    # ---------- проверка без микрофона ----------
    def _test_with_sample(self) -> None:
        """Прогнать перевод на записанном образце (без микрофона)."""
        if not self._ensure_engine():
            return
        name = self.test_combo.get()
        if not name:
            self.state_lbl.config(text="нет записей образца", fg=BAD)
            return
        path = os.path.join(sp.output_paths()["samples"], name)
        try:
            import soundfile as sf
            audio, sr = sf.read(path, dtype="float32", always_2d=False)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
        except Exception as exc:  # noqa: BLE001
            self.state_lbl.config(text=f"не прочитать запись: {exc}", fg=BAD)
            return
        self.state_lbl.config(text="перевожу запись…", fg=WARN)
        self._queue_translate(audio, sr)

    # ---------- опрос ----------
    def poll(self) -> None:
        """Вызывается из GUI-потока: разобрать ответы движка."""
        if self.translator is not None:
            self.translator.poll()
        # перевод мог дозвучать — проверяем каждый раз (дешевле, чем следить
        # за очередью в мосте из потока воспроизведения)
        self._check_swap_done()
        # отпустили ли клавишу «Говорить»? (для режима «зажать»)
        self._check_hold()
