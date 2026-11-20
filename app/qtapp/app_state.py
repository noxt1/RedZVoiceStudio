"""Общее состояние Qt-интерфейса.

Класс `AppState` — единственный источник правды для QML. Он НЕ содержит
Tkinter и не создаёт виджетов: только данные и вызовы существующих
модулей (studio_paths, studio_core, mic_bridge, hotkeys, cable).

Живой перевод берётся из `live_engine.py` (headless-обёртка над
LiveTranslator/MicBridge), озвучка и запись — из studio_core.
"""

from __future__ import annotations

import json
import os
import threading
import time

from PySide6.QtCore import QObject, Signal, Property, Slot, QTimer, QUrl
from PySide6.QtGui import QDesktopServices

import branding
import reports
import studio_paths as sp
import studio_core as core
import hotkeys as hk
import cable as cable_mod

# Цвета статуса движка
STATE_STOPPED = "STOPPED"
STATE_LOADING = "LOADING"
STATE_READY = "READY"
STATE_ERROR = "ERROR"


class AppState(QObject):
    """Состояние приложения для QML."""

    # ---- сигналы: данные изменились ----
    engineStateChanged = Signal()             # STOPPED/LOADING/READY/ERROR
    engineErrorChanged = Signal()
    bridgeStateChanged = Signal(bool)         # запущен ли мост
    devicesChanged = Signal()                 # список устройств обновлён
    hotkeysChanged = Signal(bool)             # включены ли хоткеи фраз
    hotkeyComboChanged = Signal()            # изменилась комбинация клавиш
    phraseBankChanged = Signal()              # банк фраз изменён
    recordsChanged = Signal()                 # записи образцов изменены
    statusMessage = Signal(str, str)          # (текст, тип: ok/warn/err/info)
    busyChanged = Signal(bool)
    nameChanged = Signal()
    bankLangChanged = Signal()
    livelinessChanged = Signal()
    userNameChanged = Signal()
    vramChanged = Signal()                    # VRAM/имя GPU обновились
    settingsChanged = Signal()                # пользовательские настройки UI
    profilesChanged = Signal()                # профили голоса / активный профиль
    phrasesChanged = Signal()                 # свои фразы добавлены/удалены
    reportChanged = Signal()                  # отчёт для поддержки собран

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._engine_state = STATE_STOPPED
        self._engine_error = ""
        self._bridge_on = False
        self._hotkeys_on = False
        self._busy = False
        # отчёт для поддержки: путь к последнему zip и статус
        self._report_path = ""
        self._report_status = ""

        # --- GPU / VRAM (карточка на главной) ---
        self._vram_used = 0
        self._vram_total = 0
        self._gpu_name = ""

        # --- данные пользователя ---
        self._name = "Cyril"
        self._lang = "ru"            # язык подсказок записи (ru/es)
        self._bank_lang = "es"       # язык банка фраз (es/en/ow/it)
        self._liveliness = 2         # живость интонации 0..3

        # --- устройства ---
        self._in_device: int | None = None
        self._out_device: int | None = None
        self._in_list: list[tuple[int, str]] = []
        self._out_list: list[tuple[int, str]] = []

        # --- аудио ---
        self.bridge = None           # MicBridge | None
        self.recorder = core.Recorder()

        # --- фразы / записи ---
        self._phrases: list[dict] = []
        self._records: dict[int, str] = {}

        # --- хоткеи ---
        self.hotkeys = hk.GlobalHotkeys()
        self._hk_queue: list[str] = []
        self._hk_lock = threading.Lock()
        self._ptt_active = False

        # --- таймеры Qt ---
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

        # отпускание push-to-talk: WM_HOTKEY приходит только на нажатии
        self._ptt_timer = QTimer(self)
        self._ptt_timer.setInterval(30)
        self._ptt_timer.timeout.connect(self._poll_ptt_release)
        self._ptt_timer.start()

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(2000)
        self._status_timer.timeout.connect(self._tick_status)

        # VRAM считывается через nvidia-smi (если её нет — карточка пустая)
        self._vram_timer = QTimer(self)
        self._vram_timer.setInterval(4000)
        self._vram_timer.timeout.connect(self._refresh_vram)
        self._vram_timer.start()
        QTimer.singleShot(400, self._refresh_vram)

        # --- пользовательские настройки (workspace/ui_settings.json) ---
        cfg = self._load_settings()
        # Миграция: раньше всё было выключено по умолчанию, и старый
        # ui_settings.json перекрывал новые значения. Один раз поднимаем
        # «всё готово» для существующих установок.
        fresh = int(cfg.get("defaults_v", 1) or 1) < 2
        self._hints_on = bool(cfg.get("hints", True))
        # Модели НЕ грузим сами при старте: это явное действие пользователя.
        # Старые ui_settings.json содержали auto_start_engine=true, поэтому
        # одного значения мало — нужен ещё флаг «пользователь включал сам».
        self._auto_start = bool(cfg.get("auto_start_engine", False)) and \
            bool(cfg.get("auto_start_explicit", False))
        self._auto_start_explicit = bool(cfg.get("auto_start_explicit", False))
        self._fullscreen = bool(cfg.get("fullscreen", False))
        self._voice_volume = int(cfg.get("voice_volume", 85))
        # входящий перевод (речь собеседника -> RU -> наушники)
        self._incoming_on = bool(cfg.get("incoming_on", False))
        self._incoming_volume = int(cfg.get("incoming_volume", 100))
        # русский микрофон в кабель: по умолчанию ВКЛЮЧЕН — собеседники
        # слышат живую речь; на время перевода мост её заглушает.
        # Переключатель позволяет полностью убрать русский из кабеля.
        self._cable_mic = bool(cfg.get("cable_mic", True))
        # Один раз чиним старую миграцию: раньше дефолт был false,
        # и сохранённый false не давал русскому идти в кабель.
        if int(cfg.get("cable_mic_v", 0) or 0) < 1:
            self._cable_mic = True
        self._cable_mic_migrated = True
        # наушники для входящего/исходящего перевода (-1 = авто)
        self._monitor_device = int(cfg.get("monitor_device", -1) or -1)
        # исходящий канал можно выключить независимо от входящего
        self._outgoing_on = bool(cfg.get("outgoing_on", True))
        # автоскачивание языковых пакетов — по умолчанию ВЫКЛЮЧЕНО
        self._auto_download = bool(cfg.get("auto_download", False))
        # глобальная клавиша push-to-talk (меняется в Настройках)
        self._hotkey = str(cfg.get("hotkey", "alt+capslock") or "alt+capslock")
        # при старте всё уже включено: хоткеи, мост к кабелю, движок
        self._hotkeys_pref = True if fresh else bool(cfg.get("hotkeys_on", True))
        self._bridge_pref = True if fresh else bool(cfg.get("bridge_on", True))
        # режим работы моделей: fast / balanced / quality / manual
        mode = str(cfg.get("mode", "balanced") or "balanced")
        self._mode = mode if mode in ("fast", "balanced", "quality", "manual") \
            else "balanced"
        # языки: источник (язык пользователя), вывод (ru -> X) и язык собеседника
        self._src_lang = str(cfg.get("src_lang", "ru"))
        self._target_lang = str(cfg.get("target_lang", "es"))
        self._peer_lang = str(cfg.get("peer_lang", "auto"))
        # выбранная модель распознавания ('' — по умолчанию движка)
        self._asr_model = str(cfg.get("asr_model", "") or "")
        self._active_profile = sp.get_active_profile()

        # банк фраз нужен сразу — страницы QML читают его при загрузке
        try:
            self._load_phrases()
        except Exception:
            pass

        # Стартовое состояние «всё готово»: устройства, мост, хоткеи, движок.
        # Отложено, чтобы QML успел подписаться на сигналы.
        QTimer.singleShot(1200, self._apply_startup_defaults)

    # ==================================================================
    # СВОЙСТВА ДЛЯ QML
    # ==================================================================
    @Property(str, notify=engineStateChanged)
    def engineState(self) -> str:
        return self._engine_state

    @Property(str, notify=engineErrorChanged)
    def engineError(self) -> str:
        return self._engine_error

    @Property(bool, notify=bridgeStateChanged)
    def bridgeOn(self) -> bool:
        return self._bridge_on

    @Property(bool, notify=hotkeysChanged)
    def hotkeysOn(self) -> bool:
        return self._hotkeys_on

    @Property(str, notify=hotkeyComboChanged)
    def hotkeyCombo(self) -> str:
        """Комбинация для непрерывного режима, как её вводит пользователь."""
        return self._hotkey

    @Slot(result=str)
    def hotkeyPretty(self) -> str:
        return hk.pretty_combo(self._hotkey)

    @Slot(str, result=bool)
    def setHotkey(self, combo: str) -> bool:
        """Заменить горячую клавишу (например, 'alt+capslock' или 'f9')."""
        combo = " ".join((combo or "").strip().lower().split())
        if not combo:
            return False
        key, _mods = hk.parse_combo(combo)
        if not key:
            self.statusMessage.emit(f"не понимаю клавишу: {combo}", "err")
            return False
        was_on = self._hotkeys_on
        if was_on:
            try:
                self.hotkeys.unregister_prefix("live:")
            except Exception:
                pass
            self._hotkeys_on = False
        self._hotkey = combo
        self.hotkeyComboChanged.emit()
        self._save_settings()
        if was_on:
            return self.toggleHotkeys()
        self.statusMessage.emit(
            f"клавиша сохранена: {hk.pretty_combo(combo)}", "ok")
        return True

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property("QVariantList", notify=devicesChanged)
    def inputDevices(self):
        return [{"id": i, "name": n} for i, n in self._in_list]

    @Property("QVariantList", notify=devicesChanged)
    def outputDevices(self):
        return [{"id": i, "name": n} for i, n in self._out_list]

    @Property(int, notify=devicesChanged)
    def inDevice(self) -> int:
        return self._in_device if self._in_device is not None else -1

    @Property(int, notify=devicesChanged)
    def outDevice(self) -> int:
        return self._out_device if self._out_device is not None else -1

    @Property("QVariantList", notify=phraseBankChanged)
    def phraseBank(self):
        return self._phrases

    @Property("QVariantList", notify=recordsChanged)
    def records(self):
        return [{"index": k, "path": v} for k, v in sorted(self._records.items())]

    @Property(str, notify=userNameChanged)
    def userName(self) -> str:
        return self._name

    @Property(str, notify=bankLangChanged)
    def bankLang(self) -> str:
        return self._bank_lang

    @Property(int, notify=livelinessChanged)
    def liveliness(self) -> int:
        return self._liveliness

    @Property(int, notify=vramChanged)
    def vramUsed(self) -> int:
        """Занятая видеопамять, МБ (0 — данных нет)."""
        return self._vram_used

    @Property(int, notify=vramChanged)
    def vramTotal(self) -> int:
        """Всего видеопамяти, МБ (0 — данных нет)."""
        return self._vram_total

    @Property(str, notify=vramChanged)
    def gpuName(self) -> str:
        """Имя видеокарты (пусто, если nvidia-smi недоступен)."""
        return self._gpu_name

    # ------------------------------------------------------------------
    # Пользовательские настройки
    # ------------------------------------------------------------------
    @Property(bool, notify=settingsChanged)
    def hintsOn(self) -> bool:
        return self._hints_on

    @Property(bool, notify=settingsChanged)
    def autoStartEngine(self) -> bool:
        return self._auto_start

    @Property(bool, notify=settingsChanged)
    def fullscreen(self) -> bool:
        return self._fullscreen

    @Property(int, notify=settingsChanged)
    def voiceVolume(self) -> int:
        """Громкость перевода в кабель, проценты (0..150)."""
        return self._voice_volume

    @Property(bool, notify=settingsChanged)
    def cableMicOn(self) -> bool:
        """Приглушить русский в кабеле (False = микрофон проходит)."""
        return self._cable_mic

    @Property(int, notify=settingsChanged)
    def monitorDevice(self) -> int:
        """Устройство наушников для перевода (-1 — выбрать автоматически)."""
        return self._monitor_device

    @Property(str, notify=profilesChanged)
    def activeProfile(self) -> str:
        return self._active_profile

    # ------------------------------------------------------------------
    # Входящий перевод и языки
    # ------------------------------------------------------------------
    @Property(bool, notify=settingsChanged)
    def incomingOn(self) -> bool:
        """Перевод речи собеседника включён."""
        return self._incoming_on

    @Property(int, notify=settingsChanged)
    def incomingVolume(self) -> int:
        """Громкость входящего перевода в наушниках, проценты."""
        return self._incoming_volume

    @Property(bool, notify=settingsChanged)
    def outgoingOn(self) -> bool:
        """Исходящий перевод (речь пользователя) включён."""
        return self._outgoing_on

    @Property(str, notify=settingsChanged)
    def mode(self) -> str:
        """Режим работы моделей (fast/balanced/quality/manual)."""
        return self._mode

    @Slot(str)
    def setMode(self, code: str) -> None:
        code = (code or "").strip().lower()
        if code not in ("fast", "balanced", "quality", "manual"):
            return
        self._mode = code
        eng = getattr(self, "_live_engine", None)
        if eng is not None:
            try:
                eng.setMode(code)
            except Exception:
                pass
        self._save_settings()
        self.settingsChanged.emit()

    @Property(bool, notify=settingsChanged)
    def autoDownload(self) -> bool:
        """Разрешена ли автоматическая загрузка языковых пакетов."""
        return self._auto_download

    @Slot(bool)
    def setAutoDownload(self, on: bool) -> None:
        self._auto_download = bool(on)
        eng = getattr(self, "_live_engine", None)
        if eng is not None:
            try:
                eng.setAutoDownload(self._auto_download)
            except Exception:
                pass
        self._save_settings()
        self.settingsChanged.emit()

    @Property(str, notify=settingsChanged)
    def srcLang(self) -> str:
        """Язык пользователя (с какого языка переводится его речь)."""
        return self._src_lang

    @Property(str, notify=settingsChanged)
    def targetLang(self) -> str:
        """Язык, на который переводится русская речь."""
        return self._target_lang

    @Property(str, notify=settingsChanged)
    def peerLang(self) -> str:
        """Язык речи собеседника ('auto' — определить самому)."""
        return self._peer_lang

    @Property(str, notify=settingsChanged)
    def asrModel(self) -> str:
        return self._asr_model

    @Property("QVariantList", constant=True)
    def targetLangItems(self):
        return [
            {"label": "Испанский - es_Latn", "value": "es"},
            {"label": "Английский - en_US", "value": "en"},
            {"label": "Итальянский - it_IT", "value": "it"},
            {"label": "Old West - ow", "value": "ow"},
        ]

    @Property("QVariantList", constant=True)
    def peerLangItems(self):
        return [
            {"label": "авто (определить самому)", "value": "auto"},
            {"label": "Испанский", "value": "es"},
            {"label": "Английский", "value": "en"},
            {"label": "Итальянский", "value": "it"},
            {"label": "Русский", "value": "ru"},
            {"label": "Украинский", "value": "uk"},
            {"label": "Немецкий", "value": "de"},
            {"label": "Французский", "value": "fr"},
            {"label": "Португальский", "value": "pt"},
            {"label": "Польский", "value": "pl"},
            {"label": "Турецкий", "value": "tr"},
        ]

    # ==================================================================
    # СЛОТЫ (вызываются из QML)
    # ==================================================================
    # ------------------------------------------------------------------
    # Слоты: настройки, профили, фразы
    # ------------------------------------------------------------------
    @Slot(bool)
    def setHints(self, on: bool) -> None:
        self._hints_on = bool(on)
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(bool)
    def setAutoStartEngine(self, on: bool) -> None:
        self._auto_start = bool(on)
        self._auto_start_explicit = True
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(bool)
    def setFullscreen(self, on: bool) -> None:
        self._fullscreen = bool(on)
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(int)
    def setVoiceVolume(self, value: int) -> None:
        self._voice_volume = max(0, min(150, int(value)))
        # Это громкость ПЕРЕВОДА в кабеле, а не микрофона: mic_gain не трогаем.
        eng = getattr(self, "_live_engine", None)
        if eng is not None:
            try:
                eng.setVolume(self._voice_volume)
            except Exception:
                pass
        if self.bridge is not None:
            try:
                self.bridge.set_gains(
                    phrase_gain=max(0.0, min(2.0, self._voice_volume / 100.0)))
            except Exception:
                pass
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(bool)
    def setCableMic(self, on: bool) -> None:
        """Включить/выключить русский микрофон в кабеле."""
        self._cable_mic = bool(on)
        if self.bridge is not None:
            try:
                self.bridge.mic_gain = 1.0 if self._cable_mic else 0.0
            except Exception:
                pass
        self._save_settings()
        self.settingsChanged.emit()
        self.statusMessage.emit(
            "русский микрофон в кабеле включён" if self._cable_mic
            else "русский микрофон в кабеле выключен", "info")

    @Slot(int)
    def setMonitorDevice(self, idx: int) -> None:
        """Выбрать наушники для перевода (-1 — авто)."""
        self._monitor_device = int(idx)
        if self.bridge is not None:
            dev = None if self._monitor_device < 0 else self._monitor_device
            try:
                self.bridge.set_monitor_device(dev)
            except Exception as exc:
                self.statusMessage.emit(f"наушники: {exc}", "err")
        eng = getattr(self, "_live_engine", None)
        if eng is not None:
            try:
                eng.setMonitorDevice(self._monitor_device)
            except Exception:
                pass
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(result="QVariantList")
    def profiles(self) -> list:
        try:
            return sp.list_profiles()
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Входящий перевод: настройки сохраняются и сразу идут в движок
    # ------------------------------------------------------------------
    @Slot(bool)
    def setIncoming(self, on: bool) -> None:
        self._incoming_on = bool(on)
        eng = getattr(self, "_live_engine", None)
        if eng is not None:
            try:
                eng.setIncomingEnabled(self._incoming_on)
            except Exception as exc:
                self.statusMessage.emit(f"входящий перевод: {exc}", "err")
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(int)
    def setIncomingVolume(self, value: int) -> None:
        self._incoming_volume = max(0, min(150, int(value)))
        eng = getattr(self, "_live_engine", None)
        if eng is not None:
            try:
                eng.setIncomingVolume(self._incoming_volume)
            except Exception:
                pass
        # Мост держит отдельную громкость для наушников: без этого
        # ползунок менял только сохранённое значение.
        if self.bridge is not None:
            try:
                self.bridge.set_gains(
                    monitor_gain=max(0.0, min(1.5, self._incoming_volume / 100.0)))
            except Exception:
                pass
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(bool)
    def setOutgoing(self, on: bool) -> None:
        self._outgoing_on = bool(on)
        eng = getattr(self, "_live_engine", None)
        if eng is not None:
            try:
                eng.setOutgoing(self._outgoing_on)
            except Exception as exc:
                self.statusMessage.emit(f"исходящий перевод: {exc}", "err")
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(str)
    def setSrcLang(self, code: str) -> None:
        self._src_lang = (code or "ru").strip() or "ru"
        eng = getattr(self, "_live_engine", None)
        if eng is not None:
            try:
                eng.setSrcLang(self._src_lang)
            except Exception:
                pass
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(str)
    def setTargetLang(self, code: str) -> None:
        code = (code or "").strip()
        if code not in ("es", "en", "it", "ow"):
            return
        self._target_lang = code
        eng = getattr(self, "_live_engine", None)
        if eng is not None:
            try:
                eng.setLang(code)
            except Exception:
                pass
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(str)
    def setPeerLang(self, code: str) -> None:
        self._peer_lang = (code or "auto").strip() or "auto"
        eng = getattr(self, "_live_engine", None)
        if eng is not None:
            try:
                eng.setPeerLang(self._peer_lang)
            except Exception:
                pass
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(str)
    def setAsrModel(self, name: str) -> None:
        self._asr_model = (name or "").strip()
        eng = getattr(self, "_live_engine", None)
        if eng is not None:
            try:
                eng.setAsrModel(self._asr_model)
            except Exception:
                pass
        self._save_settings()
        self.settingsChanged.emit()

    @Slot(str)
    def setProfile(self, name: str) -> None:
        name = (name or "").strip()
        if not name:
            return
        try:
            sp.set_active_profile(name)
        except Exception as exc:
            self.statusMessage.emit(f"профиль не переключился: {exc}", "err")
            return
        self._active_profile = name
        self.profilesChanged.emit()
        # Если движок уже загружен, меняем тембр на лету — без перезапуска
        # и без повторной загрузки моделей.
        eng = getattr(self, "_live_engine", None)
        if eng is not None:
            try:
                eng.setProfile(name)
            except Exception as exc:
                self.statusMessage.emit(f"профиль в движке: {exc}", "warn")
        self.statusMessage.emit(f"профиль голоса: {name}", "ok")

    @Slot(str, str)
    def playPhrase(self, phrase_id: str, lang: str = "") -> None:
        """Проиграть готовый файл фразы (mp3 из workspace)."""
        base = f"mx_{phrase_id}"
        names = []
        if lang and lang != "es":
            names.append(f"{base}_{lang}")
        names.append(base)
        paths = sp.output_paths()
        for folder in (paths["player_mp3"], paths["out_mp3"]):
            for name in names:
                path = os.path.join(folder, name + ".mp3")
                if os.path.exists(path):
                    try:
                        from ui import audio_play
                        audio_play.play_file(path)
                    except Exception as exc:
                        self.statusMessage.emit(f"не проигралось: {exc}", "err")
                    return
        self.statusMessage.emit("нет аудио для этой фразы — озвучь её", "warn")

    @Slot(str, str, result=str)
    def addPhrase(self, es: str, ru: str) -> str:
        es = (es or "").strip()
        if not es:
            self.statusMessage.emit("фраза пустая", "warn")
            return ""
        items = self._custom_phrases()
        used = {int(it["id"]) for it in items if str(it.get("id", "")).isdigit()}
        new_id = 101
        while new_id in used:
            new_id += 1
        items.append({"id": new_id, "es": es, "ru": (ru or "").strip()})
        self._save_custom_phrases(items)
        self._load_phrases()
        self.statusMessage.emit(f"фраза {new_id} добавлена", "ok")
        return str(new_id)

    @Slot(str)
    def deletePhrase(self, phrase_id: str) -> None:
        items = self._custom_phrases()
        keep = [it for it in items if str(it.get("id")) != str(phrase_id)]
        if len(keep) == len(items):
            self.statusMessage.emit("встроенную фразу удалить нельзя", "warn")
            return
        self._save_custom_phrases(keep)
        self._load_phrases()
        self.statusMessage.emit("фраза удалена", "info")

    @Slot(result=str)
    def engineStatusText(self) -> str:
        if self._engine_state == STATE_READY:
            return "готов"
        if self._engine_state == STATE_LOADING:
            return "загрузка…"
        if self._engine_state == STATE_ERROR:
            return self._engine_error or "ошибка"
        return "остановлен"

    # ------------------------------------------------------------------
    # Диагностика и отчёт для поддержки
    # ------------------------------------------------------------------
    @Property(str, notify=reportChanged)
    def reportPath(self) -> str:
        return self._report_path

    @Property(str, notify=reportChanged)
    def reportStatus(self) -> str:
        return self._report_status

    @Slot(result=str)
    def diagnostics(self) -> str:
        """Снимок того, что нужно для разбора: устройства, мост, движок."""
        eng = getattr(self, "_live_engine", None)
        in_name = self._device_name(self._in_list, self._in_device)
        out_name = self._device_name(self._out_list, self._out_device)
        lines = [f"Auraloom {branding.APP_VERSION} · режим {self._mode}",
                 f"движок: {self.engineStatusText()}"]
        if eng is not None:
            for label, attr in (("ASR", "asrModel"), ("TTS", "ttsModel")):
                try:
                    value = getattr(eng, attr, "") or ""
                except Exception:
                    value = ""
                if value:
                    lines.append(f"{label}: {value}")
        lines.append(f"микрофон: {in_name or '—'}")
        lines.append(f"выход: {out_name or '—'}")
        lines.append(f"кабель: {self.cableStatus()} · русский микрофон в кабеле: "
                     f"{'да' if self._cable_mic else 'нет'}")
        bridge = self.bridge
        if bridge is not None:
            try:
                st = bridge.status()
                lines.append(
                    f"мост: {'работает' if st.get('running') else 'стоит'} · "
                    f"{st.get('sr')} Гц · наушники "
                    f"{'ок' if st.get('monitor_ok') else 'нет'} "
                    f"({st.get('monitor_sr') or '—'} Гц)")
                lines.append(
                    "потеряно: "
                    f"{getattr(bridge, 'stream_dropped', 0)} кусков "
                    f"({getattr(bridge, 'stream_dropped_sec', 0.0):.1f} с)")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"мост: статус не прочитан ({exc})")
        else:
            lines.append("мост: выключен")
        if eng is not None:
            try:
                metrics = dict(eng.lastMetrics or {})
            except Exception:
                metrics = {}
            if metrics:
                parts = [f"{k}={v}" for k, v in metrics.items()
                         if k in ("asr_ms", "mt_ms", "tts_first_ms",
                                  "total_ms", "queue", "dropped")]
                if parts:
                    lines.append("последняя реплика: " + ", ".join(parts))
        return "\n".join(lines)

    @Slot()
    def collectReport(self) -> None:
        """Собрать zip с логами и снимком диагностики (в фоне)."""
        if self._report_status == "собираю…":
            return
        self._report_status = "собираю…"
        self.reportChanged.emit()
        snapshot = self.diagnostics()

        def worker() -> None:
            try:
                path = reports.collect(snapshot)
                self._report_path = path
                self._report_status = "готов: " + os.path.basename(path)
            except Exception as exc:  # noqa: BLE001
                self._report_status = f"не собрался: {exc}"
            self.reportChanged.emit()

        threading.Thread(target=worker, daemon=True).start()

    @Slot()
    def openReportsFolder(self) -> None:
        folder = os.path.dirname(self._report_path) if self._report_path \
            else os.path.join(sp.workspace(), "reports")
        try:
            os.makedirs(folder, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        except Exception as exc:  # noqa: BLE001
            self.statusMessage.emit(f"папка не открылась: {exc}", "err")

    @Slot(str)
    def setName(self, name: str) -> None:
        self._name = (name or "").strip() or "Cyril"
        self.userNameChanged.emit()
        self.statusMessage.emit(f"имя: {self._name}", "info")

    @Slot(str)
    def setBankLang(self, code: str) -> None:
        if code in ("es", "en", "ow", "it"):
            self._bank_lang = code
            self.bankLangChanged.emit()
            self.phraseBankChanged.emit()

    @Slot(int)
    def setLiveliness(self, level: int) -> None:
        self._liveliness = max(0, min(3, int(level)))
        self.livelinessChanged.emit()

    @Slot(int)
    def setInDevice(self, idx: int) -> None:
        self._in_device = idx if idx >= 0 else None
        core.remember_mic(self._in_device, self._device_name(self._in_list, idx))
        self.devicesChanged.emit()
        # сразу пробросить в движок: иначе PTT спрашивает «выбери микрофон»
        self._push_devices_to_engine()

    @Slot(int)
    def setOutDevice(self, idx: int) -> None:
        self._out_device = idx if idx >= 0 else None
        self.devicesChanged.emit()
        self._push_devices_to_engine()

    def _push_devices_to_engine(self) -> None:
        eng = getattr(self, "_live_engine", None)
        if eng is None:
            return
        try:
            eng.setMicDevice(self._in_device if self._in_device is not None else -1)
            eng.setOutDevice(self._out_device if self._out_device is not None else -1)
        except Exception:
            pass

    @Slot()
    def refreshDevices(self) -> None:
        self._load_devices()

    @Slot()
    def refreshPhrases(self) -> None:
        self._load_phrases()
        self.phraseBankChanged.emit()

    @Slot()
    def refreshEngine(self) -> None:
        """Перечитать состояние движка (кнопка «Обновить»)."""
        if self.engineInstalled() == "да":
            self.statusMessage.emit(
                f"движок установлен · {self.engineStatusText()}", "ok")
        else:
            self.statusMessage.emit(
                "движок не установлен — tools\\setup_env.ps1", "err")
        self.engineStateChanged.emit()

    # ------------------------------------------------------------------
    # Состояние движка (приходит из LiveEngine.stateChanged)
    # ------------------------------------------------------------------
    @Slot(str)
    def syncEngineState(self, state: str) -> None:
        state = (state or "STOPPED").upper()
        changed = state != self._engine_state
        if changed:
            self._engine_state = state
            if state != STATE_ERROR:
                self._engine_error = ""
            self.engineStateChanged.emit()
        if state == STATE_READY:
            self.statusMessage.emit("модели загружены — движок готов", "ok")
        elif state == STATE_LOADING:
            self.statusMessage.emit("загружаю модели…", "info")
        elif state == STATE_STOPPED and changed:
            self.statusMessage.emit("движок остановлен", "info")

    @Slot(str)
    def syncEngineError(self, message: str) -> None:
        self._engine_error = message or ""
        if self._engine_error:
            self._engine_state = STATE_ERROR
            self.engineStateChanged.emit()
        self.engineErrorChanged.emit()

    @Slot()
    def startEngine(self) -> None:
        """Запустить движок — делегируется LiveEngine (см. live_engine.py)."""
        eng = getattr(self, "_live_engine", None)
        if eng is None:
            self.statusMessage.emit("движок не подключён", "err")
            return
        if self.engineInstalled() != "да":
            self.statusMessage.emit(
                "движок не установлен — tools\\setup_env.ps1", "err")
        else:
            self.statusMessage.emit("запускаю движок…", "info")
        eng.start()

    @Slot()
    def stopEngine(self) -> None:
        eng = getattr(self, "_live_engine", None)
        if eng is None:
            self.statusMessage.emit("движок не подключён", "err")
            return
        self.statusMessage.emit("останавливаю движок…", "info")
        eng.stop()

    @Slot()
    def toggleOverlay(self) -> None:
        self.statusMessage.emit("оверлей переключается в настройках", "info")

    @Slot(result=bool)
    def toggleHotkeys(self) -> bool:
        """Включить/выключить глобальный хоткей push-to-talk."""
        if self._hotkeys_on:
            try:
                self.hotkeys.unregister_prefix("live:")
            except Exception:
                pass
            self._hotkeys_on = False
            self._ptt_active = False
            self.hotkeysChanged.emit(False)
            self.statusMessage.emit("горячие клавиши выключены", "info")
            return False

        try:
            self.hotkeys.set_callback(self._enqueue_hotkey)
            self.hotkeys.start()
        except Exception as exc:
            self.statusMessage.emit(f"хоткеи недоступны: {exc}", "err")
            return False

        combo = self._hotkey or "alt+capslock"
        ok = self.hotkeys.register(combo, "live:ptt:down")
        self._hotkeys_on = bool(ok)
        self._ptt_active = False
        self.hotkeysChanged.emit(self._hotkeys_on)
        if ok:
            self.statusMessage.emit(
                f"{hk.pretty_combo(combo)} — говорить (удерживать)", "ok")
            self._save_settings()
        else:
            self.statusMessage.emit(
                f"{hk.pretty_combo(combo)} занята другой программой", "err")
        return self._hotkeys_on

    def _apply_startup_defaults(self) -> None:
        """Всё готово сразу после старта: кабель, мост, хоткеи, движок."""
        try:
            if not self._out_list or not self._in_list:
                self.refreshDevices()
        except Exception:
            pass
        try:
            # Кабель должен заработать СРАЗУ при старте. _load_devices()
            # ставит первое попавшееся устройство, поэтому при наличии виртуального
            # кабеля принудительно перемаршрутизируем вывод на него.
            has_cable = any(hk.is_virtual_cable(n) for _, n in self._out_list)
            if self._out_device is None or has_cable:
                self._auto_route()
        except Exception:
            pass
        if self._bridge_pref and not self._bridge_on:
            try:
                self._start_bridge()
            except Exception:
                pass
        if self._hotkeys_pref and not self._hotkeys_on:
            try:
                self.toggleHotkeys()
            except Exception:
                pass
        if self._auto_start and self.engineInstalled() == "да":
            try:
                eng = getattr(self, "_live_engine", None)
                if eng is not None and eng.state in ("STOPPED", "ERROR"):
                    self.startEngine()
            except Exception:
                pass

    @Slot(result=bool)
    def toggleBridge(self) -> bool:
        if self._bridge_on:
            self._stop_bridge()
        else:
            self._start_bridge()
        return self._bridge_on

    @Slot()
    def autoRoute(self) -> None:
        ok, msg = self._auto_route()
        self.statusMessage.emit(msg, "ok" if ok else "err")

    @Slot(result=str)
    def engineInstalled(self) -> str:
        return "да" if sp.engine_python() and os.path.exists(sp.engine_python()) else "нет"

    @Slot(result=str)
    def referencePath(self) -> str:
        # Активный профиль — его reference; иначе общий файл.
        return sp.active_reference()

    @Slot(result=str)
    def voiceInfoText(self) -> str:
        """Что реально уйдёт в TTS: профиль, длительность, отпечаток файла.

        Если два профиля собраны из одних и тех же дублей, их reference
        побайтно совпадает — переключение ничего не меняет на слух. Раньше
        это выглядело как «клон не применяется», поэтому показываем
        отпечаток и прямо говорим о совпадении.
        """
        name = self._active_profile or "по умолчанию"
        path = sp.active_reference()
        if not os.path.exists(path):
            return f"{name}: reference.wav не найден"
        try:
            import soundfile as sf
            dur = float(sf.info(path).duration)
        except Exception:
            dur = 0.0
        md5 = ""
        try:
            import hashlib
            h = hashlib.md5()
            with open(path, "rb") as fh:
                for block in iter(lambda: fh.read(1 << 20), b""):
                    h.update(block)
            md5 = h.hexdigest()[:8]
        except Exception:
            md5 = "?"
        text = f"{name} · {dur:.1f} c · {md5}"
        try:
            for other in sp.list_profiles():
                if other == self._active_profile:
                    continue
                other_ref = sp.profile_reference(other)
                if not os.path.exists(other_ref):
                    continue
                oh = hashlib.md5()
                with open(other_ref, "rb") as fh:
                    for block in iter(lambda: fh.read(1 << 20), b""):
                        oh.update(block)
                if oh.hexdigest()[:8] == md5:
                    # Важнее предупреждение, чем отпечаток: он и так одинаков.
                    text = f"{name} · {dur:.1f} c · копия «{other}»"
                    break
        except Exception:
            pass
        return text

    @Slot(result=bool)
    def hasReference(self) -> bool:
        try:
            return os.path.exists(sp.active_reference())
        except Exception:
            return False

    @Slot(result=str)
    def cableStatus(self) -> str:
        if cable_mod.is_installed():
            return "установлен"
        return "не установлен"

    @Slot(result=bool)
    def installCable(self) -> bool:
        ok, msg = cable_mod.download()
        self.statusMessage.emit(msg, "ok" if ok else "err")
        return ok

    # ==================================================================
    # ВНУТРЕННЕЕ
    # ==================================================================
    @staticmethod
    def _looks_like_mapper(name: str) -> bool:
        n = (name or "").lower()
        return ("переназначен" in n or "sound mapper" in n
                or "основной драйвер" in n or "primary sound" in n)

    @staticmethod
    def _is_virtual_input(name: str) -> bool:
        low = (name or "").lower()
        return ("cable" in low or "output" in low or "выход" in low
                or "стерео микшер" in low or "stereo mix" in low)

    def _pick_input(self, inputs) -> int | None:
        """Выбрать входной устройство: запомненный микрофон, иначе настоящий микрофон.

        «Переназначение звуковых устр.» / Sound Mapper и виртуальные кабели
        дают тишину или чужой звук — для индикатора уровня они не годятся.
        """
        if not inputs:
            return None

        def name_of(idx: int) -> str:
            return self._device_name(inputs, idx)

        mic_idx, _ = core.recalled_mic()
        if mic_idx is not None and any(n == mic_idx for n, _ in inputs):
            name = name_of(mic_idx)
            if not self._looks_like_mapper(name) and not self._is_virtual_input(name):
                return mic_idx

        real = [(i, n) for i, n in inputs
                if not self._looks_like_mapper(n) and not self._is_virtual_input(n)]
        for i, n in real:
            low = n.lower()
            if "микро" in low or "micro" in low or "mic" in low:
                return i
        if real:
            return real[0][0]
        return inputs[0][0]

    def _device_name(self, dev_list, idx):
        for num, name in dev_list:
            if num == idx:
                return name
        return ""

    def _load_devices(self) -> None:
        try:
            inputs, outputs = hk.list_devices()
        except Exception:
            inputs, outputs = [], []
        self._in_list = inputs
        self._out_list = outputs
        self._in_device = self._pick_input(inputs)
        if outputs:
            self._out_device = outputs[0][0]
        self.devicesChanged.emit()

    def _load_phrases(self) -> None:
        try:
            lines = core.load_lines()
        except Exception:
            lines = []
        phrases = []
        for ln in lines:
            phrases.append({
                "id": str(ln.get("id", "")),
                "text": str(ln.get("es", "")),
                "ru": str(ln.get("ru", "")),
                "en": str(ln.get("en", "")),
                "ow": str(ln.get("ow", "")),
                "it": str(ln.get("it", "")),
                "cat": str(ln.get("cat", "")),
                "custom": False,
            })
        for ln in self._custom_phrases():
            phrases.append({
                "id": str(ln.get("id", "")),
                "text": str(ln.get("es", "")),
                "ru": str(ln.get("ru", "")),
                "en": "",
                "ow": "",
                "it": "",
                "cat": "custom",
                "custom": True,
            })
        self._phrases = phrases
        self.phraseBankChanged.emit()
        self.phrasesChanged.emit()

    # ------------------------------------------------------------------
    # Файлы настроек и своих фраз (рядом с workspace)
    # ------------------------------------------------------------------
    def _settings_file(self) -> str:
        return os.path.join(sp.workspace(), "ui_settings.json")

    def _load_settings(self) -> dict:
        try:
            with open(self._settings_file(), encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_settings(self) -> None:
        try:
            path = self._settings_file()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({
                    "hints": self._hints_on,
                    "auto_start_engine": self._auto_start,
                    "auto_start_explicit": self._auto_start_explicit,
                    "fullscreen": self._fullscreen,
                    "voice_volume": self._voice_volume,
                    "cable_mic": self._cable_mic,
                    "cable_mic_v": 1,
                    "monitor_device": self._monitor_device,
                    "outgoing_on": self._outgoing_on,
                    "auto_download": self._auto_download,
                    "mode": self._mode,
                    "src_lang": self._src_lang,
                    "defaults_v": 2,
                "hotkey": self._hotkey,
                "hotkeys_on": self._hotkeys_on,
                "bridge_on": self._bridge_on,
                "incoming_on": self._incoming_on,
                    "incoming_volume": self._incoming_volume,
                    "target_lang": self._target_lang,
                    "peer_lang": self._peer_lang,
                    "asr_model": self._asr_model,
                }, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _custom_file(self) -> str:
        return os.path.join(sp.workspace(), "custom_phrases.json")

    def _custom_phrases(self) -> list:
        try:
            with open(self._custom_file(), encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_custom_phrases(self, items: list) -> None:
        try:
            path = self._custom_file()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(items, fh, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.statusMessage.emit(f"не сохранилось: {exc}", "err")

    def _pick_monitor_device(self) -> int | None:
        """Наушники для перевода: явный выбор или устройство по умолчанию.

        Кабель в качестве монитора не годится: тогда перевод снова уходит
        в игру, а не в уши. Поэтому проверяем имя и индекс.
        """
        render = self._out_device
        if self._monitor_device >= 0:
            dev = int(self._monitor_device)
            return None if dev == render else dev
        names = {i: n for i, n in self._out_list}
        try:
            import sounddevice as sd
            default_out = int(sd.default.device[1])
        except Exception:
            default_out = None
        if default_out is not None and default_out != render \
                and not hk.is_virtual_cable(names.get(default_out, "")):
            return default_out
        for idx, name in self._out_list:
            if idx != render and not hk.is_virtual_cable(name):
                return idx
        return None

    def _start_bridge(self) -> None:
        import mic_bridge as mb
        render_idx = self._out_device
        mic_idx = self._in_device
        if render_idx is None:
            self.statusMessage.emit("сначала выбери устройство вывода", "err")
            return
        monitor_dev = self._pick_monitor_device()
        render_name = next((n for i, n in self._out_list if i == render_idx), "")
        # Микрофон пускаем в вывод ТОЛЬКО если это подтверждённый виртуальный
        # кабель. Иначе он ушёл бы в наушники/динамики — «слышу себя сразу».
        passthrough = bool(self._cable_mic) and hk.is_virtual_cable(render_name)
        try:
            self.bridge = mb.MicBridge(
                mic_device=mic_idx, render_device=render_idx,
                mic_gain=1.0 if passthrough else 0.0,
                # Звук в кабель — по ползунку «Перевод в кабеле»,
                # в наушники — по «Перевод в наушниках».
                phrase_gain=max(0.0, min(2.0, self._voice_volume / 100.0)),
                monitor_device=monitor_dev,
                monitor_gain=max(0.0, min(1.5, self._incoming_volume / 100.0)))
            self.bridge.start()
            # Стартовое состояние MicBridge — заглушка включена. Снимаем её
            # только для подтверждённого кабеля; _duck_timer дальше будет
            # приглушать микрофон на время перевода.
            if passthrough:
                self.bridge.set_duck(False)
            self._bridge_on = True
            # Важно: движок должен видеть тот же мост, иначе перевод
            # уходит в локальный OutputStream (кабель) и вообще не
            # попадает в наушники, а заглушка микрофона не работает.
            eng = getattr(self, "_live_engine", None)
            if eng is not None:
                try:
                    eng.bridge = self.bridge
                except Exception:
                    pass
            self.bridgeStateChanged.emit(self._bridge_on)
            st = self.bridge.status()
            if monitor_dev is not None and not st.get("monitor_ok"):
                self.statusMessage.emit(
                    "мост запущен, но наушники не открылись: "
                    + (st.get("monitor_error") or "нет устройства"), "warn")
            else:
                self.statusMessage.emit("мост запущен", "ok")
        except Exception as exc:
            self.bridge = None
            self._bridge_on = False
            self.bridgeStateChanged.emit(False)
            self.statusMessage.emit(f"мост не запустился: {exc}", "err")

    def _stop_bridge(self) -> None:
        eng = getattr(self, "_live_engine", None)
        if eng is not None:
            try:
                eng.bridge = None
            except Exception:
                pass
        if self.bridge is not None:
            try:
                self.bridge.stop()
            except Exception:
                pass
        self.bridge = None
        self._bridge_on = False
        self.bridgeStateChanged.emit(False)
        self.statusMessage.emit("мост остановлен", "info")

    def _auto_route(self) -> tuple[bool, str]:
        """Выбрать кабель/устройства автоматически (как Studio._auto_route)."""
        try:
            outs = self._out_list
            ins = self._in_list
        except Exception:
            return False, "нет списка устройств"
        render = None
        for num, name in outs:
            if hk.is_virtual_cable(name):
                render = num
                break
        if render is None and outs:
            render = outs[0][0]
        mic = self._in_device
        if mic is None and ins:
            mic = ins[0][0]
        self._out_device = render
        self._in_device = mic
        self.devicesChanged.emit()
        return True, "маршрут выбран"

    def _poll_ptt_release(self) -> None:
        """Отпускание push-to-talk: WM_HOTKEY о нём не сообщает."""
        if not self._ptt_active:
            return
        if not self._hotkeys_on:
            self._ptt_active = False
            return
        try:
            still = hk.combo_pressed(self._hotkey)
        except Exception:
            still = False
        if not still:
            self._ptt_active = False
            with self._hk_lock:
                self._hk_queue.append("live:ptt:up")

    def _poll(self) -> None:
        """Опрос очереди хоткеев (замена tk mainloop + after)."""
        with self._hk_lock:
            if not self._hk_queue:
                return
            actions = self._hk_queue[:]
            self._hk_queue.clear()
        for action in actions:
            self._do_hotkey(action)

    def _enqueue_hotkey(self, action: str) -> None:
        """Callback из потока-читателя хоткеев: только в очередь."""
        with self._hk_lock:
            self._hk_queue.append(action)

    def _do_hotkey(self, action: str) -> None:
        eng = getattr(self, "_live_engine", None)
        if eng is None:
            self.statusMessage.emit(f"хоткей: {action} (движок не подключён)",
                                    "warn")
            return
        if action == "live:ptt:down":
            if self._ptt_active:
                return
            self._ptt_active = True
            eng.pressToTalk()
            return
        if action == "live:ptt:up":
            # _poll_ptt_release уже сбросил флаг — отпускание всё равно
            # должно дойти до движка.
            self._ptt_active = False
            eng.releaseToTalk()
            return
        self.statusMessage.emit(f"хоткей: {action}", "info")

    def _tick_status(self) -> None:
        """Периодическая проверка состояния (место для расширения)."""
        pass

    def _refresh_vram(self) -> None:
        """Прочитать VRAM/имя GPU через nvidia-smi (тихо, без консоли)."""
        if os.name != "nt":
            return
        try:
            import subprocess
            flags = 0x08000000  # CREATE_NO_WINDOW
            proc = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total,name",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3,
                creationflags=flags)
            first = (proc.stdout or "").strip().splitlines()
            if not first:
                return
            parts = [p.strip() for p in first[0].split(",")]
            used = int(float(parts[0]))
            total = int(float(parts[1]))
            name = parts[2] if len(parts) > 2 else ""
        except Exception:
            return

        if (used, total, name) == (self._vram_used, self._vram_total, self._gpu_name):
            return
        self._vram_used = used
        self._vram_total = total
        self._gpu_name = name
        self.vramChanged.emit()

    # ==================================================================
    # ЖИЗНЕННЫЙ ЦИКЛ
    # ==================================================================
    def shutdown(self) -> None:
        """Аккуратно остановить всё при закрытии окна."""
        self._poll_timer.stop()
        self._status_timer.stop()
        self._vram_timer.stop()
        try:
            self.hotkeys.unregister_all()
        except Exception:
            pass
        self._stop_bridge()
        try:
            self.recorder.stop()
        except Exception:
            pass