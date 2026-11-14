"""Incoming voice capture source management (Этап A + A1).

Поддерживает три способа захвата звука собеседника:

1. Legacy Input Device — Stereo Mix / CABLE Output через sounddevice (работает).
2. WASAPI Endpoint Loopback — захват loopback-копии с устройства вывода
   через PyAudioWPatch (работает, nécessite pip install PyAudioWPatch).
3. Process Loopback — захват процесса (Discord, RedM/FiveM) — NOT IMPLEMENTED.

Оригинальный звук продолжает играть в тех же наушниках — захват не
отключает устройство вывода.

Защита от аудиопетель: при воспроизведении собственного incoming TTS
захват приостанавливается, чтобы русский перевод не попал обратно в ASR.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from enum import Enum
from typing import Callable, Optional

import numpy as np

try:
    import sounddevice as sd
except Exception:  # pragma: no cover
    sd = None

try:
    import pyaudiowpatch as _pyaudio_module
except ImportError:
    _pyaudio_module = None


class CaptureMode(Enum):
    """Режимы захвата входящего звука."""
    LEGACY_INPUT = "legacy_input"      # Stereo Mix / CABLE Output
    WASAPI_ENDPOINT = "wasapi_endpoint"  # Loopback с устройства вывода
    PROCESS_LOOPBACK = "process_loopback"  # Захват процесса (Discord/RedM)


class CaptureStatus(Enum):
    """Статус захвата."""
    OFF = "off"
    STARTING = "starting"
    ACTIVE = "active"
    STOPPING = "stopping"
    ERROR = "error"
    WAITING_FOR_AUDIO = "waiting_for_audio"
    SIGNAL_DETECTED = "signal_detected"


class LoopbackCapture:
    """Управление захватом входящего звука собеседника.

    Предоставляет единый интерфейс для всех трёх режимов захвата.
    Аудио поступает в callback, который передаёт PCM в Engine
    (через LiveClient.send_peer_pcm) для ASR → MT → TTS.

    Защита от аудиопетель:
      - set_speaking(True) при начале воспроизведения своего TTS
      - set_speaking(False) после окончания
      - Во время Speaking捕获 приостанавливается (PCM не передаётся)
    """

    def __init__(
        self,
        on_pcm: Optional[Callable[[bytes, int], None]] = None,
        on_status: Optional[Callable[[CaptureStatus, str], None]] = None,
        on_level: Optional[Callable[[float], None]] = None,
    ) -> None:
        self._on_pcm = on_pcm
        self._on_status = on_status or (lambda status, msg: None)
        self._on_level = on_level or (lambda level: None)

        self._mode: CaptureMode = CaptureMode.LEGACY_INPUT
        self._device_index: Optional[int] = None
        self._sample_rate: int = 48000
        self._block_size: int = 1024

        self._stream = None
        self._pyaudio: Optional[object] = None  # pyaudiowpatch.PyAudio instance
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._status = CaptureStatus.OFF
        self._status_message = ""

        # RMS level tracking for meter
        self._level = 0.0
        self._rms_history: deque[float] = deque(maxlen=50)
        self._last_pcm_time: Optional[float] = None

        # Diagnostics
        self._total_blocks = 0
        self._error_blocks = 0

        # Feedback loop protection
        self._speaking = False  # True когда свой TTS воспроизводится
        self._speak_lock = threading.Lock()

    # ---------- configuration ----------

    def set_mode(self, mode: CaptureMode) -> None:
        self._mode = mode

    def set_device(self, device_index: Optional[int], sample_rate: int = 48000) -> None:
        self._device_index = device_index
        self._sample_rate = sample_rate

    def set_block_size(self, block_size: int) -> None:
        self._block_size = block_size

    # ---------- feedback loop protection ----------

    def set_speaking(self, speaking: bool) -> None:
        """Установить флаг воспроизведения своего TTS.

        Когда True, входящий PCM не передаётся в ASR (защита от петель).
        """
        with self._speak_lock:
            self._speaking = bool(speaking)

    def is_speaking(self) -> bool:
        with self._speak_lock:
            return self._speaking

    def _should_forward(self) -> bool:
        """Можно ли пересылать текущий PCM в ASR."""
        with self._speak_lock:
            return not self._speaking

    # ---------- status ----------

    def get_status(self) -> CaptureStatus:
        return self._status

    def get_status_message(self) -> str:
        return self._status_message

    def get_level(self) -> float:
        return self._level

    def get_diagnostics(self) -> dict:
        return {
            "mode": self._mode.value,
            "device": self._device_index,
            "status": self._status.value,
            "message": self._status_message,
            "level": self._level,
            "total_blocks": self._total_blocks,
            "error_blocks": self._error_blocks,
            "last_pcm_time": self._last_pcm_time,
            "running": self._running,
            "speaking": self.is_speaking(),
        }

    # ---------- lifecycle ----------

    def start(self) -> bool:
        """Запуск захвата. Возвращает True при успехе."""
        if self._running:
            return True

        self._set_status(CaptureStatus.STARTING, "запуск захвата…")

        try:
            if self._mode == CaptureMode.PROCESS_LOOPBACK:
                return self._start_process_loopback()
            elif self._mode == CaptureMode.WASAPI_ENDPOINT:
                return self._start_wasapi_endpoint()
            else:
                return self._start_legacy_input()
        except Exception as exc:  # noqa: BLE001
            self._set_status(CaptureStatus.ERROR, f"ошибка запуска: {exc}")
            return False

    def stop(self) -> None:
        """Остановка захвата."""
        if not self._running:
            return

        self._set_status(CaptureStatus.STOPPING, "остановка…")
        self._running = False

        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if self._pyaudio is not None:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass
            self._pyaudio = None

        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        self._set_status(CaptureStatus.OFF, "захват остановлен")
        self._level = 0.0

    # ---------- mode implementations ----------

    def _start_legacy_input(self) -> bool:
        """Захват через реальное input устройство (Stereo Mix / CABLE Output).

        Работает через sounddevice.InputStream. Устройство должно быть
        loopback input (CABLE Output, Stereo Mix, What U Hear).
        """
        if sd is None:
            self._set_status(CaptureStatus.ERROR, "sounddevice недоступен")
            return False

        if self._device_index is None:
            self._set_status(CaptureStatus.ERROR, "не выбрано устройство записи")
            return False

        try:
            import sounddevice as sd_mod
            self._stream = sd_mod.InputStream(
                device=self._device_index,
                channels=1,
                samplerate=self._sample_rate,
                dtype="float32",
                blocksize=int(self._sample_rate * 0.05),  # 50мс блоки
                callback=self._legacy_callback,
            )
            self._stream.start()
            self._running = True
            self._set_status(CaptureStatus.ACTIVE, "запись с устройства")
            return True
        except Exception as exc:  # noqa: BLE001
            self._set_status(CaptureStatus.ERROR, f"не открылось устройство: {exc}")
            return False

    def _legacy_callback(self, indata, frames, time_info, status):  # noqa: ARG001
        """Callback для legacy input устройства."""
        if not self._running:
            return
        try:
            block = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        except Exception:
            return

        rms = float(np.sqrt((block.astype(np.float64) ** 2).mean()))
        self._update_level(rms)

        if self._should_forward():
            pcm_bytes = (np.clip(block, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
            self._total_blocks += 1
            self._last_pcm_time = time.time()
            if self._on_pcm:
                self._on_pcm(pcm_bytes, self._sample_rate)

    # ---------- WASAPI Endpoint Loopback (via PyAudioWPatch) ----------

    def _start_wasapi_endpoint(self) -> bool:
        """WASAPI Endpoint Loopback через PyAudioWPatch.

        Открывает loopback-устройство (вход) соответствующее выбранному
        физическому устройству вывода. Оригинальный звук продолжает
        воспроизводиться в тех же наушниках.
        """
        if _pyaudio_module is None:
            self._set_status(
                CaptureStatus.ERROR,
                "PyAudioWPatch не установлен. Установите: pip install PyAudioWPatch"
            )
            return False

        if self._device_index is None:
            self._set_status(CaptureStatus.ERROR, "не выбрано устройство вывода")
            return False

        try:
            self._pyaudio = _pyaudio_module.PyAudio()

            # Находим loopback-аналог выбранного устройства вывода
            loopback_info = self._pyaudio.get_wasapi_loopback_analogue_by_index(
                self._device_index
            )
            if loopback_info is None:
                self._set_status(
                    CaptureStatus.ERROR,
                    f"loopback-а не найден для устройства [{self._device_index}]"
                )
                self._pyaudio.terminate()
                self._pyaudio = None
                return False

            rate = int(loopback_info.get("defaultSampleRate", self._sample_rate))
            channels = loopback_info["maxInputChannels"]
            self._sample_rate = rate

            self._stream = self._pyaudio.open(
                format=_pyaudio_module.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=loopback_info["index"],
                frames_per_buffer=int(rate * 0.05),  # 50мс блоки
                stream_callback=self._wasapi_callback,
            )
            self._stream.start_stream()
            self._running = True
            self._set_status(
                CaptureStatus.ACTIVE,
                f"WASAPI loopback: {loopback_info['name']}"
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._set_status(CaptureStatus.ERROR, f"WASAPI ошибка: {exc}")
            if self._pyaudio is not None:
                try:
                    self._pyaudio.terminate()
                except Exception:
                    pass
                self._pyaudio = None
            self._stream = None
            return False

    def _wasapi_callback(self, in_data, frame_count, time_info, status):
        """Callback для WASAPI loopback потока."""
        if not self._running:
            return (None, _pyaudio_module.paComplete)

        try:
            audio = np.frombuffer(in_data, dtype=np.int16).astype(np.float64) / 32768.0
            rms = float(np.sqrt((audio ** 2).mean()))
        except Exception:
            return (in_data, _pyaudio_module.paContinue)

        self._update_level(rms)

        if self._should_forward():
            self._total_blocks += 1
            self._last_pcm_time = time.time()
            if self._on_pcm:
                self._on_pcm(in_data, self._sample_rate)

        return (in_data, _pyaudio_module.paContinue)

    # ---------- Process Loopback (NOT IMPLEMENTED) ----------

    def _start_process_loopback(self) -> bool:
        """Process Loopback — захват выбранного процесса.

        Требует отдельного нативного C++/Win32 helper через
        WASAPI ActivateAudioInterfaceAsync. На этом этапе недоступен.
        """
        self._set_status(
            CaptureStatus.ERROR,
            "Process Loopback не реализован. Используйте Legacy или WASAPI Endpoint режим."
        )
        return False

    # ---------- internal ----------

    def _set_status(self, status: CaptureStatus, message: str) -> None:
        self._status = status
        self._status_message = message
        if self._on_status:
            self._on_status(status, message)

    def _update_level(self, rms: float) -> None:
        self._rms_history.append(rms)
        if self._rms_history:
            self._level = sum(self._rms_history) / len(self._rms_history)
        if self._on_level:
            self._on_level(self._level)

    def is_running(self) -> bool:
        return self._running


# ---------- device discovery helpers ----------

def list_input_devices() -> list[dict]:
    """Список input устройств для Legacy режима."""
    if sd is None:
        return []
    result = []
    try:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                result.append({
                    "index": i,
                    "name": d["name"],
                    "channels": d["max_input_channels"],
                    "sample_rate": int(d["default_samplerate"]),
                    "hostapi": d.get("hostapi", -1),
                })
    except Exception:
        pass
    return result


def list_output_devices_with_loopback() -> list[dict]:
    """Список физических выходных устройств с их loopback-аналогами.

    Использует PyAudioWPatch для нахождения loopback-устройств.
    Возвращает пустой список если PyAudioWPatch не установлен.
    """
    if _pyaudio_module is None:
        return []

    result = []
    try:
        with _pyaudio_module.PyAudio() as p:
            try:
                wasapi_info = p.get_host_api_info_by_type(_pyaudio_module.paWASAPI)
            except OSError:
                return result

            # Собрать все loopback устройства
            loopbacks = {}
            try:
                for lb in p.get_loopback_device_info_generator():
                    loopbacks[lb["index"]] = lb
            except Exception:
                pass

            try:
                device_count = p.get_device_count()
            except Exception:
                return result

            for i in range(device_count):
                try:
                    info = p.get_device_info_by_index(i)
                except Exception:
                    continue
                if info.get("maxOutputChannels", 0) > 0 and not info.get("isLoopbackDevice", False):
                    lb = None
                    for lb_idx, lb_info in loopbacks.items():
                        if info["name"] in lb_info["name"] and lb_info.get("maxInputChannels", 0) > 0:
                            lb = lb_info
                            break
                    result.append({
                        "index": i,
                        "name": info["name"],
                        "channels": info["maxOutputChannels"],
                        "sample_rate": int(info.get("defaultSampleRate", 48000)),
                        "is_wasapi": info.get("hostApi") == wasapi_info["index"],
                        "loopback_index": lb["index"] if lb else None,
                        "loopback_name": lb["name"] if lb else None,
                        "loopback_channels": lb["maxInputChannels"] if lb else 0,
                    })
    except Exception:
        pass
    return result


def list_output_devices() -> list[dict]:
    """Список output устройств (обёртка для совместимости)."""
    return list_output_devices_with_loopback()


def list_running_processes() -> list[dict]:
    """Список запущенных аудиопроцессов для Process Loopback режима."""
    import subprocess
    result = []
    try:
        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode("cp1251", errors="replace")
        audio_keywords = ("discord", "redm", "fivem", "game", "voice", "chat")
        for line in out.strip().split("\n"):
            parts = line.split(",")
            if len(parts) >= 1:
                name = parts[0].strip('"').lower()
                if any(k in name for k in audio_keywords):
                    result.append({
                        "name": parts[0].strip('"'),
                        "pid": parts[1].strip('"') if len(parts) > 1 else "",
                        "session": parts[2].strip('"') if len(parts) > 2 else "",
                        "mem": parts[4].strip('"') if len(parts) > 4 else "",
                    })
    except Exception:
        pass
    return result
