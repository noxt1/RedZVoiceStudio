"""Воспроизведение аудио в новом интерфейсе.

Один модуль на все случаи:
  * проиграть готовую звуковую подсказку;
  * проиграть запись пользователя или собранный reference.wav;
  * сравнить подсказку и запись — «одновременно» или «с задержкой».

Устройство вывода выбирается явно: мост (наушники) → системный дефолт.
Раньше здесь использовался sd.play() без устройства — он уходил не туда
и подвисал, из-за чего образец интонации «не проигрывался».
"""

from __future__ import annotations

import os

import numpy as np

TARGET_SR = 44100


# --------------------------------------------------------------------------
# Устройство вывода
# --------------------------------------------------------------------------
def output_device(studio=None) -> int | None:
    """Куда играть: мост (наушники) → системный вывод по умолчанию."""
    dev = None
    try:
        bridge = getattr(studio, "bridge", None)
        if bridge is not None:
            dev = getattr(bridge, "monitor_device", None)
    except Exception:
        dev = None
    if dev is None:
        try:
            import sounddevice as sd
            dev = sd.default.device[1]
        except Exception:
            dev = None
    return dev


# --------------------------------------------------------------------------
# Загрузка
# --------------------------------------------------------------------------
def load_wav(path: str):
    """(аудио float32, частота). None, если файл не читается."""
    if not path or not os.path.exists(path):
        return None
    try:
        import soundfile as sf
        data, sr = sf.read(path, dtype="float32", always_2d=False)
        if getattr(data, "ndim", 1) > 1:
            data = data.mean(axis=1)
        return np.asarray(data, dtype=np.float32), int(sr)
    except Exception:
        return None


