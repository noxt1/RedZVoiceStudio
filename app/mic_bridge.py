"""Мост микрофон -> выход с учётом индивидуальных частот устройств.

Раньше мост открывал потоки на фиксированной частоте (48 кГц), но часть
устройств на «чужих» частотах отдаёт тишину. Теперь частота подбирается
по каждому устройству отдельно (app/audiodev.py).
"""

from __future__ import annotations

import threading
from collections import deque

import numpy as np

BLOCK = 1024        # размер блока
RATE_CANDIDATES = (48000, 44100, 32000, 16000)

# Порог мягкого лимитера: выше начинается плавное сжатие.
LIMIT_THRESHOLD = 0.90


def _soft_limit(x: np.ndarray, threshold: float = LIMIT_THRESHOLD) -> np.ndarray:
    """Мягкий лимитер: пики сжимаются плавно, без жёсткой обрезки.

    Жёсткий np.clip(x, -1, 1) срезал вершины пиков — на слух это
    «проглоченные» согласные и щелчки. Здесь всё, что ниже порога,
    проходит без изменений, а выбросы выше порога плавно подводятся
    к единице (tanh-подобная кривая).
    """
    a = np.abs(x)
    peak = float(a.max()) if a.size else 0.0
    if peak <= threshold:
        return x
    out = x.copy()
    over = a > threshold
    exc = a[over] - threshold
    headroom = max(1.0 - threshold, 1e-6)
    compressed = threshold + headroom * np.tanh(exc / headroom)
    out[over] = np.sign(x[over]) * compressed
    return out


def pick_sample_rate(mic_device, render_device) -> int:
    """Частота, которую поддерживают оба устройства (иначе речь разъедется)."""
    import sounddevice as sd

    def works(device, rate, kind):
        try:
            if kind == "input":
                with sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                    device=device, blocksize=1024):
                    pass
            else:
                with sd.OutputStream(samplerate=rate, channels=1, dtype="float32",
                                     device=device, blocksize=1024):
                    pass
            return True
        except Exception:
            return False

    for rate in RATE_CANDIDATES:
        if (mic_device is None or works(mic_device, rate, "input")) and \
           (render_device is None or works(render_device, rate, "output")):
            return rate
    return 48000


