"""IncomingTTSProvider - управление синтезом и воспроизведением входящего перевода.

Интерфейс независим от конкретной модели TTS (XTTS, Qwen3-TTS и т.п.).
Аудио идёт только в наушники (отдельный incoming bus), НЕ в виртуальный микрофон.

Архитектура:
    peer_pcm -> ASR -> translate_to_ru() -> [Engine] peer_text IPC -> GUI
    GUI -> IncomingTTSProvider.speak() -> LiveClient.incoming_speak() IPC -> [Engine]
    [Engine] speak_incoming() -> XTTS (RU) -> incoming_chunk IPC -> GUI
    GUI -> IncomingTTSProvider.on_incoming_chunk() -> MicBridge.push_incoming_pcm()
                                                              -> наушники только
"""

from __future__ import annotations

import base64
import threading
import time
from collections import deque
from typing import Callable

import numpy as np

import live_client as lc


class IncomingTTSProvider:
    """Провайдер синтеза речи для входящего перевода (ES/IT/EN → RU).

    Управляет очередью текстов на синтез, общается с движком через IPC,
    отправляет готовые чанки в MicBridge (только наушники, отдельный bus).
    """

    def __init__(self, live_client, mic_bridge,
                 on_status: Callable[[str], None] | None = None) -> None:
        self._live_client = live_client
        self._mic_bridge = mic_bridge
        self._on_status = on_status or (lambda msg: None)

        # Очередь на синтез: (request_id, text, lang, voice_profile, ts)
        self._queue: deque = deque()
        self._max_queue = 8
        self._lock = threading.Lock()
        self._next_id = 0
        self._active_id: int | None = None
        self._cancelled: set[int] = set()

        # Состояние
        self._enabled = False
        self._voice_profile: str | None = None
        self._volume = 1.0  # 0.0 - 1.0

        # Статистика задержки
        self._last_synthesis_ms = 0

    # ---------- конфигурация ----------

    def set_enabled(self, enabled: bool) -> None:
        """Включить/выключить входящий TTS. При выключении — сброс очереди."""
        self._enabled = bool(enabled)
        if not enabled:
            self.stop()
            self._on_status("входящий перевод выключен")

    def set_bridge(self, mic_bridge) -> None:
        """Обновить ссылку на MicBridge (может быть создан позже)."""
        self._mic_bridge = mic_bridge

    def set_capture(self, capture) -> None:
        """Обновить ссылку на LoopbackCapture для защиты от аудиопетель.

        Когда свой TTS воспроизводится, capture не пересылает PCM в ASR,
        чтобы русский перевод не распознавался и не переводился снова.
        """
        self._capture = capture

    def set_voice_profile(self, profile: str | None) -> None:
        self._voice_profile = profile

    def set_volume(self, volume: float) -> None:
        """Установить громкость входящего перевода (0.0 - 1.0).

        Применяется только к входящему TTS (в on_incoming_chunk),
        не затрагивает исходящий перевод в наушники.
        """
        self._volume = max(0.0, min(1.0, float(volume)))

    # ---------- публичный API ----------

    def speak(self, text: str, lang: str = "ru",
              voice_profile: str | None = None) -> bool:
        """Поставить текст на синтез и воспроизведение в наушники.

        Вызывается из GUI-потока после получения peer_text от движка.
        Текст отправляется на синтез в движок через LiveClient.incoming_speak().
        """
        if not self._enabled or not text or not text.strip():
            return False
        if self._live_client is None or not self._live_client.ready:
            self._on_status("движок не готов — текст не озвучен")
            return False

        with self._lock:
            if len(self._queue) >= self._max_queue:
                # Очередь переполнена — отбрасываем старейшее (устаревшее)
                self._queue.popleft()
                self._on_status("очередь переполнена — фраза пропущена")
            req_id = self._next_id
            self._next_id += 1
            self._queue.append((req_id, text.strip(), lang,
                                voice_profile or self._voice_profile,
                                time.time()))

        self._send_next()
        return True

    def stop(self) -> None:
        """Остановить синтез и очистить очередь ожидающих запросов.

        Текущий синтез в движке будет доведён до конца, но его чанки
        будут проигнорированы (помечены как отменённые).
        """
        with self._lock:
            self._queue.clear()
            if self._active_id is not None:
                self._cancelled.add(self._active_id)
            self._active_id = None

    def is_enabled(self) -> bool:
        return self._enabled

    def is_busy(self) -> bool:
        with self._lock:
            return self._active_id is not None or bool(self._queue)

    # ---------- обработка событий от движка (вызывается из GUI-потока) ----------

    def on_incoming_chunk(self, data: dict) -> None:
        """Движок прислал чанк входящего аудио (base64 int16, 24 кГц)."""
        seq = data.get("seq", 0)
        with self._lock:
            if self._active_id != seq:
                return  # чанк от неактивного запроса — игнорируем
            if seq in self._cancelled:
                return  # запрос был отменён — не играем

        try:
            pcm = lc.pcm_to_float16(base64.b64decode(data["pcm"]))
        except Exception:
            return

        # Применяем громкость входящего перевода
        if self._volume != 1.0:
            pcm = pcm * self._volume

        self._push_to_headphones(pcm)

    def on_incoming_done(self, data: dict) -> None:
        """Движок закончил синтез фразы."""
        seq = data.get("seq", 0)
        with self._lock:
            if self._active_id == seq:
                self._active_id = None
                self._cancelled.discard(seq)
        # Защита от аудиопетель: больше не Speaking
        if self._capture is not None:
            self._capture.set_speaking(False)
        self._send_next()

    # ---------- внутреннее ----------

    def _send_next(self) -> None:
        """Отправить следующий текст на синтез движку."""
        with self._lock:
            if not self._enabled:
                self._active_id = None
                return
            if not self._queue or self._active_id is not None:
                return
            req_id, text, lang, voice_profile, ts = self._queue.popleft()
            self._active_id = req_id
            self._cancelled.discard(req_id)

        # Проверяем актуальность (не устарел ли пока ждал в очереди)
        if not self._enabled:
            with self._lock:
                self._active_id = None
            return

        try:
            t0 = time.time()
            ok = self._live_client.incoming_speak(text, req_id, voice_profile)
            if not ok:
                self._on_status("ошибка отправки на синтез")
                with self._lock:
                    self._active_id = None
                self._send_next()
            else:
                self._last_synthesis_ms = int((time.time() - t0) * 1000)
                # Защита от аудиопетель: пока свой TTS играет,
                # capture не пересылает PCM в ASR
                if self._capture is not None:
                    self._capture.set_speaking(True)
        except Exception as exc:  # noqa: BLE001
            self._on_status(f"ошибка синтеза: {exc}")
            with self._lock:
                self._active_id = None
            self._send_next()

    def _push_to_headphones(self, pcm: np.ndarray) -> None:
        """Отправить PCM в MicBridge только в наушники (не в кабель)."""
        bridge = self._mic_bridge
        if bridge is None or not getattr(bridge, "running", False):
            return
        try:
            bridge.push_incoming_pcm(pcm, lc.SR_TTS)
        except Exception:
            pass
