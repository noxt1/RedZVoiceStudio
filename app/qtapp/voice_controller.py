"""Контроллер страницы «Голоса» для QML.

Содержит всё, что не является аудиодвижком:
  * выбор текущей подсказки, навигация по списку;
  * запись дубля с микрофона (studio_core.Recorder);
  * проигрывание подсказки и сравнение «подсказка + дубль» (ui.audio_play);
  * сборка reference.wav (studio_core.build_reference);
  * список готовых дублей и удаление.

Tkinter не используется. Состояние — обычные атрибуты + Qt-сигналы.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot, Property

import audiodev
import studio_paths as sp
import studio_core as core
import prompt_library as plib


class VoiceController(QObject):
    """Логика страницы «Голоса»."""

    # ---- сигналы ----
    recordingChanged = Signal(bool)
    takeChanged = Signal()
    promptChanged = Signal()
    progressChanged = Signal()
    statusMessage = Signal(str, str)
    referenceChanged = Signal()
    referenceBuildStarted = Signal(int)
    referenceBuildFinished = Signal(bool, str)
    referenceBuildStateChanged = Signal()
    samplesChanged = Signal()
    levelChanged = Signal(float)
    playingChanged = Signal()

    def __init__(self, parent=None, mic_provider=None) -> None:
        super().__init__(parent)
        # откуда брать микрофон: выбор в «Настройках» (см. main.py)
        self._mic_provider = mic_provider
        self._mic_name = ""
        self.recorder = core.Recorder()
        self._records: dict[int, str] = {}
        self._index = 0
        self._filter = ""
        self._recording = False
        self._take_ok = False
        self._take_duration = 0.0
        self._error = ""
        # отмеченные записи для сборки reference (пути wav)
        self._selected: set[str] = set()
        self._building_ref = False
        self._build_note = ""
        self._dur_cache: dict[str, tuple[float, float]] = {}
        # что играет сейчас (путь) — для кнопки «стоп» в интерфейсе
        self._playing_path = ""
        self._silent_ticks = 0
        self._silence_warned = False

        # таймер уровня
        from PySide6.QtCore import QTimer
        self._level_timer = QTimer(self)
        self._level_timer.setInterval(80)
        self._level_timer.timeout.connect(self._tick_level)

        # таймер записи (максимум 20 с на дубль)
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(1000)
        self._rec_timer.timeout.connect(self._tick_rec)

        # следим за общим плеером: кнопка «прослушать» должна стать «стоп»,
        # а когда запись закончилась — обратно
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(200)
        self._play_timer.timeout.connect(self._sync_playback)
        self._play_timer.start()

        self._load_records()
        self._load_phrases()

    # ==================================================================
    # СОСТОЯНИЕ
    # ==================================================================
    @Property(bool, notify=recordingChanged)
    def recording(self) -> bool:
        return self._recording

    @Property(bool, notify=takeChanged)
    def takeOk(self) -> bool:
        return self._take_ok

    @Property(str, notify=playingChanged)
    def playingPath(self) -> str:
        """Путь к файлу, который звучит сейчас ('' — ничего)."""
        return self._playing_path

    @Property(str, notify=statusMessage)
    def takeStatus(self) -> str:
        if self._recording:
            return f"запись… {self._rec_seconds:.1f} c"
        if self._take_ok:
            return "ок"
        if self._error:
            return self._error
        return "нет дубля"

    @Property(int, notify=promptChanged)
    def currentIndex(self) -> int:
        return self._index

    @Property(str, notify=statusMessage)
    def progressText(self) -> str:
        total = len(self._items)
        done = len(self._records)
        return f"{done} / {total}"

    @Property("QVariantList", notify=promptChanged)
    def promptModel(self):
        out = []
        for it in self._items:
            if self._filter and it.get("emotion") != self._filter:
                continue
            out.append(it)
        return out

    @Property("QVariantList", notify=takeChanged)
    def takeModel(self):
        return self._take_model()

    @Property("QVariantList", notify=samplesChanged)
    def sampleModel(self):
        return self._sample_model()

    @Property("QVariantList", notify=samplesChanged)
    def sampleRows(self):
        """Список записей для галочек: каждый wav-файл отдельной строкой."""
        return self._sample_rows()

    @Property(int, notify=samplesChanged)
    def selectedSample(self) -> int:
        return self._selected_sample_row

    # внутреннее
    _selected_sample_row = 0
    _rec_seconds = 0.0
    _items: list[dict] = []

    # ==================================================================
    # СЛОТЫ: подсказки
    # ==================================================================
    @Slot(result=str)
    def currentPromptText(self) -> str:
        if 0 <= self._index < len(self._items):
            return str(self._items[self._index].get("es", ""))
        return "—"

    @Slot(result=str)
    def currentPromptRu(self) -> str:
        if 0 <= self._index < len(self._items):
            return str(self._items[self._index].get("ru", ""))
        return ""

    @Slot()
    def nextPrompt(self) -> None:
        if self._index + 1 < len(self._items):
            self._index += 1
            self._reset_take()
            self.promptChanged.emit()

    @Slot()
    def prevPrompt(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._reset_take()
            self.promptChanged.emit()

    @Slot(int)
    def selectPrompt(self, idx: int) -> None:
        if 0 <= idx < len(self._items):
            self._index = idx
            self._reset_take()
            self.promptChanged.emit()

    @Slot(str)
    def setEmotionFilter(self, emotion: str) -> None:
        self._filter = emotion or ""
        self.promptChanged.emit()

    @Slot()
    def resetTake(self) -> None:
        self._reset_take()
        self.takeChanged.emit()

    @Slot(result=bool)
    def allDone(self) -> bool:
        return len(self._records) >= len(self._items) and len(self._items) > 0

    @Slot(result=bool)
    def takeOkSlot(self) -> bool:
        return self._take_ok

    # ==================================================================
    # СЛОТЫ: запись
    # ==================================================================
    @Slot()
    def toggleRecording(self) -> None:
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    @staticmethod
    def _device_name(index) -> str:
        if index is None:
            return ""
        try:
            import sounddevice as sd
            return str(sd.query_devices(index)["name"])
        except Exception:
            return ""

    @staticmethod
    def _mic_usable(index) -> bool:
        """У устройства есть входные каналы (индекс мог «съехать»)."""
        try:
            import sounddevice as sd
            return int(sd.query_devices(index).get("max_input_channels", 0)) > 0
        except Exception:
            return False

    def _pick_mic(self) -> tuple:
        """Микрофон для записи: выбранный в настройках, затем
        запомненный, затем подобранный автоматически.

        Раньше запись шла с устройства по умолчанию Windows, игнорируя
        выбор в настройках: если по умолчанию стоит виртуальный кабель
        (CABLE Output — его выбирают для Discord), дубль выходил тишиной.
        """
        if callable(self._mic_provider):
            try:
                idx = int(self._mic_provider())
            except Exception:
                idx = -1
            if idx >= 0 and self._mic_usable(idx):
                safe = audiodev.safe_input(idx)
                return safe, self._device_name(safe)
        idx, name = core.recalled_mic()
        if idx is not None and self._mic_usable(idx):
            safe = audiodev.safe_input(idx)
            return safe, self._device_name(safe)
        idx, name = core.pick_input_device()
        if idx is not None:
            safe = audiodev.safe_input(idx)
            return safe, self._device_name(safe) or name
        return idx, name

    def _start_recording(self) -> None:
        if self._recording:
            return
        device, name = self._pick_mic()
        try:
            self.recorder.start(device)
        except Exception as exc:
            if device is None:
                self._error = f"микрофон не открылся: {exc}"
                self.statusMessage.emit(self._error, "err")
                return
            # выбранный микрофон отвалился — пробуем системный
            try:
                self.recorder.start(None)
                device, name = None, ""
            except Exception as exc2:
                self._error = f"микрофон не открылся: {exc2}"
                self.statusMessage.emit(self._error, "err")
                return
        self._mic_name = name or self._device_name(device)
        if device is not None:
            core.remember_mic(device, self._mic_name)
        self._recording = True
        self._rec_seconds = 0.0
        self._take_ok = False
        self._error = ""
        self._silent_ticks = 0
        self._silence_warned = False
        self._level_timer.start()
        self._rec_timer.start()
        self.recordingChanged.emit(True)
        self.takeChanged.emit()
        self.statusMessage.emit(
            f"пишу с «{self._mic_name}»" if self._mic_name
            else "пишу с микрофона Windows по умолчанию", "ok")

    def _stop_recording(self) -> None:
        if not self._recording:
            return
        audio = self.recorder.stop()
        self._recording = False
        self._level_timer.stop()
        self._rec_timer.stop()
        self.recordingChanged.emit(False)

        if audio.size == 0:
            self._error = "пустая запись"
            note = str(getattr(self.recorder, "status_note", "") or "")
            if note:
                self._error += f" (поток: {note})"
            if self._mic_name:
                self._error += f" — микрофон «{self._mic_name}»"
            self.statusMessage.emit(self._error, "err")
            self.takeChanged.emit()
            return

        dur = len(audio) / float(self.recorder.sr or core.SR)
        if dur < 0.4:
            self._error = "слишком коротко"
            self.takeChanged.emit()
            return

        # обрезать тишину по краям — в reference идёт уже обрезанный дубль
        audio = core.trim_by_energy(audio, int(self.recorder.sr or core.SR))
        dur = len(audio) / float(self.recorder.sr or core.SR)
        if audio.size == 0:
            self._error = "пустая запись"
            note = str(getattr(self.recorder, "status_note", "") or "")
            if note:
                self._error += f" (поток: {note})"
            if self._mic_name:
                self._error += f" — микрофон «{self._mic_name}»"
            self.statusMessage.emit(self._error, "err")
            self.takeChanged.emit()
            return

        # та же проверка, что в старой (Tk) версии: тишина и «слишком
        # коротко» дублем не считаются — иначе в reference попадает тишина
        rep = core.quality_report(audio, int(self.recorder.sr or core.SR))
        if not rep["ok"]:
            self._take_ok = False
            self._error = f"переделай: {rep['reason']}"
            if self._mic_name:
                self._error += f" (микрофон «{self._mic_name}»)"
            self.takeChanged.emit()
            self.statusMessage.emit(self._error, "warn")
            return

        # сохранить дубль
        path = self._take_path(self._index)
        try:
            import soundfile as sf
            os.makedirs(os.path.dirname(path), exist_ok=True)
            sf.write(path, audio, int(self.recorder.sr or core.SR))
        except Exception as exc:
            self._take_ok = False
            self._error = f"не сохранилось: {exc}"
            self.takeChanged.emit()
            return

        self._records[self._index] = path
        self._take_ok = True
        self._take_duration = dur
        self._error = ""
        self.takeChanged.emit()
        self.progressChanged.emit()
        self.samplesChanged.emit()
        self.statusMessage.emit(f"записано {rep['dur']:.1f} c — ок", "ok")
        # как в старой версии: удачный дубль — и сразу следующая подсказка
        self.nextPrompt()

    def _tick_level(self) -> None:
        level = float(getattr(self.recorder, "level", 0.0) or 0.0)
        self.levelChanged.emit(level)
        if not self._recording or self._silence_warned:
            return
        if level > 0.004:
            self._silent_ticks = 0
            return
        # ~1.5 c тишины после старта: поток открылся, но сигнала нет.
        self._silent_ticks += 1
        if self._silent_ticks >= 19:
            self._silence_warned = True
            name = self._mic_name or "микрофон Windows по умолчанию"
            self.statusMessage.emit(
                f"«{name}» открылся, но сигнала нет: проверь доступ к "
                f"микрофону (Параметры → Конфиденциальность → Микрофон) "
                f"и что выбран сам микрофон, а не CABLE Output", "warn")

    def _tick_rec(self) -> None:
        self._rec_seconds += 1.0
        if self._rec_seconds >= 20.0:
            self._stop_recording()
        else:
            self.takeChanged.emit()

    def _reset_take(self) -> None:
        self._take_ok = self._index in self._records
        self._take_duration = 0.0
        self._error = ""

    @staticmethod
    def _take_path(index: int) -> str:
        d = sp.output_paths()["samples"]
        return os.path.join(d, f"take_{index + 1:02d}.wav")

    # ==================================================================
    # СЛОТЫ: прослушивание и сравнение
    # ==================================================================
    @Slot()
    def playPrompt(self) -> None:
        self.playPromptAt(self._index)

    @Slot(int)
    def playPromptAt(self, index: int) -> None:
        try:
            from ui import audio_play
        except Exception as exc:
            self.statusMessage.emit(f"нет аудиомодуля: {exc}", "err")
            return
        path = plib.audio_path(index)
        if not path:
            self.statusMessage.emit("нет аудио подсказки", "warn")
            return
        audio_play.play_file(path)

    @Slot(str, float)
    def compare(self, mode: str, delay: float) -> None:
        prompt = plib.audio_path(self._index)
        take = self._records.get(self._index)
        if not prompt:
            self.statusMessage.emit("нет подсказки", "warn")
            return
        if not take:
            self.statusMessage.emit("сначала запиши дубль", "warn")
            return
        try:
            from ui import audio_play
        except Exception as exc:
            self.statusMessage.emit(f"нет аудиомодуля: {exc}", "err")
            return
        audio_play.compare(prompt, take, mode=mode or "delay", delay=delay or 1.2)

    @Slot(str)
    def playSample(self, path: str) -> None:
        """Играть/остановить запись: повторный клик по той же — стоп."""
        if not path:
            return
        try:
            from ui import audio_play
        except Exception:
            return
        audio_play.player_toggle_file(path)
        self._sync_playback()

    @Slot()
    def stopPlayback(self) -> None:
        """Остановить любое прослушивание."""
        try:
            from ui import audio_play
        except Exception:
            return
        audio_play.player_stop()
        self._sync_playback()

    def _sync_playback(self) -> None:
        """Обновить playingPath по состоянию общего плеера."""
        try:
            from ui import audio_play
            path = audio_play.player_current() if audio_play.player_is_playing() else ""
        except Exception:
            path = ""
        if path != self._playing_path:
            self._playing_path = path or ""
            self.playingChanged.emit()

    @Slot(int)
    def playSampleAt(self, row: int) -> None:
        """Прослушать запись по строке списка (а не только reference)."""
        items = self._sample_model()
        if not (0 <= row < len(items)):
            return
        self.playSample(items[row]["path"])

    @Slot(str)
    def toggleSample(self, path: str) -> None:
        """Отметить/снять запись для сборки reference."""
        if not path:
            return
        if path in self._selected:
            self._selected.discard(path)
        else:
            self._selected.add(path)
        self.samplesChanged.emit()

    @Slot()
    def selectAllSamples(self) -> None:
        self._selected = {it["path"] for it in self._sample_model()}
        self.samplesChanged.emit()

    @Slot()
    def clearSelection(self) -> None:
        self._selected.clear()
        self.samplesChanged.emit()

    @Property(int, notify=samplesChanged)
    def selectedCount(self) -> int:
        return len(self._selected)

    @Property(bool, notify=referenceBuildStateChanged)
    def referenceBusy(self) -> bool:
        return self._building_ref

    @Property(float, notify=levelChanged)
    def level(self) -> float:
        """Текущий уровень записи (0..1) для анимации микрофона."""
        return float(getattr(self.recorder, "level", 0.0) or 0.0)

    @Property(str, notify=referenceBuildStateChanged)
    def referenceNote(self) -> str:
        return self._build_note

    @Slot(str, result=bool)
    def saveProfile(self, name: str) -> bool:
        """Сохранить текущий reference как новый голосовой профиль.

        Если profile.wav нет — сначала собираем reference из отмеченных
        записей (или всех), чтобы профиль не остался пустым.
        """
        name = (name or "").strip()
        if not name:
            self.statusMessage.emit("введи имя профиля", "warn")
            return False
        # Не перезаписываем существующий профиль молча: create_profile()
        # возвращает путь и для уже существующего, а copy2 портил его reference.
        target_dir = sp.profile_dir(name)
        if os.path.isdir(target_dir) and os.listdir(target_dir):
            self.statusMessage.emit(f"профиль «{name}» уже существует", "warn")
            return False
        try:
            # create_profile() возвращает (путь_к_reference, сообщение)
            target, _msg = sp.create_profile(name)
            if not target:
                self.statusMessage.emit(_msg or "профиль не создан", "err")
                return False
            os.makedirs(os.path.dirname(target), exist_ok=True)
            # Собираем сразу в reference нового профиля — из отмеченных
            # записей или из всех. Общий reference.wav не трогаем.
            samples = [p for p in sorted(self._selected) if os.path.exists(p)]
            if not samples:
                samples = [row["path"] for row in self._sample_rows()
                           if os.path.exists(row["path"])]
            used = 0
            if samples:
                res = core.build_reference(samples, target)
                if not (isinstance(res, dict) and res.get("ok")):
                    self.statusMessage.emit("не удалось собрать профиль", "err")
                    return False
                used = int(res.get("count") or len(samples))
                self._copy_takes(name, samples)
            else:
                ref = sp.output_paths()["reference"]
                if not os.path.exists(ref):
                    self.statusMessage.emit("нет записей для профиля", "warn")
                    return False
                shutil.copy2(ref, target)
        except Exception as exc:
            self.statusMessage.emit(f"профиль не создался: {exc}", "err")
            return False
        # Одинаковые дубли дают побайтно одинаковый reference — на слух
        # переключение профилей тогда ничего не меняет («клон не применяется»).
        twin = self._same_reference(name, target)
        if twin:
            self.statusMessage.emit(
                f"профиль «{name}» совпадает с «{twin}»: те же дубли", "warn")
        elif used and not self._selected:
            self.statusMessage.emit(
                f"профиль «{name}» создан из всех {used} дублей", "ok")
        else:
            self.statusMessage.emit(f"профиль «{name}» создан", "ok")
        # Движок должен подхватить новый reference сразу, даже если он уже
        # загружен (иначе остаётся старый тембр из workspace/reference.wav).
        self.referenceChanged.emit()
        self.samplesChanged.emit()
        return True

    def _same_reference(self, name: str, target: str) -> str:
        """Имя другого профиля с таким же reference.wav (или "")."""
        try:
            import hashlib

            def digest(path: str) -> str:
                h = hashlib.md5()
                with open(path, "rb") as fh:
                    for block in iter(lambda: fh.read(1 << 20), b""):
                        h.update(block)
                return h.hexdigest()

            mine = digest(target)
            for other in sp.list_profiles():
                if other == name:
                    continue
                path = sp.profile_reference(other)
                if os.path.exists(path) and digest(path) == mine:
                    return other
        except Exception:
            return ""
        return ""

    def _copy_takes(self, name: str, samples: list[str]) -> None:
        """Сохранить исходные дубли внутри профиля (они не «исчезают»)."""
        dest = os.path.join(sp.profile_dir(name), "takes")
        os.makedirs(dest, exist_ok=True)
        rows = []
        for src in samples:
            try:
                base = os.path.basename(src)
                out = os.path.join(dest, base)
                if os.path.abspath(src) != os.path.abspath(out):
                    shutil.copy2(src, out)
                rows.append({"file": base, "source": src,
                             "bytes": os.path.getsize(out)})
            except Exception:
                continue
        try:
            with open(os.path.join(dest, "takes.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"profile": name, "takes": rows}, fh,
                          ensure_ascii=False, indent=2)
        except Exception:
            pass

    @Slot(str)
    def deleteSample(self, path: str) -> None:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as exc:
            self.statusMessage.emit(f"не удалилось: {exc}", "err")
            return
        self._selected.discard(path)
        self._load_records()
        self.takeChanged.emit()
        self.samplesChanged.emit()
        self.progressChanged.emit()

    @Slot(str)
    def selectSample(self, path: str) -> None:
        items = self._sample_model()
        for i, it in enumerate(items):
            if it.get("path") == path:
                self._selected_sample_row = i
                break
        self.samplesChanged.emit()

    # ==================================================================
    # СЛОТЫ: сборка reference
    # ==================================================================
    @Slot()
    def buildReference(self) -> None:
        """Собрать reference из отмеченных записей (или из всех).

        Раньше сборка шла в GUI-потоке: интерфейс дёргался, а результат
        было не видно. Теперь работа уходит в фоновый поток, а в UI
        приходят signals с прогрессом и итогом.
        """
        if self._building_ref:
            self.statusMessage.emit("уже собираю образец", "warn")
            return
        samples = [p for p in sorted(self._selected) if os.path.exists(p)]
        if not samples:
            samples = [row["path"] for row in self._sample_rows()
                       if os.path.exists(row["path"])]
        if not samples:
            self.statusMessage.emit("нет записей — сначала запиши дубли", "warn")
            return
        self._building_ref = True
        self._build_note = f"собираю образец из {len(samples)} дублей…"
        self.referenceBuildStateChanged.emit()
        self.referenceBuildStarted.emit(len(samples))
        self.statusMessage.emit(self._build_note, "info")
        threading.Thread(target=self._build_reference_job,
                         args=(samples,), daemon=True).start()

    def _build_reference_job(self, samples: list[str]) -> None:
        """Фоновая сборка reference активного профиля."""
        import threading  # noqa: F401  (явная зависимость потока)
        out = sp.active_reference()
        ok = False
        note = ""
        try:
            res = core.build_reference(samples, out)
            ok = bool(isinstance(res, dict) and res.get("ok"))
            if ok:
                secs = float(res.get("seconds", 0) or 0)
                note = f"reference готов ({secs:.1f} c)"
            else:
                note = "не удалось собрать reference"
        except Exception as exc:  # noqa: BLE001
            note = f"ошибка сборки: {exc}"
        self._building_ref = False
        self._build_note = note
        if ok:
            self.referenceChanged.emit()
        self.referenceBuildFinished.emit(ok, note)
        self.referenceBuildStateChanged.emit()
        self.statusMessage.emit(note, "ok" if ok else "err")

    # ==================================================================
    # МОДЕЛИ
    # ==================================================================
    def _take_model(self) -> list[dict]:
        out = []
        for it in self._items:
            idx = int(it.get("index", 0))
            path = self._records.get(idx, "")
            dur = 0.0
            if path and os.path.exists(path):
                try:
                    import soundfile as sf
                    dur = float(sf.info(path).duration)
                except Exception:
                    pass
            out.append({
                "index": idx,
                "text": it.get("es", ""),
                "emotion": it.get("emotion", ""),
                "emotion_label": it.get("emotion_label", ""),
                "duration": dur,
                "path": path,
                "selected": bool(path) and path in self._selected,
                "ok": bool(path),
            })
        return out

    def _duration(self, path: str) -> float:
        """Длительность WAV с кэшем: sf.info на 25 файлах при каждом
        нажатии галочки тормозил GUI."""
        try:
            mt = os.path.getmtime(path)
        except Exception:
            mt = 0.0
        hit = self._dur_cache.get(path)
        if hit is not None and abs(hit[1] - mt) < 0.001:
            return hit[0]
        dur = 0.0
        try:
            import soundfile as sf
            dur = float(sf.info(path).duration)
        except Exception:
            pass
        self._dur_cache[path] = (dur, mt)
        return dur

    def _sample_rows(self) -> list[dict]:
        """Все записи из voice_samples отдельными строками.

        Раньше список на странице «Голос» строился только по take_NN.wav,
        поэтому более старые записи (p01_take_*.wav) не показывались и
        выбрать их галочкой было нельзя. Теперь в списке каждый файл,
        а подпись — текст подсказки, если имя на неё указывает.
        """
        out = []
        d = sp.output_paths()["samples"]
        if not os.path.isdir(d):
            return out
        import re
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith(".wav"):
                continue
            p = os.path.join(d, fn)
            m = (re.match(r"^p(\d{1,2})_", fn.lower())
                 or re.match(r"^take_(\d{1,2})", fn.lower()))
            idx = int(m.group(1)) - 1 if m else -1
            if 0 <= idx < len(self._items):
                text = str(self._items[idx].get("es") or
                           self._items[idx].get("ru") or fn)
            else:
                text = fn
            dur = self._duration(p)
            out.append({
                "index": idx,
                "name": fn,
                "text": text,
                "path": p,
                "duration": dur,
                "selected": p in self._selected,
                "ok": True,
            })
        return out

    def _sample_model(self) -> list[dict]:
        out = []
        d = sp.output_paths()["samples"]
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if not fn.lower().endswith(".wav"):
                    continue
                p = os.path.join(d, fn)
                dur = self._duration(p)
                out.append({
                    "path": p,
                    "name": fn,
                    "meta": f"{dur:.1f} c" if dur else "—",
                    "duration": dur,
                    "selected": p in self._selected,
                })
        return out

    # ==================================================================
    # ЗАГРУЗКА
    # ==================================================================
    def _load_records(self) -> None:
        d = sp.output_paths()["samples"]
        self._records = {}
        if not os.path.isdir(d):
            return
        for fn in os.listdir(d):
            low = fn.lower()
            if not low.startswith("take_") or not low.endswith(".wav"):
                continue
            try:
                num = int(low[5:7])
            except Exception:
                continue
            self._records[num - 1] = os.path.join(d, fn)

    def _load_phrases(self) -> None:
        try:
            self._items = [dict(x) for x in plib.manifest()]
        except Exception:
            self._items = []
        self._reset_take()