def resample(data: np.ndarray, sr: int, target: int = TARGET_SR) -> np.ndarray:
    """Линейная передискретизация (достаточно для прослушивания)."""
    if sr == target or len(data) == 0:
        return data
    n = int(round(len(data) * target / float(sr)))
    if n <= 1:
        return np.zeros(target // 2, dtype=np.float32)
    src = np.linspace(0.0, len(data) - 1.0, num=len(data))
    dst = np.linspace(0.0, len(data) - 1.0, num=n)
    return np.interp(dst, src, data).astype(np.float32)


# --------------------------------------------------------------------------
# Воспроизведение
# --------------------------------------------------------------------------
def play_array(data, sr: int, studio=None) -> None:
    """Проиграть массив (блокирующий вызов — оборачивать в поток).

    Устройство выбираем аккуратно: мост (наушники) -> дефолт -> первые
    живые выходы. Раньше OutputStream открывался только на одном
    устройстве, и если оно было занято, «Прослушать» молча ничего
    не делал (исключение глоталось в вызывающем коде).
    """
    if data is None or len(data) == 0:
        return
    arr = np.asarray(data, dtype=np.float32)
    rate = int(sr) if sr else TARGET_SR

    stream = None
    tried = []
    for dev in _device_candidates(studio):
        if dev in tried:
            continue
        tried.append(dev)
        try:
            stream = _open_output(dev, rate)
            break
        except Exception:
            stream = None
    if stream is None:
        return

    stream.start()
    try:
        block = 1024
        pos = 0
        while pos < len(arr):
            chunk = arr[pos:pos + block]
            if len(chunk) < block:
                chunk = np.concatenate([chunk, np.zeros(block - len(chunk),
                                                       dtype=np.float32)])
            stream.write(chunk.reshape(-1, 1))
            pos += block
    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass


def _open_output(device, rate: int):
    """Открыть OutputStream на конкретном устройстве."""
    import sounddevice as sd
    kwargs = {"device": device} if device is not None else {}
    return sd.OutputStream(samplerate=rate, channels=1, dtype="float32",
                           blocksize=1024, **kwargs)


def _device_candidates(studio=None) -> list:
    """Кандидаты для воспроизведения: мост -> дефолт -> первые живые выходы."""
    out = []

    dev = output_device(studio)
    if dev is not None:
        out.append(dev)

    try:
        import sounddevice as sd
        try:
            d = sd.default.device[1]
            if d is not None and d not in out:
                out.append(d)
        except Exception:
            pass
        for i, info in enumerate(sd.query_devices()):
            if info.get("max_output_channels", 0) > 0 and i not in out:
                out.append(i)
            if len(out) >= 6:
                break
    except Exception:
        pass
    return out

def play_file(path: str, studio=None) -> bool:
    """Проиграть файл. False, если нечего играть.

    Использует общий плеер: новый запуск останавливает предыдущий,
    поэтому два файла не звучат одновременно.
    """
    return player_play_file(path, studio) is not None


# --------------------------------------------------------------------------
# Единый плеер: один поток, остановка, переключение «играть/стоп»
# --------------------------------------------------------------------------
import threading

_lock = threading.Lock()
_player = {
    "stream": None,      # активный OutputStream
    "thread": None,      # поток воспроизведения
    "stop": False,       # флаг остановки
    "path": None,        # что играет сейчас
    "playing": False,
}


def player_stop():
    """Остановить текущее воспроизведение.

    Поток НЕ закрывается здесь: это приводит к access violation в
    PortAudio (close из чужого потока). Ставим флаг — воркер сам
    выйдет из цикла и закроет поток у себя.
    """
    with _lock:
        _player["stop"] = True
        _player["playing"] = False
        _player["path"] = None


def player_is_playing() -> bool:
    with _lock:
        return bool(_player["playing"])


def player_current() -> str | None:
    with _lock:
        return _player["path"]


def player_toggle_file(path: str, studio=None):
    """Играть файл или остановить, если он уже играет.

    Возвращает True, если после вызова файл ИГРАЕТ, False — если
    остановлен (или играть нечего).
    """
    with _lock:
        same = (_player["path"] == path and _player["playing"])
    if same:
        player_stop()
        return False
    return player_play_file(path, studio) is not None


def player_play_file(path: str, studio=None):
    """Запустить воспроизведение файла (прервав предыдущее)."""
    loaded = load_wav(path)
    if loaded is None:
        return None
    data, sr = loaded
    with _lock:
        old = _player["thread"]
    player_stop()
    # Ждём, пока старый воркер увидит stop и закроет поток: иначе два
    # OutputStream на одном устройстве коротко звучат вместе, а на
    # виртуальном кабеле — заметно дольше (звук «накладывается»).
    if old is not None and old.is_alive():
        old.join(timeout=0.5)

    # обнуляем перед новым запуском
    with _lock:
        _player["stop"] = False
        _player["path"] = path
        _player["playing"] = True

    t = threading.Thread(target=_player_worker,
                         args=(data, sr, studio, path), daemon=True)
    with _lock:
        _player["thread"] = t
    t.start()
    return t


def _player_worker(data, sr, studio, path=None):
    """Поток воспроизведения: пишет блоки в stream, проверяет stop."""
    arr = np.asarray(data, dtype=np.float32)
    rate = int(sr) if sr else TARGET_SR

    stream = None
    tried = []
    for dev in _device_candidates(studio):
        if dev in tried:
            continue
        tried.append(dev)
        try:
            stream = _open_output(dev, rate)
            break
        except Exception:
            stream = None
    if stream is None:
        with _lock:
            _player["playing"] = False
        return

    with _lock:
        _player["stream"] = stream

    stream.start()
    try:
        block = 256          # мельче: stop замечается быстрее
        pos = 0
        while pos < len(arr):
            with _lock:
                if _player["stop"]:
                    break
                # если нас уже сменил другой запуск — выходим
                if _player["path"] != path:
                    break
            chunk = arr[pos:pos + block]
            if len(chunk) < block:
                chunk = np.concatenate([chunk, np.zeros(block - len(chunk),
                                                       dtype=np.float32)])
            stream.write(chunk.reshape(-1, 1))
            pos += block
    except Exception:
        pass
    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
        with _lock:
            if _player["stream"] is stream:
                _player["stream"] = None
                _player["playing"] = False
                _player["path"] = None


# --------------------------------------------------------------------------
# Сравнение: образец + своя запись
# --------------------------------------------------------------------------
def compare(prompt_path: str, take_path: str, mode: str = "together",
            studio=None, gap: float = 0.6) -> bool:
    """Сравнить образец интонации со своей записью.

    mode:
        "together" — одновременно (наложение двух дорожек);
        "delay"    — сначала образец, потом пауза, потом своя запись.
    False, если нечего сравнивать.
    """
    p = load_wav(prompt_path)
    t = load_wav(take_path)
    if p is None and t is None:
        return False

    sr = TARGET_SR
    pa = resample(p[0], p[1], sr) if p else np.zeros(0, dtype=np.float32)
    ta = resample(t[0], t[1], sr) if t else np.zeros(0, dtype=np.float32)

    if mode == "delay":
        parts = []
        if len(pa):
            parts.append(pa)
            parts.append(np.zeros(int(sr * gap), dtype=np.float32))
        if len(ta):
            parts.append(ta)
        mixed = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    else:
        n = max(len(pa), len(ta))
        mixed = np.zeros(n, dtype=np.float32)
        if len(pa):
            mixed[:len(pa)] += pa * 0.85
        if len(ta):
            mixed[:len(ta)] += ta * 0.85
        peak = float(np.abs(mixed).max()) if mixed.size else 0.0
        if peak > 0.99:
            mixed = mixed * (0.99 / peak)

    if not len(mixed):
        return False
    play_array(mixed, sr, studio)
    return True


def speak_silence(seconds: float, sr: int = TARGET_SR) -> np.ndarray:
    """Тишина заданной длины (для склейки)."""
    return np.zeros(int(sr * seconds), dtype=np.float32)
