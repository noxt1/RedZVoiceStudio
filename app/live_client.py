"""Клиент живого перевода: общается с движком (tools/live_translate.py).

Схема работы:
  1. GUI запускает движок отдельным процессом (в нём torch и модели).
  2. Модели грузятся один раз и живут в памяти (~15 с при старте).
  3. При нажатии кнопки «Говорить»:
       запись с микрофона -> PCM -> движок -> распознавание, перевод, синтез
     -> чанки аудио приходят обратно и играются в выбранное устройство.
  4. Пока идёт синтез, можно говорить снова (очередь).

Модели в EXE не влезают (4 ГБ), поэтому GUI только заказывает, а движок считает.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import subprocess
import sys
import threading
import time

import numpy as np

SR_ASR = 16000
SR_TTS = 24000

# Версия протокола GUI <-> движок. Должна совпадать с PROTOCOL_VERSION в
# tools/live_translate.py: иначе рядом со сборкой работает старый движок
# (после обновления EXE он мог остаться запущенным), и правки не доезжают.
PROTOCOL_VERSION = 3


class LiveTranslator:
    """Управление процессом движка и воспроизведение ответа."""

    def __init__(self, engine_python: str | None, script: str,
                 reference: str, on_event=None, on_text=None) -> None:
        self.engine_python = engine_python
        self.script = script
        self.reference = reference
        self.on_event = on_event or (lambda kind, data: None)
        self.on_text = on_text or (lambda ru, es, tone="": None)

        self.proc: subprocess.Popen | None = None
        self.ready = False
        self.loading = False
        self.busy = False
        self.seq = 0
        self.error = ""
        self._lines: queue.Queue[str] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._stopping = False      # stop() закрыл поток штатно
        # Поколение процесса: строка от старого процесса (его EOF после
        # перезапуска) не должна опрокидывать НОВЫЙ движок в ERROR.
        self._proc_gen = 0
        self.last_send_error = ""   # последняя ошибка записи в stdin движка
        # RLock, а не Lock: _send() берёт его изнутри translate_pcm()
        self._lock = threading.RLock()

    # ---------- запуск ----------
    def start(self) -> bool:
        """Запустить движок и загрузить модели."""
        with self._lock:
            self._stopping = False
            if self.proc is not None:
                # процесс мог умереть (OOM, креш движка) — тогда перезапускаем
                if self.proc.poll() is None:
                    return True
                self._diag_log("[gui] предыдущий движок уже завершился — перезапуск")
                self.proc = None
                self.ready = False
                self.loading = False
            self._diag_log(f"[gui] start(): python={self.engine_python} "
                           f"script={self.script}")
            if not self.engine_python or not os.path.exists(self.engine_python):
                self.error = "нет движка (engine не установлен)"
                self._diag_log(f"[gui] ОШИБКА: {self.error}")
                return False
            if not os.path.exists(self.script):
                self.error = f"нет скрипта движка: {self.script}"
                self._diag_log(f"[gui] ОШИБКА: {self.error}")
                return False

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            env["COQUI_TOS_AGREED"] = "1"
            env["PYTHONUNBUFFERED"] = "1"
            # PyInstaller (onefile) прокидывает в окружение потомка свои
            # переменные (_MEIPASS, _PYI_*) и подставляет _MEIPASS в PATH.
            # Дочерний python из-за этого грузит не свои DLL и падает —
            # вычищаем всё это.
            for key in list(env):
                if key.startswith("_PYI") or key == "_MEIPASS":
                    env.pop(key, None)
            path = env.get("PATH", "")
            if "_MEI" in path:
                keep = [p for p in path.split(os.pathsep) if "_MEI" not in p]
                env["PATH"] = os.pathsep.join(keep)
            self._diag_log(f"[gui] окружение: PATH={env.get('PATH', '')[:300]}")
            # Движок — консольный python: без флага Windows показывает окно
            # консоли прямо поверх игры во время загрузки моделей.
            no_window = 0x08000000 if os.name == "nt" else 0
            try:
                self.proc = subprocess.Popen(
                    [self.engine_python, self.script,
                     f"--reference={self.reference}"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding="utf-8",
                    errors="replace", bufsize=1, env=env,
                    creationflags=no_window,
                    cwd=os.path.dirname(self.script))
            except Exception as exc:  # noqa: BLE001
                self.error = f"не удалось запустить движок: {exc}"
                self.proc = None
                return False

            # Движок работает В ФОНЕ игры: понижаем приоритет, чтобы
            # Windows отдавала ресурсы игре, а перевод ждал своей очереди.
            # Иначе при 100% GPU игра начинает подтормаживать.
            try:
                import ctypes
                BELOW_NORMAL = 0x00004000
                handle = ctypes.windll.kernel32.OpenProcess(
                    0x1F0FFF, False, self.proc.pid)
                if handle:
                    ctypes.windll.kernel32.SetPriorityClass(handle, BELOW_NORMAL)
                    ctypes.windll.kernel32.CloseHandle(handle)
            except Exception:
                pass
            self._proc_gen += 1
            gen = self._proc_gen
            self._reader = threading.Thread(target=self._read_loop,
                                            args=(gen,), daemon=True)
            self._reader.start()
            threading.Thread(target=self._read_err, args=(gen,),
                             daemon=True).start()
            self._diag_log(f"[gui] запуск: {self.engine_python} {self.script}")
            self._send({"cmd": "load"})
            self.loading = True
            return True

    def _diag_log(self, text: str) -> None:
        """Записать в лог отладочную строку (что запускаем и что пришло)."""
        try:
            logs = os.path.join(os.path.dirname(self.reference), "logs")
            os.makedirs(logs, exist_ok=True)
            with open(os.path.join(logs, "live_engine.log"), "a",
                      encoding="utf-8") as fh:
                fh.write(text + "\n")
                fh.flush()
        except Exception:
            pass

    def _read_loop(self, gen: int = 0) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            text = line.rstrip()
            # чанки аудио большие — в лог не пишем, но очередь получают целиком
            if not text.startswith('{"event":"chunk"'):
                self._diag_log(f"[engine>] {text[:300]}")
            self._lines.put((gen, text))
        self._diag_log("[engine] поток вывода закрыт")
        self._lines.put((gen, ""))  # признак конца потока

    def _read_err(self, gen: int = 0) -> None:
        assert self.proc and self.proc.stderr
        # stderr движка пишем в ОТДЕЛЬНЫЙ файл: сам движок уже ведёт
        # свой лог (live_engine.log), иначе строки дублируются
        log_path = None
        try:
            logs = os.path.join(os.path.dirname(self.reference), "logs")
            os.makedirs(logs, exist_ok=True)
            log_path = os.path.join(logs, "live_engine_stderr.log")
        except Exception:
            log_path = None
        fh = open(log_path, "a", encoding="utf-8") if log_path else None
        try:
            for line in self.proc.stderr:
                text = line.rstrip()
                if fh:
                    fh.write(text + "\n")
                    fh.flush()
                self.on_event("log", text)
        except Exception:
            pass
        finally:
            if fh:
                try:
                    fh.close()
                except Exception:
                    pass

    def _send(self, msg: dict) -> None:
        if not self.proc or not self.proc.stdin:
            return
        try:
            with self._lock:
                self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
                self.proc.stdin.flush()
        except Exception as exc:  # noqa: BLE001
            # Молча глотать нельзя: раньше ошибка записи (большой кадр
            # собеседника) терялась и фраза просто исчезала.
            self.last_send_error = str(exc)
            self._diag_log(f"[gui] ошибка отправки {msg.get('cmd')}: {exc}")

    # ---------- приём ответов ----------
    def poll(self) -> None:
        """Разобрать пришедшие строки. Вызывается из GUI-потока."""
        while True:
            try:
                gen, line = self._lines.get_nowait()
            except queue.Empty:
                return
            if gen != self._proc_gen:
                # остаток вывода старого процесса — не наш, игнорируем
                continue
            if not line:
                if self._stopping:
                    # поток уже закрыт штатно (stop()) — не повторяем ошибку
                    self.proc = None
                    continue
                self.error = "движок остановился"
                self.ready = False
                self.loading = False
                self.proc = None      # иначе перезапуск считает процесс живым
                self.on_event("state", {"error": self.error})
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            kind = msg.get("event")
            if kind == "ready":
                self.ready = True
                self.loading = False
                self.error = ""
                self.on_event("state", {"ready": True})
            elif kind == "text":
                self.on_text(msg.get("ru", ""), msg.get("es", ""),
                             msg.get("tone", ""))
            elif kind == "chunk":
                self.on_event("chunk", msg)
            elif kind == "done":
                self.busy = False
                self.on_event("done", msg)
            elif kind == "boot":
                # версия протокола движка: GUI предупредит о расхождении
                self.on_event("boot", msg)
            elif kind in ("phrase_timing", "peer_skip"):
                # тайминги фразы и причины «фраза была — перевода нет»
                self.on_event(kind, msg)
            elif kind == "peer_text":
                # чужой игрок: оригинал + перевод на русский
                self.on_event("peer_text", msg)
            elif kind == "incoming_chunk":
                # чанк входящего перевода (для наушников)
                self.on_event("incoming_chunk", msg)
            elif kind == "incoming_done":
                # завершение синтеза входящего перевода
                self.on_event("incoming_done", msg)
            elif kind == "lang":
                self.on_event("lang", msg)
            elif kind == "package":
                # статус языкового пакета (скачивание/установка/ошибка)
                self.on_event("package", msg)
            elif kind == "auto_download":
                self.on_event("auto_download", msg)
            elif kind in ("catalog", "download", "verify", "model_removed",
                          "model_selected", "packs", "pack", "pack_verify",
                          "peer_lang", "peer_lang_detected", "unloaded",
                          "mode", "peer_partial", "metrics", "stats",
                          "reference"):
                # управление моделями и языковые пакеты
                self.on_event(kind, msg)
            elif kind == "src_lang":
                # подтверждение языка пользователя
                self.on_event("src_lang", msg)
            elif kind == "models":
                # список установленных моделей (ASR/TTS/MT)
                self.on_event("models", msg)
            elif kind == "asr":
                # подтверждение смены модели распознавания
                self.on_event("asr", msg)
            elif kind == "error":
                self.error = msg.get("message", "")
                self.busy = False
                self.loading = False
                self.on_event("state", {"error": self.error})

    # ---------- язык перевода ----------
    def set_lang(self, code: str) -> bool:
        """Переключить язык перевода (es / en / ow / it)."""
        if not self.ready:
            return False
        try:
            self._send({"cmd": "lang", "code": str(code)})
            return True
        except Exception:
            return False

    def set_reference(self, path: str) -> bool:
        """Сменить reference.wav активного профиля на лету."""
        if not self.ready or not path:
            return False
        self.reference = path
        self._send({"cmd": "reference", "path": str(path)})
        return True

    def set_src_lang(self, code: str) -> bool:
        """Язык пользователя (источник исходящего перевода)."""
        if not self.ready:
            return False
        self._send({"cmd": "src_lang", "code": str(code)})
        return True

    def send(self, msg: dict) -> bool:
        """Отправить произвольную команду движку (каталог/загрузки/пакеты)."""
        if not self.proc:
            return False
        self._send(msg)
        return True

    def set_auto_download(self, on: bool) -> bool:
        """Разрешить движку скачивать недостающие пакеты перевода."""
        if not self.ready:
            return False
        self._send({"cmd": "set_auto_download", "on": bool(on)})
        return True

    def request_models(self) -> bool:
        """Запросить у движка список реально установленных моделей."""
        if not self.ready:
            return False
        self._send({"cmd": "models"})
        return True

    def set_asr_model(self, name: str) -> bool:
        """Переключить модель распознавания (должна быть установлена)."""
        if not self.ready or not name:
            return False
        self._send({"cmd": "set_asr", "name": str(name)})
        return True

    def set_peer_lang(self, code: str) -> bool:
        """Язык чужой речи: auto или конкретный (es/en/it/ru)."""
        if not self.ready:
            return False
        try:
            self._send({"cmd": "peer_lang", "code": str(code)})
            return True
        except Exception:
            return False

    def set_mode(self, code: str) -> bool:
        """Режим работы движка: fast / balanced / quality / manual."""
        if not self.ready:
            return False
        self._send({"cmd": "mode", "code": str(code)})
        return True

    def send_peer_pcm(self, pcm, sr: int = 16000,
                      partial: bool = False, last: bool = True,
                      phrase: int | None = None) -> bool:
        """Отдать фрагмент звука игры на разбор речи игроков.

        Принимает И bytes int16 (так отдаёт wasapi_loopback), И float32-массив.
        Раньше ожидался только массив: байты падали в np.clip, ошибка
        глушилась, и звук собеседника вообще не доходил до движка.

        last=False — это кусок длинной фразы (транспорт, не реплика):
        движок скопит куски и распознает/переведёт фразу целиком.
        phrase — номер реплики: движок не склеит куски двух разных фраз,
        если у предыдущей потерялся последний кусок.
        """
        if not self.ready or pcm is None:
            return False
        try:
            if isinstance(pcm, (bytes, bytearray, memoryview)):
                data = np.frombuffer(pcm, dtype=np.int16)
            else:
                arr = np.asarray(pcm, dtype=np.float32)
                data = (np.clip(arr, -1.0, 1.0) * 32767).astype(np.int16)
            if data.size == 0:
                return False
            msg = {"cmd": "peer", "sr": int(sr),
                   "pcm": base64.b64encode(data.tobytes()).decode("ascii")}
            if partial:
                msg["partial"] = True
            if not last:
                msg["last"] = False
            if phrase is not None:
                msg["phrase"] = int(phrase)
            self._send(msg)
            return True
        except Exception as exc:  # noqa: BLE001
            self.last_send_error = str(exc)
            self._diag_log(f"[gui] peer не отправлен: {exc}")
            return False

    def incoming_speak(self, text: str, seq: int = 0,
                       voice_profile: str | None = None) -> bool:
        """Запросить синтез русского текста для входящего перевода.

        Движок синтезирует текст через XTTS (язык 'ru') и отдаёт чанки
        через incoming_chunk события. GUI направляет их в наушники.
        """
        if not self.ready:
            return False
        try:
            self._send({"cmd": "incoming_speak", "text": str(text),
                        "seq": int(seq),
                        "voice_profile": str(voice_profile)
                        if voice_profile is not None else None})
            return True
        except Exception:
            return False

    # ---------- перевод ----------
    def set_liveliness(self, level: int) -> bool:
        """Задать уровень «живости» синтеза (0 — ровно, 3 — максимум).

        Движок сдвигает параметры XTTS: чем выше, тем свободнее сэмплирование
        и разнообразнее интонация.
        """
        if not self.ready:
            return False
        try:
            self._send({"cmd": "liveliness", "level": int(level)})
            return True
        except Exception:
            return False

    def translate_pcm(self, pcm: np.ndarray, sr: int = 44100,
                      floor: float = 0.0) -> bool:
        """Отдать записанное аудио на перевод.

        Аудио шлём «как есть» (int16, с частотой sr) — ресемплинг до 16 кГц
        делает движок: в EXE нет scipy, а в движке он есть.

        floor — уровень шума комнаты: движок отбросит фрагменты тише него
        (иначе Whisper на шуме галлюцинирует и это озвучивается).
        """
        if not self.ready:
            return False
        with self._lock:
            self.seq += 1
            seq = self.seq
            data = (np.clip(pcm, -1.0, 1.0) * 32767).astype(np.int16)
            self.busy = True
            self._send({"cmd": "translate", "seq": seq, "sr": int(sr),
                        "floor": round(float(floor), 6),
                        "pcm": base64.b64encode(data.tobytes()).decode("ascii")})
        return True

    def stop(self) -> None:
        """Остановить движок и выбросить всё, что не успело прозвучать.

        Без очистки очереди уже синтезированные чанки продолжали играть
        после остановки: пользователь останавливал модель, а перевод
        ещё несколько секунд «договаривал» старые фразы.
        """
        proc = self.proc
        self._stopping = True
        self.ready = False
        self.loading = False
        self.busy = False
        # Выбрасываем накопленные строки: чанки, тексты, события
        try:
            while True:
                self._lines.get_nowait()
        except queue.Empty:
            pass
        except Exception:
            pass
        self._lines = queue.Queue()
        if proc:
            # Сначала unload/quit (модели освобождают RAM), потом завершаем
            # процесс.
            for cmd in ({"cmd": "unload"}, {"cmd": "quit"}):
                try:
                    if proc.stdin:
                        proc.stdin.write(json.dumps(cmd, ensure_ascii=False) + "\n")
                        proc.stdin.flush()
                except Exception:
                    pass
            try:
                proc.terminate()
                proc.wait(timeout=8)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            self.proc = None


def pcm_to_float16(pcm_bytes: bytes) -> np.ndarray:
    """bytes int16 -> float32 mono."""
    return np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0


def float16_to_pcm_bytes(audio: np.ndarray) -> bytes:
    """float32 -> bytes int16."""
    return (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def resample_to_16k(audio: np.ndarray, sr: int) -> np.ndarray:
    """Перевести в 16 кГц для Whisper.

    В GUI scipy нет (исключён из сборки EXE), поэтому используем
    линейную интерполяцию numpy. Точность здесь не критична: дальше
    движок всё равно приводит аудио к 16 кГц через scipy.
    """
    if sr == SR_ASR or audio.size == 0:
        return audio
    n_out = int(round(len(audio) * SR_ASR / sr))
    if n_out < 1:
        return audio
    x_in = np.arange(len(audio), dtype=np.float64)
    x_out = np.linspace(0, len(audio) - 1, n_out)
    return np.interp(x_out, x_in, audio).astype(np.float32)