class MicBridge:
    """Непрерывный мост микрофон -> устройство вывода с подмешиванием фраз."""

    def __init__(self, mic_device: int | None, render_device: int | None,
                 mic_gain: float = 1.0, phrase_gain: float = 1.0,
                 monitor_device: int | None = None,
                 monitor_gain: float = 1.0):
        self.mic_device = mic_device
        self.render_device = render_device
        self.mic_gain = mic_gain
        self.phrase_gain = phrase_gain
        # Устройство, на котором ИГРОК слушает себя. Если оно отличается от
        # render_device, фраза дублируется туда — чтобы игрок её слышал.
        self.monitor_device = monitor_device
        if monitor_device is not None and monitor_device == render_device:
            self.monitor_device = None
        # Громкость перевода в наушниках (что слышит игрок).
        self.monitor_gain = monitor_gain
        # Монитор может открыться не на той же частоте, что кабель:
        # тогда данные для наушников ресемплим заранее (в push_*).
        self._mon_sr = 0
        self.monitor_error = ""
        self._mon_was_pushed = False

        self.sr = pick_sample_rate(mic_device, render_device)
        self._mic_blocks: deque[np.ndarray] = deque(maxlen=16)
        # последние секунды микрофона: нужно, чтобы по кнопке перевести
        # то, что игрок только что сказал
        self._recent: deque[np.ndarray] = deque(maxlen=800)
        # «заглушка»: русский голос приглушен, в кабель идёт только перевод.
        # Стартовое состояние БЕЗОПАСНОЕ: microphone не идёт ни в один выход,
        # пока не подтверждено, что вывод — реальный виртуальный кабель.
        self.ducked = True
        self._mic_gain_now = 0.0
        # сколько чанков перевода потеряно из-за переполнения очереди
        self.stream_dropped = 0
        self._phrase: np.ndarray | None = None
        self._phrase_pos = 0
        # потоковое аудио (живой перевод): очередь чанков.
        # maxlen=8 при блоке 1024/48кГц — максимум ~170 мс буфера.
        # Раньше было 64 (~1.4 с), и перевод опаздывал на секунду с лишним.
        self._stream_q: deque[np.ndarray] = deque(maxlen=8)
        # очередь для наушников (что слышит игрок)
        self._mon_q: deque[np.ndarray] = deque(maxlen=8)
        self._lock = threading.Lock()
        self._in = None
        self._out = None
        self._mon = None
        self.running = False
        self.peak_out = 0.0
        self.mic_peak = 0.0
        # Общая громкость того, что уходит В КАБЕЛЬ (и речь, и перевод).
        # master_gain = 1.0 — как есть.
        self.out_gain = 1.0

    # ---------- внутреннее ----------
    def _in_callback(self, indata, frames, time_info, status):  # noqa: ARG001
        mono = indata[:, 0] if indata.ndim > 1 else indata
        block = mono.astype(np.float32).copy()
        self._mic_blocks.append(block)
        self._recent.append(block)
        self.mic_peak = max(self.mic_peak * 0.995, float(np.abs(mono).max()))

    def _out_callback(self, outdata, frames, time_info, status):  # noqa: ARG001
        # Исключение здесь PortAudio считает отказом потока: кабель замолкает
        # до переоткрытия. Поэтому любая ошибка смешивания = тишина, а не краш.
        try:
            self._mix_out(outdata, frames)
        except Exception:
            try:
                outdata.fill(0)
            except Exception:
                pass

    def _mix_out(self, outdata, frames) -> None:
        with self._lock:
            if self._mic_blocks:
                chunk = self._mic_blocks.popleft()
            else:
                chunk = np.zeros(BLOCK, dtype=np.float32)
            if len(chunk) < frames:
                chunk = np.pad(chunk, (0, frames - len(chunk)))

            phrase_part = np.zeros(frames, dtype=np.float32)
            if self._phrase is not None:
                remaining = len(self._phrase) - self._phrase_pos
                take = min(frames, remaining)
                if take > 0:
                    phrase_part[:take] = self._phrase[self._phrase_pos:self._phrase_pos + take]
                    self._phrase_pos += take
                    if self._phrase_pos >= len(self._phrase):
                        self._phrase = None
                        self._phrase_pos = 0

            # потоковое аудио (живой перевод) — приоритетнее готовой фразы
            stream_part = np.zeros(frames, dtype=np.float32)
            if self._stream_q:
                stream_chunk = self._stream_q.popleft()
                take = min(frames, len(stream_chunk))
                if take > 0:
                    stream_part[:take] = stream_chunk[:take]
                    if take < len(stream_chunk):
                        self._stream_q.appendleft(stream_chunk[take:])

        # «заглушка»: пока она включена, русский голос в кабель НЕ идёт —
        # слышен только перевод (переключатель языка)
        # Плавное затухание/нарастание: без него русский «резко обрывался»
        # при нажатии PTT и резко возвращался после перевода.
        target = 0.0 if self.ducked else self.mic_gain
        if self._mic_gain_now < target:
            self._mic_gain_now = min(target, self._mic_gain_now + 0.10)
        else:
            self._mic_gain_now = max(target, self._mic_gain_now - 0.10)
        mic_gain = self._mic_gain_now
        mix = chunk * mic_gain + (phrase_part + stream_part) * self.phrase_gain
        # Общая громкость кабеля
        mix *= self.out_gain
        # Мягкий лимитер вместо жёсткого np.clip: жёсткий клип срезал пики
        # и звучал как «проглоченные» согласные. Здесь выбросы плавно
        # сжимаются, а обычная громкость не меняется.
        mix = _soft_limit(mix)
        self.peak_out = max(self.peak_out * 0.99, float(np.abs(mix).max()))
        outdata[:] = mix.reshape(-1, 1)

    # ---------- публичное ----------
    def start(self) -> None:
        import sounddevice as sd
        if self.running:
            return
        self._mic_blocks.clear()
        self._phrase = None
        self._phrase_pos = 0

        mic_kwargs = {"device": self.mic_device} if self.mic_device is not None else {}
        out_kwargs = {"device": self.render_device} if self.render_device is not None else {}
        self._in = sd.InputStream(samplerate=self.sr, channels=1, dtype="float32",
                                 blocksize=BLOCK, callback=self._in_callback, **mic_kwargs)
        self._out = sd.OutputStream(samplerate=self.sr, channels=1, dtype="float32",
                                    blocksize=BLOCK, callback=self._out_callback, **out_kwargs)
        self._in.start()
        self._out.start()
        # Отдельный выход в наушники: игрок слышит перевод (то, что говорят
        # его персонажу), не мешая кабелю. Монитор открываем с подбором
        # частоты: у наушников она не всегда совпадает с кабелем.
        self._mon = None
        self._mon_sr = 0
        self.monitor_error = ""
        if self.monitor_device is not None:
            self._open_monitor()
        self.running = True

    def _open_monitor(self) -> None:
        """Открыть поток в наушники на первой поддерживаемой частоте."""
        import sounddevice as sd
        self._mon = None
        self.monitor_error = ""
        rates = []
        if self.sr:
            rates.append(int(self.sr))
        rates.extend(r for r in RATE_CANDIDATES if r not in rates)
        for rate in rates:
            try:
                stream = sd.OutputStream(
                    samplerate=rate, channels=1, dtype="float32",
                    blocksize=BLOCK, callback=self._mon_callback,
                    device=self.monitor_device)
                stream.start()
            except Exception as exc:  # noqa: BLE001
                self.monitor_error = f"{type(exc).__name__}: {exc}"
                continue
            with self._lock:
                self._mon = stream
                self._mon_sr = int(rate)
                self._mon_q.clear()
            self.monitor_error = ""
            return
        # Не смогли — не роняем мост: кабель и микрофон должны работать.
        self._mon = None
        self._mon_sr = 0

    def set_monitor_device(self, device: int | None) -> None:
        """Сменить устройство наушников на лету (без перезапуска моста)."""
        if device is not None and device == self.render_device:
            device = None
        if device == self.monitor_device:
            return
        self.monitor_device = device
        if not self.running:
            return
        old = self._mon
        self._mon = None
        if old is not None:
            try:
                old.stop()
                old.close()
            except Exception:
                pass
        with self._lock:
            self._mon_q.clear()
            self._mon_sr = 0
        if device is not None:
            self._open_monitor()


    def stop(self) -> None:
        for stream in (self._in, self._out, self._mon):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self._in = self._out = self._mon = None
        self._mon_sr = 0
        self.running = False

    def _mon_callback(self, outdata, frames, time_info, status):  # noqa: ARG001
        """Вывод в наушники: перевод с регулируемой громкостью."""
        try:
            self._mix_mon(outdata)
        except Exception:
            try:
                outdata.fill(0)
            except Exception:
                pass

    def _mix_mon(self, outdata) -> None:
        need = outdata.shape[0]
        out = np.zeros(need, dtype=np.float32)
        pos = 0
        with self._lock:
            while pos < need and self._mon_q:
                chunk = self._mon_q[0]
                take = min(need - pos, len(chunk))
                if take <= 0:
                    self._mon_q.popleft()
                    continue
                out[pos:pos + take] = chunk[:take] * self.monitor_gain
                if take < len(chunk):
                    self._mon_q[0] = chunk[take:]
                else:
                    self._mon_q.popleft()
                pos += take
        outdata[:, 0] = _soft_limit(out)

    def play_phrase(self, path: str) -> bool:
        """Подмешать фразу в микшер (её услышат все, кто слышит микрофон)."""
        import soundfile as sf
        try:
            data, sr = sf.read(path, dtype="float32", always_2d=False)
        except Exception:
            return False
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != self.sr:
            # scipy нет в EXE (исключён из сборки) -> линейная интерполяция
            n_out = int(round(len(data) * self.sr / sr))
            if n_out > 0 and len(data) > 1:
                x_in = np.arange(len(data), dtype=np.float64)
                x_out = np.linspace(0, len(data) - 1, n_out)
                data = np.interp(x_out, x_in, data).astype(np.float32)
        peak = float(np.abs(data).max()) if len(data) else 0.0
        if peak > 1.0:
            data = data / peak
        with self._lock:
            self._phrase = data.astype(np.float32)
            self._phrase_pos = 0

        if self.monitor_device is not None:
            try:
                import sounddevice as sd
                # громкость в наушниках регулируется ползунком
                sd.play(data * self.monitor_gain, samplerate=self.sr,
                        device=self.monitor_device)
            except Exception:
                pass
        return True

    def set_duck(self, flag: bool) -> None:
        """Заглушить/восстановить русский голос в потоке.

        Нужно для «переключателя языка»: игрок говорит по-русски, жмёт
        кнопку — русский мгновенно пропадает, и в кабель идёт только перевод.
        """
        self.ducked = bool(flag)

    def set_gains(self, monitor_gain: float | None = None,
                  phrase_gain: float | None = None,
                  out_gain: float | None = None) -> None:
        """Настроить громкости.

        monitor_gain — что слышит ИГРОК (перевод в наушниках);
        phrase_gain  — громкость ПЕРЕВОДА относительно своей речи;
        out_gain     — общая громкость В КАБЕЛЬ (и речь, и перевод).
        """
        if monitor_gain is not None:
            self.monitor_gain = float(monitor_gain)
        if phrase_gain is not None:
            self.phrase_gain = float(phrase_gain)
        if out_gain is not None:
            self.out_gain = float(out_gain)

    def recent_audio(self, seconds: float = 5.0) -> np.ndarray:
        """Последние N секунд микрофона (то, что игрок только что сказал)."""
        need = max(1, int(self.sr * seconds / 1024))
        with self._lock:
            blocks = list(self._recent)[-need:]
        if not blocks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(blocks)

    def push_pcm(self, pcm: np.ndarray, sr: int) -> bool:
        """Подмешать потоковое аудио в микшер (живой перевод).

        Так перевод идёт В ТОТ ЖЕ поток, что и твоя речь с микрофона,
        а значит Discord/игра услышат и то, и другое.

        Если включён выход в наушники — дубль туда же: игрок слышит, что
        говорит его персонаж (с регулируемой громкостью).
        """
        if pcm is None or len(pcm) == 0:
            return False
        data = np.asarray(pcm, dtype=np.float32)
        if data.ndim > 1:
            data = data.mean(axis=1)
        data = self._resample(data, sr, self.sr)
        if data is None:
            return False
        peak = float(np.abs(data).max()) if len(data) else 0.0
        if peak > 1.0:
            data = data / peak
        # В наушники кладём всегда, даже если поток ещё не открылся:
        # иначе первый перевод после старта уходил только в кабель.
        mon = self._resample(data, self.sr, self._mon_sr) \
            if self._mon_sr else data
        with self._lock:
            # maxlen не даёт копить задержку, но старый чанк при этом теряется:
            # считаем такие потери, иначе «пропал звук» выглядит загадочно.
            if len(self._stream_q) >= self._stream_q.maxlen:
                self.stream_dropped += 1
            self._stream_q.append(data.astype(np.float32))
            if self.monitor_device is not None and mon is not None:
                self._mon_q.append(mon.astype(np.float32))
                self._mon_was_pushed = True
        return True

    def push_incoming_pcm(self, pcm: np.ndarray, sr: int) -> bool:
        """Отдать аудио входящего перевода только в наушники (не в кабель).

        Критически важно: этот метод НЕ добавляет аудио в _stream_q (кабель),
        иначе русский TTS попадёт обратно в виртуальный микрофон и может быть
        перехвачен перехvatом речи игроков (аудиопетель).
        """
        if pcm is None or len(pcm) == 0:
            return False
        data = np.asarray(pcm, dtype=np.float32)
        if data.ndim > 1:
            data = data.mean(axis=1)
        data = self._resample(data, sr, self.sr)
        if data is None:
            return False
        peak = float(np.abs(data).max()) if len(data) else 0.0
        if peak > 1.0:
            data = data / peak
        mon = self._resample(data, self.sr, self._mon_sr) \
            if self._mon_sr else data
        with self._lock:
            if self.monitor_device is not None and mon is not None:
                self._mon_q.append(mon.astype(np.float32))
                self._mon_was_pushed = True
        return True

    @staticmethod
    def _resample(data: np.ndarray, src: int, dst: int) -> np.ndarray | None:
        """Линейный ресемплинг (scipy в EXE нет)."""
        if data is None or len(data) == 0:
            return None
        if not src or not dst or int(src) == int(dst):
            return np.asarray(data, dtype=np.float32)
        n_out = int(round(len(data) * float(dst) / float(src)))
        if n_out <= 0 or len(data) < 2:
            return None
        x_in = np.arange(len(data), dtype=np.float64)
        x_out = np.linspace(0, len(data) - 1, n_out)
        return np.interp(x_out, x_in, data).astype(np.float32)

    def clear_stream(self) -> None:
        """Убрать весь недозвучавший перевод из очереди.

        Нужно, когда перевод выключают: иначе уже отправленные чанки
        продолжают играть ПАРАЛЛЕЛЬНО с живым русским голосом.
        """
        with self._lock:
            self._stream_q.clear()

    def stream_pending(self) -> bool:
        """Есть ли ещё аудио перевода в очереди воспроизведения?

        Нужно, чтобы понять, когда перевод дозвучал и пора вернуть русский
        голос (в мосте, а не в локальном плеере).
        """
        with self._lock:
            return bool(self._stream_q)

    def ensure_alive(self) -> str:
        """Переоткрыть выход, если поток умер (WASAPI/MME иногда отваливается).

        Возвращает текст для лога: пустая строка — всё в порядке.
        """
        if not self.running or self._out is None:
            return ""
        try:
            if self._out.active:
                return ""
        except Exception:
            pass
        import sounddevice as sd
        try:
            try:
                self._out.stop()
                self._out.close()
            except Exception:
                pass
            kwargs = {"device": self.render_device} if self.render_device is not None else {}
            fresh = sd.OutputStream(samplerate=self.sr, channels=1,
                                    dtype="float32", blocksize=BLOCK,
                                    callback=self._out_callback, **kwargs)
            fresh.start()
        except Exception as exc:  # noqa: BLE001
            return f"выход не переоткрылся: {type(exc).__name__}: {exc}"
        with self._lock:
            self._out = fresh
        return "выход переоткрыт после сбоя"

    def status(self) -> dict:
        return {"running": self.running, "mic_peak": self.mic_peak,
                "out_peak": self.peak_out, "sr": self.sr,
                "monitor": self.monitor_device,
                "monitor_sr": self._mon_sr,
                "monitor_ok": self._mon is not None,
                "monitor_error": self.monitor_error}
