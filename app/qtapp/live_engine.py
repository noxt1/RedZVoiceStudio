"""Headless-движок живого перевода для Qt-интерфейса.

Что делает: поднимает процесс-движок (`tools/live_translate.py`) через
существующий `live_client.LiveTranslator`, гоняет микрофон через
`mic_bridge.MicBridge` и отправляет PCM на перевод. Ничего не дублирует —
только связывает существующие модули и отдаёт события в Qt.

Tkinter не используется. Вместо `root.after` — Qt-сигналы.

Связь с QML: QML вызывает слоты (`start`, `stop`, `pushToTalk`,
`setContinuous`, `setLang`...), а события приходят сигналами
(`stateChanged`, `textReady`, `levelChanged`, `logLine`).
"""

from __future__ import annotations

import base64
import os
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot, Property, QTimer

import studio_paths as sp
import studio_core as core
import live_client as lc

SR_REC = 44100
BLOCK_SEC = 0.05
SILENCE_END = 0.75
MIN_SPEECH = 0.35
MAX_SEG = 25.0
# Сколько ждать перевод после отпускания PTT, прежде чем вернуть русский.
HOLD_MAX_WAIT = 20.0

# Сегментация звука собеседника (системный звук через loopback).
PEER_SILENCE_END = 0.80
PEER_MIN_SPEECH = 0.45
PEER_MAX_SEG = 18.0
# Куски отправки звука собеседника в движок (сек).
PEER_SEND_CHUNK = 5.0


class LiveEngine(QObject):
    """Управление живым переводом без UI-зависимостей."""

    # ---- сигналы в QML ----
    stateChanged = Signal(str)               # STOPPED/LOADING/READY/ERROR
    textReady = Signal(str, str, str)        # ru, es, tone
    peerTextReady = Signal(str, str, str)    # src, ru, es
    levelChanged = Signal(float)             # 0..1 уровень микрофона
    logLine = Signal(str)
    errorMessage = Signal(str)
    busyChanged = Signal(bool)
    translationStarted = Signal()
    translationFinished = Signal()
    capturedAudio = Signal(float)            # длительность захваченного аудио, сек
    captureChanged = Signal(bool)            # захват речи игроков вкл/выкл
    incomingChanged = Signal()               # входящая озвучка: вкл/выкл/громкость
    outgoingChanged = Signal()               # исходящий перевод вкл/выкл
    lastPhraseChanged = Signal()             # последняя реплика (оригинал+перевод)
    incomingActiveChanged = Signal(bool)     # сейчас играет входящий перевод
    peerLangChanged = Signal()
    peerLevelChanged = Signal(float)
    modelsChanged = Signal()                 # установленные модели ASR/TTS/MT
    autoDownloadChanged = Signal()
    packageChanged = Signal()                # статус загрузки языкового пакета
    catalogChanged = Signal()                # каталог моделей
    catalogStatusChanged = Signal()          # текст «обновляю/обновлён»
    packsChanged = Signal()                  # языковые пакеты
    downloadsChanged = Signal()              # прогресс загрузок
    modelsLoadedChanged = Signal()           # модели в памяти движка
    peerLangInfoChanged = Signal()           # определённый язык собеседника
    modeChanged = Signal()                   # режим fast/balanced/quality/manual
    peerPartialChanged = Signal()            # промежуточное распознавание
    metricsChanged = Signal()                # метрики последней реплики

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # --- движок (subprocess) ---
        self._translator: lc.LiveTranslator | None = None
        self._state = "STOPPED"
        self._error = ""
        self._ready = False
        self._loading = False
        self._busy = False

        # --- устройства ---
        self._mic_idx: int | None = None
        self._out_idx: int | None = None

        # --- режим PTT («зажать») ---
        self._hold_on = False
        self._hold_wait_play = False
        self._hold_release_at = 0.0

        # --- непрерывный режим ---
        self._cont_on = False
        self._cont_buf: list[np.ndarray] = []
        self._cont_silence = 0.0
        self._cont_has_speech = False
        self._noise = 0.005
        self._rms_history: list[float] = []
        self._smooth: list[float] = []
        self._strong_blocks = 0

        # --- воспроизведение (когда моста нет) ---
        self._play_stream = None
        self._play_queue: list[np.ndarray] = []
        self._play_lock = threading.Lock()
        self._playing = False
        # Частота, на которой реально открылся выход. Кабель VB-Audio в
        # WASAPI не умеет 24 кГц — раньше открытие падало молча и перевод
        # после первой фразы просто исчезал.
        self._play_sr = 0
        self._play_note = ""
        self._bridge_note = ""
        self._bridge_check = 0.0
        self._bridge_dropped = 0

        # --- очередь на перевод ---
        self._queue: list[tuple[np.ndarray, int]] = []
        self._queue_lock = threading.Lock()

        # --- вход ---
        self._stream = None

        # --- захват звука собеседников ---
        self._loopback = None
        self._capture_on = False
        self._peer_level = 0.0

        # --- сегментация звука собеседника (loopback -> фразы) ---
        self._peer_buf: list[np.ndarray] = []
        self._peer_sr = 48000
        self._peer_silence = 0.0
        self._peer_speech = False
        self._peer_strong = 0
        self._peer_noise = 0.004
        self._peer_rms: list[float] = []

        # --- входящий перевод: RU-озвучка в наушники ---
        self._incoming = None
        self._incoming_on = False
        self._incoming_volume = 1.0
        self._incoming_active = False
        self._incoming_seq = 0
        self._incoming_q: list[np.ndarray] = []
        self._incoming_stream = None
        self._incoming_playing = False
        self._incoming_lock = threading.Lock()
        # Устройство для входящего перевода (наушники). None = системное по
        # умолчанию; в кабель (virtual mic) входящий звук не идёт никогда.
        self._monitor_idx: int | None = None

        # --- установленные модели (приходят из движка командой models) ---
        self._asr_models: list[dict] = []
        self._asr_model = ""
        self._tts_models: list[dict] = []
        self._tts_model = ""
        self._mt_info: list[dict] = []

        # --- индикатор уровня (ставится извне) ---
        self.recorder = None
        # уровень с открытого входа живого режима (0..1)
        self._level = 0.0
        # громкость синтеза в кабель/динамики (1.0 = 100 %)
        self._volume = 1.0
        self._signals_bound = False

        # --- язык перевода ---
        self._lang_code = "es"
        self._peer_lang = "auto"
        self._liveliness = 2
        # язык пользователя (источник исходящего перевода)
        self._src_lang = "ru"
        self._src_langs: list[dict] = []
        # исходящий канал можно выключить независимо от входящего
        self._outgoing_on = True
        # автоскачивание языковых пакетов (по умолчанию ВЫКЛЮЧЕНО)
        self._auto_download = False
        self._package_status = ""
        # Model Manager / языковые пакеты
        self._catalog: list = []
        self._catalog_status: str = ""
        self._packs: list = []
        self._downloads: dict = {}
        self._models_loaded = False
        self._peer_confirmed = ""
        self._peer_prob = 0.0
        self._peer_reason = ""
        self._mode = "balanced"
        self._mode_info = ""
        self._peer_partial = ""
        self._metrics: dict = {}
        self._dropped = 0
        self._cancelled = 0
        # накопление для промежуточного распознавания
        self._peer_acc = 0.0
        self._peer_partial_acc = 0.0
        self._peer_partial_t = 0.0
        # последние реплики для показа оригинала и перевода
        self._last_out: tuple[str, str] = ("", "")
        self._last_in: tuple[str, str] = ("", "")

        # --- повтор из истории переводов ---
        self._replay_seq = 0

        # --- Qt-таймеры ---
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._poll)

        self._hold_timer = QTimer(self)
        self._hold_timer.setInterval(50)
        self._hold_timer.timeout.connect(self._check_hold)

        self._level_timer = QTimer(self)
        self._level_timer.setInterval(100)
        self._level_timer.timeout.connect(self._emit_level)

        # Русский в кабеле идёт, пока говорит человек, и глохнет ровно
        # на время перевода (и PTT, и непрерывный режим).
        self._duck_timer = QTimer(self)
        self._duck_timer.setInterval(60)
        self._duck_timer.timeout.connect(self._update_duck)
        self._duck_timer.start()

        # Страховка: если движок не пришлёт incoming_done, снимаем блокировку
        # входящего перевода, чтобы захват собеседника не залип.
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.setInterval(30000)
        self._watchdog.timeout.connect(self._incoming_timeout)

        # ссылка на мост (ставит AppState)
        self.bridge = None
        self._state_obj = None

    # ==================================================================
    # СВОЙСТВА
    # ==================================================================
    @Property(str, notify=stateChanged)
    def state(self) -> str:
        return self._state

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(bool, notify=stateChanged)
    def ready(self) -> bool:
        return self._ready

    @Property(str, notify=errorMessage)
    def error(self) -> str:
        return self._error

    @Property(bool, notify=captureChanged)
    def captureOn(self) -> bool:
        return self._capture_on

    @Property(bool, notify=outgoingChanged)
    def outgoingOn(self) -> bool:
        """Включён ли исходящий перевод (речь пользователя -> собеседник)."""
        return self._outgoing_on

    @Property(bool, notify=autoDownloadChanged)
    def autoDownload(self) -> bool:
        """Разрешено ли движку скачивать недостающие пакеты."""
        return self._auto_download

    @Property(str, notify=packageChanged)
    def packageStatus(self) -> str:
        return self._package_status

    # ---------- Model Manager ----------
    @Property("QVariantList", notify=catalogChanged)
    def catalog(self):
        """Каталог моделей: метаданные + состояние установки."""
        return self._catalog

    @Property("QVariantList", notify=packsChanged)
    def packs(self):
        """Языковые пакеты: что установлено, чего не хватает."""
        return self._packs

    @Property("QVariantMap", notify=downloadsChanged)
    def downloads(self):
        """Текущие загрузки: id модели -> {state, percent, label, message}."""
        return self._downloads

    @Property(bool, notify=modelsLoadedChanged)
    def modelsLoaded(self) -> bool:
        """Загружены ли модели в память движка."""
        return self._models_loaded

    @Property(str, notify=peerLangInfoChanged)
    def peerLangConfirmed(self) -> str:
        """Подтверждённый язык собеседника (режим auto)."""
        return self._peer_confirmed

    @Property(float, notify=peerLangInfoChanged)
    def peerLangProb(self) -> float:
        return float(self._peer_prob)

    @Property(str, notify=peerLangInfoChanged)
    def peerLangReason(self) -> str:
        return self._peer_reason

    @Property(str, notify=modeChanged)
    def mode(self) -> str:
        """Режим работы: fast / balanced / quality / manual."""
        return self._mode

    @Property(str, notify=modeChanged)
    def modeInfo(self) -> str:
        """Фактические параметры режима (что реально применяется)."""
        return self._mode_info

    @Property(str, notify=peerPartialChanged)
    def peerPartial(self) -> str:
        """Промежуточное распознавание (только показ, без перевода)."""
        return self._peer_partial

    @Property("QVariantMap", notify=metricsChanged)
    def lastMetrics(self):
        return self._metrics

    @Slot(str)
    def setMode(self, code: str) -> None:
        code = (code or "").strip().lower()
        if code not in ("fast", "balanced", "quality", "manual"):
            return
        self._mode = code
        if self._translator is not None and self._translator.ready:
            try:
                self._translator.set_mode(code)
            except Exception:
                pass
        self.modeChanged.emit()
        self.logLine.emit(f"режим: {code}")

    def _send_cmd(self, payload: dict) -> bool:
        if self._translator is None:
            self.errorMessage.emit("движок не запущен — нажми «Загрузить модели» на странице «Модели»")
            return False
        return bool(self._translator.send(payload))

    @Property(str, notify=catalogStatusChanged)
    def catalogStatus(self) -> str:
        """Что происходит с обновляемым каталогом (последний ответ HF)."""
        return self._catalog_status

    def _set_catalog_status(self, text: str) -> None:
        self._catalog_status = text or ""
        self.catalogStatusChanged.emit()

    @Slot()
    def requestCatalog(self) -> None:
        self._send_cmd({"cmd": "catalog"})

    @Slot()
    def refreshCatalog(self) -> None:
        """Перечитать список моделей с HuggingFace (тяжёлое — в движке)."""
        if self._send_cmd({"cmd": "refresh_catalog"}):
            self._set_catalog_status("обновляю каталог…")

    @Slot()
    def requestPacks(self) -> None:
        self._send_cmd({"cmd": "packs"})

    @Slot(str)
    def downloadModel(self, model_id: str) -> None:
        if model_id:
            self._send_cmd({"cmd": "model_download", "id": model_id,
                            "request": model_id})

    @Slot(str)
    def cancelDownload(self, request: str) -> None:
        self._send_cmd({"cmd": "model_cancel", "request": request})

    @Slot(str)
    def removeModel(self, model_id: str) -> None:
        if model_id:
            self._send_cmd({"cmd": "model_remove", "id": model_id})

    @Slot(str)
    def verifyModel(self, model_id: str) -> None:
        if model_id:
            self._send_cmd({"cmd": "model_verify", "id": model_id})

    @Slot(str, str)
    def selectModel(self, kind: str, model_id: str) -> None:
        self._send_cmd({"cmd": "model_select", "kind": kind, "id": model_id})

    @Slot()
    def loadModels(self) -> None:
        self._send_cmd({"cmd": "models_load"})

    @Slot()
    def unloadModels(self) -> None:
        self._send_cmd({"cmd": "models_unload"})

    @Slot(str)
    def installPack(self, code: str) -> None:
        if code:
            self._send_cmd({"cmd": "pack_install", "code": code,
                            "request": "pack:" + code})

    @Slot(str)
    def removePack(self, code: str) -> None:
        if code:
            self._send_cmd({"cmd": "pack_remove", "code": code})

    @Slot(str)
    def verifyPack(self, code: str) -> None:
        if code:
            self._send_cmd({"cmd": "pack_verify", "code": code})

    @Slot(bool)
    def setAutoDownload(self, on: bool) -> None:
        self._auto_download = bool(on)
        if self._translator is not None and self._translator.ready:
            try:
                self._translator.set_auto_download(self._auto_download)
            except Exception:
                pass
        self.autoDownloadChanged.emit()
        self.logLine.emit("автоскачивание пакетов включено" if on
                          else "автоскачивание пакетов выключено")

    @Property(str, notify=modelsChanged)
    def srcLang(self) -> str:
        return self._src_lang

    @Property("QVariantList", notify=modelsChanged)
    def srcModels(self):
        """Языки пользователя, с которых реально можно переводить."""
        return self._src_langs

    @Property(str, notify=lastPhraseChanged)
    def lastOutOriginal(self) -> str:
        return self._last_out[0]

    @Property(str, notify=lastPhraseChanged)
    def lastOutTranslation(self) -> str:
        return self._last_out[1]

    @Property(str, notify=lastPhraseChanged)
    def lastInOriginal(self) -> str:
        return self._last_in[0]

    @Property(str, notify=lastPhraseChanged)
    def lastInTranslation(self) -> str:
        return self._last_in[1]

    @Property(bool, notify=incomingChanged)
    def incomingOn(self) -> bool:
        """Включён ли перевод речи собеседника в наушники."""
        return self._incoming_on

    @Property(int, notify=incomingChanged)
    def incomingVolume(self) -> int:
        return int(round(self._incoming_volume * 100.0))

    @Property(bool, notify=incomingActiveChanged)
    def incomingActive(self) -> bool:
        """Сейчас синтез/воспроизведение входящего перевода."""
        return self._incoming_active

    @Property(float, notify=peerLevelChanged)
    def peerLevel(self) -> float:
        return float(self._peer_level)

    @Property(str, notify=peerLangChanged)
    def peerLang(self) -> str:
        return self._peer_lang

    @Property("QVariantList", notify=modelsChanged)
    def asrModels(self):
        return self._asr_models

    @Property(str, notify=modelsChanged)
    def asrModel(self) -> str:
        return self._asr_model

    @Property("QVariantList", notify=modelsChanged)
    def ttsModels(self):
        return self._tts_models

    @Property(str, notify=modelsChanged)
    def ttsModel(self) -> str:
        return self._tts_model

    @Property("QVariantList", notify=modelsChanged)
    def mtInfo(self):
        """Направления перевода: что установлено, чего нет."""
        return self._mt_info

    @Slot(result=str)
    def mtSummary(self) -> str:
        """Короткая строка о доступных направлениях для UI."""
        items = [m for m in self._mt_info if m.get("pair")]
        if not items:
            return "нет данных — запусти движок"
        ok = [m["pair"] for m in items if m.get("installed")]
        bad = [m["pair"] for m in items if not m.get("installed")]
        text = "установлено: " + (", ".join(ok) if ok else "нет")
        if bad:
            text += "; нет модели: " + ", ".join(bad)
        return text

    # ==================================================================
    # ЖИЗНЕННЫЙ ЦИКЛ
    # ==================================================================
    def attach(self, state_obj) -> None:
        """Связать с AppState: пробросить состояние движка и ошибки в UI."""
        self._state_obj = state_obj
        if self._signals_bound:
            return
        self._signals_bound = True
        try:
            self.stateChanged.connect(state_obj.syncEngineState)
            self.errorMessage.connect(state_obj.syncEngineError)
        except Exception:
            pass
        try:
            self.setVolume(int(state_obj.voiceVolume))
            # устройства могли быть выбраны до подключения движка —
            # без этого PTT отвечал «выбери микрофон»
            self._sync_devices_from_state()
            state_obj.devicesChanged.connect(self._sync_devices_from_state)
        except Exception:
            pass
        # настройки, сохранённые в ui_settings.json
        try:
            self._lang_code = getattr(state_obj, "targetLang", self._lang_code)
            self._peer_lang = getattr(state_obj, "peerLang", self._peer_lang)
            self._incoming_volume = max(
                0.0, min(1.5, float(getattr(state_obj, "incomingVolume", 100)) / 100.0))
            # только флаг: захват стартует по явному включению из UI
            self._incoming_on = bool(getattr(state_obj, "incomingOn", False))
            self._asr_model = str(getattr(state_obj, "asrModel", "") or "")
            self._liveliness = int(getattr(state_obj, "liveliness", self._liveliness))
            self._outgoing_on = bool(getattr(state_obj, "outgoingOn", True))
            self._auto_download = bool(getattr(state_obj, "autoDownload", False))
            self._mode = str(getattr(state_obj, "mode", self._mode))
            self._src_lang = str(getattr(state_obj, "srcLang", "ru") or "ru")
        except Exception:
            pass
        # Подтягиваем reference активного профиля, если он уже выбран.
        try:
            self.setProfile(sp.get_active_profile())
        except Exception:
            pass

    def _sync_devices_from_state(self) -> None:
        """Подтянуть выбранные в UI микрофон/выход в живой движок."""
        st = self._state_obj
        if st is None:
            return
        try:
            self._mic_idx = st.inDevice if st.inDevice >= 0 else None
            self._out_idx = st.outDevice if st.outDevice >= 0 else None
        except Exception:
            pass

    def _set_state(self, state: str, error: str = "") -> None:
        self._state = state
        self._error = error
        self._ready = (state == "READY")
        self._loading = (state == "LOADING")
        self.stateChanged.emit(state)
        if error:
            self.errorMessage.emit(error)

    def start(self) -> None:
        """Запустить движок и загрузить модели."""
        if self._translator is not None and self._translator.ready:
            self._set_state("READY")
            return
        if self._translator is None:
            script = os.path.join(sp.workspace_tools(), "live_translate.py")
            # Активный профиль: его reference.wav, а не общий workspace.
            ref = sp.active_reference()
            if not os.path.exists(ref):
                fallback = sp.output_paths()["reference"]
                if os.path.exists(fallback):
                    ref = fallback
                else:
                    self._set_state("ERROR", "нет образца голоса (reference.wav)")
                    return
            self._translator = lc.LiveTranslator(
                sp.engine_python(), script, ref,
                on_event=self._on_event, on_text=self._on_text)
            self.logLine.emit(f"reference: {ref}")
        else:
            # Движок уже создан, но профиль мог смениться, пока он был
            # остановлен: обновляем путь до следующего load.
            try:
                ref = sp.active_reference()
                if os.path.exists(ref):
                    self._translator.reference = ref
            except Exception:
                pass
        self._set_state("LOADING")
        ok = self._translator.start()
        if not ok:
            self._set_state("ERROR", self._translator.error or "движок не запустился")
            return
        self._poll_timer.start()
        self.logLine.emit("движок запускается…")

    def stop(self) -> None:
        """Остановить перевод и выгрузить модели."""
        if self._state != "STOPPED":
            self._set_state("STOPPING")
        self._stop_input()
        self._cont_on = False
        self._hold_on = False
        self._hold_wait_play = False
        self._hold_timer.stop()
        self._duck(False)
        self._poll_timer.stop()
        self._level_timer.stop()
        if self._translator is not None:
            self._translator.stop()
        self._clear_play()
        self._clear_incoming()
        self._peer_buf = []
        self._peer_speech = False
        self._set_state("STOPPED")

    def shutdown(self) -> None:
        """Полная остановка при закрытии приложения."""
        self.stop()
        self._stop_capture()
        self._watchdog.stop()

    # ==================================================================
    # ЯЗЫК / ЖИВОСТЬ
    # ==================================================================
    @Slot(str)
    def setLang(self, code: str) -> None:
        self._lang_code = code
        if self._translator is not None and self._translator.ready:
            self._translator.set_lang(code)

    def _sync_voice_reference(self) -> None:
        """Принудительно применить reference активного профиля.

        Нужно после загрузки моделей: движок стартует с путём из argv, а
        профиль могли переключить, пока шла загрузка. Без этого TTS
        оставался с прежним тембром — «клон не применяется».
        """
        tr = self._translator
        if tr is None:
            return
        ref = sp.active_reference()
        if not os.path.exists(ref):
            fallback = sp.output_paths()["reference"]
            if os.path.exists(fallback):
                ref = fallback
        if not os.path.exists(ref):
            return
        tr.reference = ref
        if tr.ready:
            try:
                tr.set_reference(ref)
                name = sp.get_active_profile() or "по умолчанию"
                self.logLine.emit(f"голос активного профиля: {name}")
            except Exception as exc:  # noqa: BLE001
                self.logLine.emit(f"голос не применился: {exc}")

    @Slot(str)
    def setProfile(self, name: str) -> None:
        """Сменить голосовой профиль на лету (без перезагрузки моделей)."""
        name = (name or "").strip()
        ref = sp.profile_reference(name) if name else sp.output_paths()["reference"]
        if not os.path.exists(ref):
            self.logLine.emit(f"у профиля «{name or 'по умолчанию'}» нет reference.wav")
            return
        tr = self._translator
        if tr is None:
            return
        tr.reference = ref
        if tr.ready:
            try:
                tr.set_reference(ref)
                self.logLine.emit(f"голос переключён: {name or 'по умолчанию'}")
            except Exception as exc:
                self.logLine.emit(f"голос не переключился: {exc}")

    @Slot(bool)
    def setOutgoing(self, on: bool) -> None:
        """Включить/выключить исходящий перевод."""
        self._outgoing_on = bool(on)
        if not on:
            if self._hold_on:
                self._stop_hold()
            if self._cont_on:
                self._stop_cont()
        self.outgoingChanged.emit()
        self.logLine.emit("исходящий перевод включён" if on
                          else "исходящий перевод выключен")

    @Slot(str)
    def setSrcLang(self, code: str) -> None:
        """Язык пользователя (с какого языка переводим его речь)."""
        self._src_lang = (code or "ru").strip() or "ru"
        if self._translator is not None and self._translator.ready:
            try:
                self._translator.set_src_lang(self._src_lang)
            except Exception:
                pass
        self.modelsChanged.emit()

    @Slot(str)
    def setPeerLang(self, code: str) -> None:
        # generation guard на стороне UI: старый перевод не должен
        # доигрываться после смены языка собеседника
        self._clear_play()
        self._peer_partial = ""
        self.peerPartialChanged.emit()
        self._peer_lang = code
        if self._translator is not None and self._translator.ready:
            self._translator.set_peer_lang(code)
        self.peerLangChanged.emit()

    # ==================================================================
    # ВХОДЯЩИЙ ПЕРЕВОД (речь собеседника -> RU -> наушники)
    # ==================================================================
    @Slot(bool)
    def setIncomingEnabled(self, on: bool) -> None:
        """Включить/выключить перевод речи собеседника."""
        self._incoming_on = bool(on)
        if on:
            if not self._capture_on:
                self.startCapture()
            self.logLine.emit("перевод речи собеседника включён")
        else:
            self._stop_capture()
            self._clear_incoming()
            self.logLine.emit("перевод речи собеседника выключен")
        self.incomingChanged.emit()

    @Slot(int)
    def setIncomingVolume(self, percent: int) -> None:
        """Громкость входящего перевода (проценты, 0..150)."""
        self._incoming_volume = max(0.0, min(1.5, float(percent) / 100.0))
        # Живой мост держит свою громкость наушников — обновляем сразу,
        # иначе ползунок менял только сохранённое число.
        b = self.bridge
        if b is not None and getattr(b, "running", False):
            try:
                b.set_gains(monitor_gain=self._incoming_volume)
            except Exception:
                pass
        self.incomingChanged.emit()

    @Slot(int)
    def setMonitorDevice(self, idx: int) -> None:
        """Устройство для входящего перевода (наушники). -1 = по умолчанию."""
        self._monitor_idx = idx if idx >= 0 else None

    @Slot()
    def requestModels(self) -> None:
        """Перечитать список установленных моделей из движка."""
        tr = self._translator
        if tr is None or not tr.ready:
            self.logLine.emit("движок не запущен — список моделей недоступен")
            return
        try:
            tr.request_models()
        except Exception:
            pass

    @Slot(str)
    def setAsrModel(self, name: str) -> None:
        """Переключить модель распознавания (должна быть установлена)."""
        name = (name or "").strip()
        if not name or name == self._asr_model:
            return
        tr = self._translator
        if tr is None or not tr.ready:
            self.logLine.emit("движок не запущен — модель не переключена")
            return
        if tr.set_asr_model(name):
            self._asr_model = name
            self.logLine.emit(f"переключаю распознавание на {name}…")
            self.modelsChanged.emit()

    @Slot(int)
    def setVolume(self, percent: int) -> None:
        """Громкость синтезированного голоса (проценты, 0..200)."""
        self._volume = max(0.0, min(2.0, float(percent) / 100.0))
        b = self.bridge
        if b is not None and getattr(b, "running", False):
            try:
                b.set_gains(phrase_gain=self._volume)
            except Exception:
                pass

    @Slot(int)
    def setLiveliness(self, level: int) -> None:
        self._liveliness = max(0, min(3, int(level)))
        if self._translator is not None and self._translator.ready:
            self._translator.set_liveliness(self._liveliness)

    # ==================================================================
    # УСТРОЙСТВА
    # ==================================================================
    @Slot(int)
    def setMicDevice(self, idx: int) -> None:
        self._mic_idx = idx if idx >= 0 else None

    @Slot(int)
    def setOutDevice(self, idx: int) -> None:
        self._out_idx = idx if idx >= 0 else None

    # ==================================================================
    # PTT: «ЗАЖАТЬ И ГОВОРИТЬ»
    # ==================================================================
    @Slot()
    def pressToTalk(self) -> None:
        self._start_hold()

    @Slot()
    def releaseToTalk(self) -> None:
        self._stop_hold()

    def _start_hold(self) -> None:
        if self._hold_on:
            return
        if not self._outgoing_on:
            self.errorMessage.emit("исходящий перевод выключен")
            return
        if self._cont_on:
            self.logLine.emit("сначала выключи непрерывный режим")
            return
        if self._mic_idx is None:
            self.errorMessage.emit("выбери микрофон")
            return
        # Микрофон открываем сразу — уровень и запись работают даже пока
        # модели грузятся; перевод пойдёт, как только движок станет готов.
        if not self._ensure_engine():
            self.logLine.emit("движок не готов — идёт только проверка микрофона")
        self._hold_on = True
        self._cont_buf = []
        self._cont_silence = 0.0
        self._cont_has_speech = False
        self._strong_blocks = 0
        self._noise = 0.005
        self._open_input(self._cont_callback)
        self._level_timer.start()
        self._duck(True)
        self.translationStarted.emit()

    def _stop_hold(self) -> None:
        if not self._hold_on:
            return
        self._hold_on = False
        self._level_timer.stop()
        self._close_input()
        self._flush_segment()
        self._hold_wait_play = True
        # Таймер запускается только здесь: он единственный, кто снимет
        # _hold_wait_play и вернёт русский в кабель.
        self._hold_release_at = time.monotonic()
        self._hold_timer.start()

    def _bridge_pending(self) -> bool:
        """Есть ли ещё недозвучавший перевод в мосту."""
        bridge = self.bridge
        if bridge is None or not getattr(bridge, "running", False):
            return False
        try:
            return bool(bridge.stream_pending())
        except Exception:
            return False

    def _check_hold(self) -> None:
        if not self._hold_wait_play:
            self._hold_timer.stop()
            return
        # Перевод может доигрывать в мосту — тогда русский возвращать
        # нельзя, иначе он ляжет поверх перевода. Страховка: если движок
        # не ответил, русский не должен замолкнуть навсегда.
        stuck = time.monotonic() - self._hold_release_at > HOLD_MAX_WAIT
        if stuck or not (self._bridge_pending() or self._playback_busy()
                         or self._busy):
            self._hold_wait_play = False
            self._hold_timer.stop()
            self._duck(False)
            self.translationFinished.emit()
            if stuck:
                self.logLine.emit("перевод не подтвердился — русский возвращён")

    # ==================================================================
    # НЕПРЕРЫВНЫЙ РЕЖИМ
    # ==================================================================
    @Slot()
    def toggleContinuous(self) -> None:
        """Переключить непрерывный режим (глобальный хоткей Ctrl+Alt+L)."""
        self.setContinuous(not self._cont_on)

    @Slot(bool)
    def setContinuous(self, on: bool) -> None:
        if on:
            self._start_cont()
        else:
            self._stop_cont()

    def _start_cont(self) -> None:
        if self._cont_on:
            return
        if not self._outgoing_on:
            self.errorMessage.emit("исходящий перевод выключен")
            return
        if self._mic_idx is None:
            self.errorMessage.emit("выбери микрофон")
            return
        if not self._ensure_engine():
            self.logLine.emit("движок не готов — идёт только проверка микрофона")
        self._cont_on = True
        self._cont_buf = []
        self._cont_silence = 0.0
        self._cont_has_speech = False
        self._noise = 0.005
        self._open_input(self._cont_callback)
        self._level_timer.start()
        self.logLine.emit("непрерывный режим включён")

    def _stop_cont(self) -> None:
        self._cont_on = False
        self._close_input()
        self._flush_segment()
        self._level_timer.stop()
        self.logLine.emit("непрерывный режим выключен")

    # ==================================================================
    # МИКРОФОН
    # ==================================================================
    def _ensure_engine(self) -> bool:
        if self._translator is not None and self._translator.ready:
            return True
        if self._translator is not None and self._translator.loading:
            return False
        self.start()
        return self._translator is not None and self._translator.ready

    def _open_input(self, callback) -> None:
        import sounddevice as sd
        self._close_input()
        self._stream = sd.InputStream(
            device=self._mic_idx, channels=1, samplerate=SR_REC,
            dtype="float32", blocksize=int(SR_REC * BLOCK_SEC),
            callback=callback)
        self._stream.start()

    def _close_input(self) -> None:
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None
        self._level = 0.0

    def _stop_input(self) -> None:
        self._close_input()

    def _cont_callback(self, indata, frames, time_info, status) -> None:
        """Колбэк микрофона: режем речь на фразы по паузам."""
        if not (self._cont_on or self._hold_on):
            return
        try:
            block = indata[:, 0].copy()
        except Exception:
            return
        rms = float(np.sqrt((block.astype(np.float64) ** 2).mean()))
        # уровень для индикатора: логарифмическая шкала (-55 дБ…0 дБ),
        # чтобы полоска была живой и на тихом микрофоне
        db = 20.0 * float(np.log10(max(rms, 1e-6)))
        lvl = max(0.0, min(1.0, (db + 55.0) / 55.0))
        self._level = max(lvl, self._level * 0.55)
        self._rms_history.append(rms)
        if len(self._rms_history) > 240:
            self._rms_history.pop(0)
        floor = float(np.percentile(self._rms_history, 20))
        self._noise = floor
        thr = max(floor * 3.0, 0.006)
        self._smooth.append(rms)
        if len(self._smooth) > 5:
            self._smooth.pop(0)
        smooth = sum(self._smooth) / len(self._smooth)
        if smooth > thr:
            self._cont_has_speech = True
            self._cont_silence = 0.0
            if rms > thr * 1.5:
                self._strong_blocks += 1
        else:
            self._cont_silence += BLOCK_SEC
        self._cont_buf.append(block)
        if self._cont_silence >= SILENCE_END and self._cont_has_speech:
            self._flush_segment()
            return
        if len(self._cont_buf) * BLOCK_SEC >= MAX_SEG:
            self._flush_segment()

    def _flush_segment(self) -> None:
        buf = self._cont_buf
        self._cont_buf = []
        had_speech = self._cont_has_speech
        strong = self._strong_blocks
        self._cont_has_speech = False
        self._strong_blocks = 0
        self._cont_silence = 0.0
        if not buf or not had_speech:
            return
        if strong < 3:
            return
        audio = np.concatenate(buf)
        audio = self._trim_silence(audio)
        dur = len(audio) / SR_REC
        if dur < MIN_SPEECH:
            return
        seg_rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
        floor = self._noise if self._noise > 0 else 0.001
        if seg_rms < floor * 2.2:
            return
        # Убираем гул/шипение комнаты до отправки в Whisper: высокочастотный
        # фильтр + мягкий гейт по кадрам. Это не «шумодав» уровня RTX Voice,
        # но заметно снижает ложные фразы на фоновом телевизоре/вентиляторе.
        audio = self._denoise(audio)
        self._queue_translate(audio, SR_REC)

    @staticmethod
    def _denoise(audio: np.ndarray) -> np.ndarray:
        """Высокочастотный фильтр (80 Гц) + мягкий гейт тихих кадров."""
        if audio.size < 256:
            return audio
        x = audio.astype(np.float32, copy=True)
        x -= float(x.mean())
        # lowpass через скользящее среднее, highpass = x - lowpass
        n = max(8, int(SR_REC / 80.0))
        if n < len(x):
            cs = np.cumsum(np.pad(x, (n, 0), mode="edge"), dtype=np.float64)
            low = (cs[n:] - cs[:-n]) / float(n)
            x = (x - low).astype(np.float32)
        # гейт: кадры тише фонового шума приглушаем, а не режем в ноль
        win = max(64, int(SR_REC * 0.01))
        count = len(x) // win
        if count >= 4:
            frames = x[:count * win].reshape(count, win)
            rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
            floor = float(np.percentile(rms, 15))
            # Мягкий expander: только реально шумные кадры. Агрессивный гейт
            # 0.15 срезал тихие согласные и голос звучал «рваным».
            thr = max(floor * 1.4, 0.002)
            gain = np.where(rms < thr, 0.6, 1.0)
            # сглаживаем переходы, чтобы не было щелчков
            kernel = np.ones(3, dtype=np.float64) / 3.0
            gain = np.convolve(gain, kernel, mode="same")
            # Огибающая на ВСЮ длину сигнала, а не на целое число окон:
            # `np.repeat(gain, win)` давал длину count*win, и после обрезки
            # тишины (длина уже не кратна окну) умножение падало с
            # ValueError — фраза терялась целиком.
            envelope = np.interp(np.arange(len(x), dtype=np.float64) / win,
                                 np.arange(len(gain), dtype=np.float64), gain)
            x = (x * envelope).astype(np.float32)
        peak = float(np.abs(x).max()) if x.size else 0.0
        if peak > 0.98:
            x = x / peak * 0.98
        return x

    @staticmethod
    def _trim_silence(audio: np.ndarray) -> np.ndarray:
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
        thr = max(peak * 0.06, 0.0015)
        loud = np.where(energy > thr)[0]
        if loud.size == 0:
            return audio
        start = max(0, (loud[0] - int(0.25 / 0.02)) * win)
        end = min(len(audio), (loud[-1] + 1 + int(0.25 / 0.02)) * win)
        return audio[start:end]

    # ==================================================================
    # ОТПРАВКА НА ПЕРЕВОД
    # ==================================================================
    def _queue_translate(self, pcm: np.ndarray, sr: int) -> None:
        if self._translator is None or not self._translator.ready:
            return
        with self._queue_lock:
            # Очередь исходящего ограничена: при перегрузке теряем САМУЮ
            # старую фразу, а не копим задержку до неприемлемой.
            if len(self._queue) >= 3:
                self._queue.pop(0)
                self._dropped += 1
            self._queue.append((pcm, sr))
        self._pump_queue()

    def _pump_queue(self) -> None:
        t = self._translator
        if t is None or not t.ready or t.busy:
            return
        with self._queue_lock:
            if not self._queue:
                return
            pcm, sr = self._queue.pop(0)
        if t.translate_pcm(pcm, sr, self._noise):
            self._set_busy(True)
            self.capturedAudio.emit(len(pcm) / sr)

    def _set_busy(self, flag: bool) -> None:
        if self._busy == flag:
            return
        self._busy = flag
        self.busyChanged.emit(flag)

    # ==================================================================
    # ВОСПРОИЗВЕДЕНИЕ
    # ==================================================================
    def _log_play(self, text: str) -> None:
        """Записать в лог профиля, что происходит с выводом звука.

        Без этого поломка вывода выглядела как «перевод пропал»: ошибка
        открытия устройства молча глоталась.
        """
        try:
            tr = self._translator
            if tr is not None:
                tr._diag_log("[play] " + text)
        except Exception:
            pass
        try:
            self.logLine.emit(text)
        except Exception:
            pass

    @staticmethod
    def _resample(data: np.ndarray, src: int, dst: int) -> np.ndarray:
        """Линейный ресемплинг (scipy в EXE нет)."""
        if data is None or len(data) == 0:
            return data
        if not src or not dst or int(src) == int(dst):
            return data
        n_out = int(round(len(data) * float(dst) / float(src)))
        if n_out <= 0 or len(data) < 2:
            return data
        x_in = np.arange(len(data), dtype=np.float64)
        x_out = np.linspace(0, len(data) - 1, n_out)
        return np.interp(x_out, x_in, data).astype(np.float32)

    def _emit_audio(self, pcm: np.ndarray) -> None:
        if pcm is None or len(pcm) == 0:
            return
        bridge = self.bridge
        if bridge is not None and getattr(bridge, "running", False):
            try:
                # Громкости раздельные: phrase_gain — что уходит в кабель
                # (ползунок «Перевод в кабеле»), monitor_gain — что слышит
                # игрок в наушниках («Перевод в наушниках»). Раньше мост
                # получал уже усиленный PCM и фиксированный monitor_gain,
                # поэтому ползунок наушников ничего не менял.
                bridge.set_gains(phrase_gain=self._volume)
                if bridge.push_pcm(pcm, lc.SR_TTS):
                    return
            except Exception as exc:  # noqa: BLE001
                if self._bridge_note != str(exc):
                    self._bridge_note = str(exc)
                    self._log_play(f"мост не принял аудио: {exc}")
        if self._volume != 1.0:
            pcm = np.clip(pcm * self._volume, -1.0, 1.0)
        with self._play_lock:
            sr = self._play_sr or lc.SR_TTS
            self._play_queue.append(self._resample(pcm, lc.SR_TTS, sr))
        self._ensure_playback()

    # Частоты, которые пробуем открыть на выходе по очереди. 24 кГц нет у
    # WASAPI-кабеля, поэтому перебираем до рабочей.
    PLAYBACK_RATES = (lc.SR_TTS, 48000, 44100, 32000, 16000)

    def _ensure_playback(self) -> None:
        import sounddevice as sd
        with self._play_lock:
            if self._playing or not self._play_queue:
                return
            self._playing = True
            out = self._out_idx
            current = self._play_sr
        rates = ([current] if current else []) + [
            r for r in self.PLAYBACK_RATES if r != current]
        err = None
        stream = None
        rate = 0
        for candidate in rates:
            try:
                stream = sd.OutputStream(
                    device=out, channels=1, samplerate=candidate,
                    dtype="float32", blocksize=int(candidate * 0.05),
                    callback=self._play_callback)
                stream.start()
            except Exception as exc:  # noqa: BLE001
                err = exc
                stream = None
                continue
            rate = candidate
            break
        if stream is None:
            with self._play_lock:
                self._playing = False
                # не копим минуты тишины в памяти
                total = sum(len(c) for c in self._play_queue)
                while self._play_queue and total > lc.SR_TTS * 20:
                    total -= len(self._play_queue.pop(0))
            note = f"выход не открылся: {err}"
            if note != self._play_note:
                self._play_note = note
                self._log_play(note)
            return
        with self._play_lock:
            if rate != self._play_sr:
                src = self._play_sr or lc.SR_TTS
                if src != rate:
                    self._play_queue = [
                        self._resample(ch, src, rate) for ch in self._play_queue]
                self._play_sr = rate
            self._play_stream = stream
        note = f"выход {rate} Гц" + ("" if out is None else f", устройство {out}")
        if note != self._play_note:
            self._play_note = note
            self._log_play("воспроизведение — " + note)
        threading.Thread(target=self._drain_play, daemon=True).start()

    def _play_callback(self, outdata, frames, time_info, status) -> None:
        # Исключение в аудио-колбэке PortAudio трактует как отказ потока:
        # дальше он молчит до переоткрытия. Поэтому глушим всё здесь.
        try:
            need = outdata.shape[0]
            out = np.zeros(need, dtype=np.float32)
            pos = 0
            with self._play_lock:
                while pos < need and self._play_queue:
                    chunk = self._play_queue[0]
                    take = min(need - pos, len(chunk))
                    if take <= 0:
                        self._play_queue.pop(0)
                        continue
                    out[pos:pos + take] = chunk[:take]
                    if take < len(chunk):
                        self._play_queue[0] = chunk[take:]
                    else:
                        self._play_queue.pop(0)
                    pos += take
            outdata[:, 0] = out
        except Exception:
            try:
                outdata.fill(0)
            except Exception:
                pass

    def _drain_play(self) -> None:
        import time
        # Пауза перед закрытием: между фразами поток не переоткрываем.
        # Каждое открытие/закрытие — шанс, что устройство (WASAPI-кабель)
        # откажет, и перевод пропадёт.
        idle = 0.0
        while True:
            time.sleep(0.2)
            with self._play_lock:
                if self._play_queue:
                    idle = 0.0
                    continue
                idle += 0.2
                if idle < 2.0:
                    continue
                stream = self._play_stream
                self._play_stream = None
                self._playing = False
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            break

    def _playback_busy(self) -> bool:
        with self._play_lock:
            if self._play_queue:
                return True
        return self._playing

    def _clear_play(self) -> None:
        with self._play_lock:
            self._play_queue.clear()
        try:
            if self._play_stream is not None:
                self._play_stream.stop()
                self._play_stream.close()
        except Exception:
            pass
        self._play_stream = None
        self._playing = False

    # ==================================================================
    # DUCING (заглушение русского в кабеле)
    # ==================================================================
    def _update_duck(self) -> None:
        """Глушить микрофон в кабеле, пока звучит перевод."""
        bridge = self.bridge
        if bridge is None or not getattr(bridge, "running", False):
            return
        # «Фильтр русского»: пока зажата кнопка захвата, русский в кабель
        # НЕ идёт вообще — ни до первого слова перевода, ни между фразами.
        # Раньше заглушка считалась только по busy/playback, поэтому
        # собеседник слышал русский ДО перевода и ПОСЛЕ него.
        need = bool(self._hold_on or self._hold_wait_play or self._busy
                    or self._playback_busy() or self._bridge_pending())
        try:
            bridge.set_duck(need)
        except Exception:
            pass
        self._check_bridge(bridge)
        # Пока звучит СВОЙ перевод, захват игры/наушников должен быть
        # выключен: иначе он ловит наш же Spanish из наушников и озвучивает
        # его обратно русским — слышно как «дублирование себя».
        try:
            self._suppress_capture(need)
        except Exception:
            pass

    def _check_bridge(self, bridge) -> None:
        """Раз в секунду: жив ли выход моста и не теряются ли чанки."""
        now = time.monotonic()
        if now - self._bridge_check < 1.0:
            return
        self._bridge_check = now
        try:
            msg = bridge.ensure_alive()
            if msg and msg != self._bridge_note:
                self._bridge_note = msg
                self._log_play("мост: " + msg)
            dropped = int(bridge.stream_dropped)
            if dropped != self._bridge_dropped:
                self._bridge_dropped = dropped
                self._log_play(
                    f"мост: очередь переполнена, потеряно чанков {dropped} "
                    f"(~{bridge.stream_dropped_sec:.1f} с)")
        except Exception:
            pass

    def _duck(self, flag: bool) -> None:
        bridge = self.bridge
        if bridge is not None and getattr(bridge, "running", False):
            try:
                bridge.set_duck(flag)
            except Exception:
                pass

    # ==================================================================
    # ЗАХВАТ ЗВУКА СОБЕСЕДНИКОВ
    # ==================================================================
    @Slot(result=bool)
    def startCapture(self) -> bool:
        if self._capture_on:
            return True
        try:
            from wasapi_loopback import (
                LoopbackCapture, CaptureMode, list_output_devices_with_loopback)
        except Exception as exc:
            self.errorMessage.emit(f"захват недоступен: {exc}")
            return False
        if self._loopback is None:
            self._loopback = LoopbackCapture(
                on_pcm=self._on_loopback_pcm,
                on_status=lambda status, msg: self.logLine.emit(f"захват: {msg}"),
                on_level=self._on_capture_level)
            self._configure_capture_device(list_output_devices_with_loopback,
                                           CaptureMode)
        ok = self._loopback.start()
        self._capture_on = bool(ok)
        self.captureChanged.emit(self._capture_on)
        if not ok:
            self.errorMessage.emit(self._loopback.get_status_message())
        return self._capture_on

    def _configure_capture_device(self, list_outputs, capture_mode) -> None:
        """Выбрать loopback-устройство: звук игры, а не наш же кабель."""
        try:
            outs = list_outputs()
        except Exception:
            outs = []
        pick = None
        for dev in outs:
            name = str(dev.get("name") or "").lower()
            if dev.get("loopback_index") is None:
                continue
            if "cable" in name:
                continue
            pick = dev
            break
        if pick is None:
            for dev in outs:
                if dev.get("loopback_index") is not None:
                    pick = dev
                    break
        if pick is None:
            return
        try:
            self._loopback.set_mode(capture_mode.WASAPI_ENDPOINT)
            self._loopback.set_device(int(pick["index"]),
                                      int(pick.get("sample_rate") or 48000))
            self.logLine.emit(f"захват собеседника: {pick.get('name', '')}")
        except Exception:
            pass

    @Slot()
    def stopCapture(self) -> None:
        self._stop_capture()

    def _stop_capture(self) -> None:
        if self._loopback is not None:
            try:
                self._loopback.stop()
            except Exception:
                pass
        self._capture_on = False
        self._peer_buf = []
        self._peer_speech = False
        self._peer_silence = 0.0
        self._peer_strong = 0
        self._peer_level = 0.0
        self.captureChanged.emit(False)

    def _on_loopback_pcm(self, pcm, sr: int) -> None:
        """Системный звук -> фразы собеседника -> движок.

        Раньше сюда шёл КАЖДЫЙ блок (десятки миллисекунд): распознавать
        такое бессмысленно. Теперь копим звук и отправляем фразу по паузам.
        """
        tr = self._translator
        if tr is None or not tr.ready:
            return
        if self._incoming_gate_closed():
            # Играет наш русский перевод — в ASR его не отдаём (нет петли).
            self._peer_buf = []
            return
        try:
            block = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        except Exception:
            return
        if block.size == 0:
            return
        sr = int(sr)
        if sr != self._peer_sr and self._peer_buf:
            self._flush_peer_segment()
        self._peer_sr = sr
        block_sec = len(block) / float(sr)
        rms = float(np.sqrt((block.astype(np.float64) ** 2).mean()))
        self._peer_rms.append(rms)
        if len(self._peer_rms) > 400:
            self._peer_rms.pop(0)
        floor = float(np.percentile(self._peer_rms, 20)) if self._peer_rms else 0.0
        self._peer_noise = floor
        thr = max(floor * 2.5, 0.004)
        if rms > thr:
            self._peer_speech = True
            self._peer_silence = 0.0
            if rms > thr * 1.6:
                self._peer_strong += 1
        else:
            self._peer_silence += block_sec
        self._peer_buf.append(block)
        db = 20.0 * float(np.log10(max(rms, 1e-6)))
        lvl = max(0.0, min(1.0, (db + 55.0) / 55.0))
        self._peer_level = max(lvl, self._peer_level * 0.6)
        self._peer_acc += block_sec
        # Промежуточное распознавание раз в ~0.9 с речи: показываем текст,
        # но не переводим и не озвучиваем его.
        import time as _t
        if (self._peer_speech and self._incoming_on
                and self._peer_acc - self._peer_partial_acc >= 0.9
                and _t.time() - self._peer_partial_t >= 0.7):
            self._peer_partial_acc = self._peer_acc
            self._peer_partial_t = _t.time()
            self._send_peer_partial()
        if self._peer_silence >= PEER_SILENCE_END and self._peer_speech:
            self._flush_peer_segment()
        elif len(self._peer_buf) * block_sec >= PEER_MAX_SEG:
            self._flush_peer_segment()

    def _flush_peer_segment(self) -> None:
        """Отправить накопленную фразу собеседника в движок."""
        buf = self._peer_buf
        had_speech = self._peer_speech
        strong = self._peer_strong
        sr = self._peer_sr
        self._peer_buf = []
        self._peer_speech = False
        self._peer_strong = 0
        self._peer_silence = 0.0
        self._peer_acc = 0.0
        self._peer_partial_acc = 0.0
        self._peer_partial = ""
        self.peerPartialChanged.emit()
        tr = self._translator
        if not buf or not had_speech or strong < 3:
            return
        if tr is None or not tr.ready:
            return
        audio = self._trim_silence(np.concatenate(buf))
        dur = len(audio) / float(sr)
        if dur < PEER_MIN_SPEECH:
            return
        seg_rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
        floor = self._peer_noise if self._peer_noise > 0 else 0.001
        if seg_rms < floor * 2.0:
            return
        # Режем на небольшие куски: одна огромная JSON-строка (18 с PCM)
        # терялась при записи в stdin движка на Windows.
        step = max(1, int(PEER_SEND_CHUNK * sr))
        sent = 0
        for i in range(0, len(audio), step):
            part = audio[i:i + step]
            if len(part) < int(0.2 * sr):
                continue
            pcm = (np.clip(part, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
            if not tr.send_peer_pcm(pcm, sr):
                break
            sent += 1
        err = getattr(tr, "last_send_error", "")
        if sent:
            self.logLine.emit(
                f"фраза собеседника на разбор ({dur:.1f} с, {sent} част.)")
            if err:
                self.errorMessage.emit(f"движок не принял звук: {err}")
        elif err:
            self.errorMessage.emit(f"движок не принял звук собеседника: {err}")

    def _send_peer_partial(self) -> None:
        """Отправить движку срез ещё не законченной реплики (только показ)."""
        tr = self._translator
        if tr is None or not tr.ready or not self._peer_buf:
            return
        try:
            audio = np.concatenate(self._peer_buf)
        except Exception:
            return
        # не больше 12 секунд: промежуточный срез нужен только для показа
        max_len = int(12.0 * self._peer_sr)
        if len(audio) > max_len:
            audio = audio[-max_len:]
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        try:
            tr.send_peer_pcm(pcm, self._peer_sr, partial=True)
        except Exception:
            pass

    def _incoming_gate_closed(self) -> bool:
        """Идёт воспроизведение нашего перевода — захват молчит."""
        if self._incoming_active or self._incoming_playing:
            return True
        lb = self._loopback
        try:
            return bool(lb is not None and lb.is_speaking())
        except Exception:
            return False

    def _on_capture_level(self, lv: float) -> None:
        self._peer_level = float(lv)
        self.peerLevelChanged.emit(self._peer_level)

    # ==================================================================
    # ВХОДЯЩАЯ ОЗВУЧКА
    # ==================================================================
    def _speak_incoming(self, text: str) -> None:
        """Русский текст перевода собеседника -> синтез -> наушники."""
        tr = self._translator
        text = (text or "").strip()
        if not text or tr is None or not tr.ready:
            return
        self._incoming_seq += 1
        seq = self._incoming_seq
        self._set_incoming_active(True)
        try:
            ok = tr.incoming_speak(text, seq)
        except Exception as exc:
            self.errorMessage.emit(f"входящая озвучка не запустилась: {exc}")
            self._set_incoming_active(False)
            return
        if not ok:
            self._set_incoming_active(False)
            return
        self._watchdog.start()
        self._suppress_capture(True)

    def _set_incoming_active(self, flag: bool) -> None:
        if self._incoming_active == flag:
            return
        self._incoming_active = flag
        self.incomingActiveChanged.emit(flag)

    def _suppress_capture(self, flag: bool) -> None:
        """Защита от аудиопетли: пока играем свой русский, не слушаем игру."""
        lb = self._loopback
        try:
            if lb is not None:
                lb.set_speaking(bool(flag))
        except Exception:
            pass

    def _incoming_timeout(self) -> None:
        if self._incoming_active:
            self.logLine.emit("входящая озвучка не подтвердилась — снимаю блокировку")
            self._set_incoming_active(False)
            self._suppress_capture(False)

    def _incoming_finished(self) -> None:
        self._watchdog.stop()
        self._set_incoming_active(False)
        self._suppress_capture(False)

    def _emit_incoming_audio(self, pcm: np.ndarray) -> None:
        """Входящий перевод — ТОЛЬКО в наушники, никогда в кабель."""
        if pcm is None or len(pcm) == 0:
            return
        data = np.asarray(pcm, dtype=np.float32)
        bridge = self.bridge
        # Мост умеет отдельную шину прослушивания: только если она есть.
        if (bridge is not None and getattr(bridge, "running", False)
                and getattr(bridge, "monitor_device", None) is not None):
            try:
                # Громкость наушников применяет мост (monitor_gain);
                # иначе ползунок «Перевод в наушниках» не действовал бы.
                bridge.set_gains(monitor_gain=self._incoming_volume)
                if bridge.push_incoming_pcm(data, lc.SR_TTS):
                    return
            except Exception:
                pass
        if self._incoming_volume != 1.0:
            data = np.clip(data * self._incoming_volume, -1.0, 1.0)
        with self._incoming_lock:
            self._incoming_q.append(data)
        self._ensure_incoming_playback()

    def _ensure_incoming_playback(self) -> None:
        import sounddevice as sd
        with self._incoming_lock:
            if self._incoming_playing or not self._incoming_q:
                return
            self._incoming_playing = True
            out = self._monitor_idx
        try:
            self._incoming_stream = sd.OutputStream(
                device=out, channels=1, samplerate=lc.SR_TTS,
                dtype="float32", blocksize=int(lc.SR_TTS * 0.05),
                callback=self._incoming_callback)
            self._incoming_stream.start()
        except Exception:
            with self._incoming_lock:
                self._incoming_playing = False
            return
        threading.Thread(target=self._drain_incoming, daemon=True).start()

    def _incoming_callback(self, outdata, frames, time_info, status) -> None:
        need = outdata.shape[0]
        out = np.zeros(need, dtype=np.float32)
        pos = 0
        with self._incoming_lock:
            while pos < need and self._incoming_q:
                chunk = self._incoming_q[0]
                take = min(need - pos, len(chunk))
                if take <= 0:
                    self._incoming_q.pop(0)
                    continue
                out[pos:pos + take] = chunk[:take]
                if take < len(chunk):
                    self._incoming_q[0] = chunk[take:]
                else:
                    self._incoming_q.pop(0)
                pos += take
        outdata[:, 0] = out

    def _drain_incoming(self) -> None:
        import time
        while True:
            time.sleep(0.2)
            with self._incoming_lock:
                empty = not self._incoming_q
                if empty and self._incoming_stream is not None:
                    stream = self._incoming_stream
                    self._incoming_stream = None
                    self._incoming_playing = False
                else:
                    stream = None
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                break

    def _clear_incoming(self) -> None:
        with self._incoming_lock:
            self._incoming_q.clear()
        try:
            if self._incoming_stream is not None:
                self._incoming_stream.stop()
                self._incoming_stream.close()
        except Exception:
            pass
        self._incoming_stream = None
        self._incoming_playing = False
        self._incoming_finished()

    # ==================================================================
    # ПОВТОР ИЗ ИСТОРИИ ПЕРЕВОДОВ
    # ==================================================================
    @Slot(str)
    def replay(self, text: str) -> None:
        """Ещё раз озвучить текст записи (кнопка ▶ в «Последних переводах»)."""
        text = (text or "").strip()
        if not text:
            return
        tr = self._translator
        if tr is None or not getattr(tr, "ready", False):
            self.errorMessage.emit("движок не запущен — сначала «Запустить модель»")
            return
        self._replay_seq += 1
        try:
            ok = tr.incoming_speak(text, self._replay_seq)
        except Exception as exc:
            self.errorMessage.emit(f"повтор не удался: {exc}")
            return
        if not ok:
            self.errorMessage.emit("движок занят — повтори чуть позже")

    # ==================================================================
    # СОБЫТИЯ ОТ ДВИЖКА
    # ==================================================================
    def _on_event(self, kind: str, data) -> None:
        if kind == "chunk":
            try:
                pcm = lc.pcm_to_float16(base64.b64decode(data["pcm"]))
                self._emit_audio(pcm)
            except Exception:
                pass
        elif kind == "done":
            self._set_busy(False)
            self._pump_queue()
        elif kind == "text":
            pass
        elif kind == "peer_text":
            src_lang = str(data.get("lang", "") or "")
            original = str(data.get("src", "") or "")
            ru = str(data.get("ru", "") or "")
            missing = str(data.get("missing_mt", "") or "")
            # (язык, перевод, оригинал) — история показывает оба текста
            self._peer_partial = ""
            self.peerPartialChanged.emit()
            self.peerTextReady.emit(src_lang, ru, original)
            if original or ru:
                self._last_in = (original, ru)
                self.lastPhraseChanged.emit()
            if missing:
                self.errorMessage.emit(
                    f"нет модели перевода {missing}: фраза распознана, "
                    f"но не переведена")
                return
            if ru and self._incoming_on:
                self._speak_incoming(ru)
        elif kind == "incoming_chunk":
            # generation guard: старый синтез не должен попасть в новую
            # реплику (например, после смены языка или остановки)
            try:
                seq = int(data.get("seq", self._incoming_seq))
            except Exception:
                seq = self._incoming_seq
            if seq != self._incoming_seq:
                self._cancelled += 1
                return
            try:
                pcm = lc.pcm_to_float16(base64.b64decode(data["pcm"]))
                self._emit_incoming_audio(pcm)
            except Exception:
                pass
        elif kind == "incoming_done":
            self._incoming_finished()
            self._pump_queue()
        elif kind == "models":
            self._apply_models(data)
            self.logLine.emit(f"модели: распознавание — {self._asr_model}")
        elif kind == "package":
            pair = str(data.get("pair", "") or "")
            state = str(data.get("state", "") or "")
            msg = str(data.get("message", "") or "")
            if state == "downloading":
                self._package_status = f"скачиваю пакет {pair}…"
                self.logLine.emit(self._package_status)
            elif state == "installed":
                self._package_status = f"пакет {pair} установлен"
                self.logLine.emit(self._package_status)
                self.requestModels()
            else:
                self._package_status = f"пакет {pair}: ошибка {msg}".strip()
                self.errorMessage.emit(self._package_status)
            self.packageChanged.emit()
        elif kind == "auto_download":
            self._auto_download = bool(data.get("on"))
            self.autoDownloadChanged.emit()
        elif kind == "catalog":
            self._apply_catalog(data)
        elif kind == "catalog_refreshed":
            if data.get("ok"):
                self._set_catalog_status(
                    "обновлено: " + str(data.get("found", 0)) + " моделей"
                    + " (ASR " + str(data.get("asr", 0))
                    + ", перевод " + str(data.get("mt", 0)) + ")")
            else:
                self._set_catalog_status(
                    "не обновился: " + str(data.get("error") or "нет сети"))
        elif kind == "download":
            self._apply_download(data)
        elif kind == "verify":
            ok = bool(data.get("ok"))
            name = str(data.get("id", "") or "")
            if ok:
                self.logLine.emit(f"целостность {name}: ok "
                                  f"({data.get('size_mb', 0)} МБ)")
            else:
                self.errorMessage.emit(
                    f"проверка {name}: " + "; ".join(data.get("missing") or []))
        elif kind == "model_removed":
            self.logLine.emit(f"модель удалена: {data.get('id')} "
                              f"({data.get('size_mb', 0)} МБ)")
            self.requestCatalog()
            self.requestPacks()
        elif kind == "model_selected":
            self.logLine.emit(f"выбрана модель {data.get('kind')}: "
                              f"{data.get('value')}")
            self.requestModels()
            self.requestCatalog()
        elif kind == "packs":
            self._packs = list(data.get("packs") or [])
            self.packsChanged.emit()
        elif kind == "pack":
            self._apply_pack(data)
        elif kind == "pack_verify":
            code = str(data.get("code", "") or "")
            if data.get("ok"):
                self.logLine.emit(f"пакет {code}: целостность ok")
            else:
                self.errorMessage.emit(
                    f"пакет {code}: проблемы — "
                    + "; ".join(p.get("id", "") for p in
                                 (data.get("problems") or [])))
        elif kind == "peer_lang":
            code = str(data.get("code", "") or "")
            if code and code != "auto":
                self._peer_lang = code
            else:
                self._peer_confirmed = str(
                    data.get("confirmed", self._peer_confirmed) or "")
            self._peer_prob = float(data.get("prob", 0.0) or 0.0)
            self.peerLangChanged.emit()
            self.peerLangInfoChanged.emit()
        elif kind == "peer_lang_detected":
            self._peer_confirmed = str(data.get("confirmed", "") or "")
            self._peer_prob = float(data.get("prob", 0.0) or 0.0)
            self._peer_reason = str(data.get("reason", "") or "")
            self.peerLangInfoChanged.emit()
        elif kind == "unloaded":
            self._models_loaded = False
            self.modelsLoadedChanged.emit()
        elif kind == "mode":
            self._apply_mode(data)
        elif kind == "peer_partial":
            text = str(data.get("text", "") or "").strip()
            self._peer_partial = text
            self.peerPartialChanged.emit()
        elif kind == "metrics":
            self._apply_metrics(data)
        elif kind == "stats":
            # диагностика: RAM/VRAM/очереди — показываем и пишем в лог
            info = {k: data.get(k) for k in
                    ("rss_mb", "vram_mb", "dropped", "cancelled")}
            queues = data.get("queues") or {}
            info["queue"] = queues.get("peer", 0)
            self._metrics = {**self._metrics, **info}
            self.metricsChanged.emit()
            try:
                import json
                import time
                logs = os.path.join(sp.workspace(), "logs")
                os.makedirs(logs, exist_ok=True)
                with open(os.path.join(logs, "diagnostics.log"), "a",
                          encoding="utf-8") as fh:
                    fh.write(json.dumps({"ts": time.strftime(
                        "%Y-%m-%d %H:%M:%S"), "stats": info},
                        ensure_ascii=False) + "\n")
            except Exception:
                pass
        elif kind == "src_lang":
            code = str(data.get("code", "") or "")
            if code:
                self._src_lang = code
            self.modelsChanged.emit()
        elif kind == "asr":
            name = str(data.get("name", "") or "")
            if name:
                self._asr_model = name
            self.modelsChanged.emit()
            self.logLine.emit(f"распознавание: {name or self._asr_model}")
        elif kind == "state":
            if data.get("ready"):
                self._set_state("READY")
                self._push_settings()
                # Профиль мог быть выбран, пока движок грузился: argv
                # процесса уже не поменять, поэтому после ready явно
                # пересобираем эмбеддинг активного профиля.
                self._sync_voice_reference()
            elif data.get("error"):
                self._set_state("ERROR", data["error"])
        elif kind == "lang":
            pass
        elif kind == "log":
            text = str(data)
            # технические эхо-строки движка не показываем тостами
            if text.startswith("[engine] команда:"):
                return
            self.logLine.emit(text)
        elif kind == "error":
            self._set_state("ERROR", str(data))

    def _on_text(self, ru: str, es: str, tone: str = "") -> None:
        self._last_out = (ru, es)
        self.lastPhraseChanged.emit()
        self.textReady.emit(ru, es, tone)
        self._set_busy(False)
        self._pump_queue()

    def _push_settings(self) -> None:
        if self._translator is None:
            return
        self._translator.set_lang(self._lang_code)
        self._translator.set_mode(self._mode)
        self._translator.set_auto_download(self._auto_download)
        self._translator.set_src_lang(self._src_lang)
        self._translator.set_peer_lang(self._peer_lang)
        self._translator.set_liveliness(self._liveliness)
        if self._asr_model:
            self._translator.set_asr_model(self._asr_model)
        # какие модели реально установлены — для экрана настроек
        self._translator.request_models()

    def _apply_catalog(self, data) -> None:
        self._catalog = [m for m in (data.get("models") or [])
                         if isinstance(m, dict)]
        self._models_loaded = bool(data.get("loaded"))
        self.catalogChanged.emit()
        self.modelsLoadedChanged.emit()

    def _apply_download(self, data) -> None:
        model_id = str(data.get("id", "") or "")
        request = str(data.get("request", "") or model_id)
        state = str(data.get("state", "") or "")
        self._downloads[model_id] = {
            "id": model_id, "request": request, "state": state,
            "percent": int(data.get("percent", 0) or 0),
            "mb": float(data.get("mb", 0) or 0),
            "expected_mb": float(data.get("expected_mb", 0) or 0),
            "label": str(data.get("label", "") or ""),
            "message": str(data.get("message", "") or ""),
        }
        self.downloadsChanged.emit()
        if state in ("READY", "ERROR", "CANCELLED"):
            if state == "READY":
                self.logLine.emit(f"модель установлена: {model_id}")
                self.requestCatalog()
                self.requestPacks()
            elif state == "ERROR":
                self.errorMessage.emit(
                    f"загрузка {model_id}: {self._downloads[model_id]['message']}")
            else:
                self.logLine.emit(f"загрузка {model_id} отменена")
            self._downloads.pop(model_id, None)
            self.downloadsChanged.emit()

    def _apply_mode(self, data) -> None:
        """Фактические параметры режима от движка."""
        self._mode = str(data.get("mode", self._mode) or self._mode)
        self._mode_info = (
            f"ASR {data.get('asr_model', '')} ({data.get('asr_compute', '')})"
            f", beam {data.get('beam_size', '')}"
            f", TTS chunk {data.get('stream_chunk', '')}"
            f", проверок синтеза {data.get('verify_attempts', '')}"
            f"; вариантов ASR: {data.get('asr_alternatives', 0)}"
            f", TTS: {data.get('tts_alternatives', 0)}")
        self.modeChanged.emit()

    def _apply_metrics(self, data) -> None:
        """Метрики реплики: в UI (последние) и в диагностический лог."""
        self._metrics = {k: v for k, v in data.items() if k != "event"}
        try:
            self._dropped = int(data.get("dropped", self._dropped) or 0)
            self._cancelled = int(data.get("cancelled", self._cancelled) or 0)
        except Exception:
            pass
        self.metricsChanged.emit()
        try:
            import json
            import time
            logs = os.path.join(sp.workspace(), "logs")
            os.makedirs(logs, exist_ok=True)
            line = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), **self._metrics}
            with open(os.path.join(logs, "diagnostics.log"), "a",
                      encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _apply_pack(self, data) -> None:
        code = str(data.get("code", "") or "")
        state = str(data.get("state", "") or "")
        msg = str(data.get("message", "") or "")
        if state in ("DOWNLOADING", "INSTALLING"):
            self._package_status = f"пакет {code}: {state.lower()}…"
        elif state == "READY":
            self._package_status = f"пакет {code} готов"
            self.logLine.emit(self._package_status)
            self.requestPacks()
            self.requestCatalog()
            self.requestModels()
        elif state == "REMOVED":
            self._package_status = f"пакет {code} удалён"
            self.logLine.emit(self._package_status)
            self.requestPacks()
            self.requestCatalog()
        else:
            self._package_status = f"пакет {code}: ошибка {msg}".strip()
            self.errorMessage.emit(self._package_status)
        self.packageChanged.emit()

    def _apply_models(self, data) -> None:
        """Сохранить ответ движка о моделях и обновить UI."""
        self._asr_models = [
            {"name": str(m.get("name", "")),
             "label": str(m.get("name", "")),
             "active": bool(m.get("active"))}
            for m in (data.get("asr") or []) if isinstance(m, dict)]
        cur = str(data.get("asr_current") or "")
        if cur:
            self._asr_model = cur
        self._tts_models = [
            {"name": str(m.get("name", "")),
             "installed": bool(m.get("installed"))}
            for m in (data.get("tts") or []) if isinstance(m, dict)]
        self._tts_model = str(data.get("tts_current") or "")
        self._src_langs = [
            {"code": str(m.get("code", "")),
             "label": str(m.get("name", "") or m.get("code", ""))}
            for m in (data.get("src_languages") or []) if isinstance(m, dict)]
        cur_src = str(data.get("src_current") or "")
        if cur_src:
            self._src_lang = cur_src
        self._mt_info = [
            {"pair": str(m.get("pair", "")),
             "installed": bool(m.get("installed")),
             "models": ", ".join(m.get("models") or [])}
            for m in (data.get("mt") or []) if isinstance(m, dict)]
        self.modelsChanged.emit()

    # ==================================================================
    # СЛУЖЕБНОЕ
    # ==================================================================
    def _emit_level(self) -> None:
        level = float(self._level)
        rec = self.recorder
        if rec is not None:
            try:
                level = max(level, float(getattr(rec, "level", 0.0) or 0.0))
            except Exception:
                pass
        self.levelChanged.emit(level)

    def _poll(self) -> None:
        if self._translator is not None:
            try:
                self._translator.poll()
            except Exception:
                pass