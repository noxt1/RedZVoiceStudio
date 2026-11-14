"""Рабочие частоты устройств: у каждого микрофона своя.

PortAudio умеет открыть устройство на нескольких частотах, но на «чужих»
частотах поток открывается и отдаёт тишину (нули). Из-за этого раньше мост
работал вхолостую: Fifine открывался на 48 кГц, а отдавал данные на 16 кГц.

Модуль перебирает частоты и запоминает рабочие.
"""

from __future__ import annotations

import threading
import time

CANDIDATE_RATES = (16000, 22050, 32000, 44100, 48000)

_cache: dict[tuple[str, int], list[int]] = {}
_lock = threading.Lock()


def _test_input(idx: int, rate: int, seconds: float = 0.35) -> bool:
    import sounddevice as sd
    try:
        with sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                            device=idx, blocksize=1024) as st:
            data, _ = st.read(int(rate * seconds))
        return len(data) > 0
    except Exception:
        return False


def _test_output(idx: int, rate: int) -> bool:
    import sounddevice as sd
    import numpy as np
    try:
        with sd.OutputStream(samplerate=rate, channels=1, dtype="float32",
                             device=idx, blocksize=1024) as st:
            st.write(np.zeros(int(rate * 0.08), dtype="float32"))
        return True
    except Exception:
        return False


def working_rates(idx: int, kind: str = "input") -> list[int]:
    """Частоты, на которых устройство реально работает."""
    key = (kind, int(idx))
    with _lock:
        if key in _cache:
            return _cache[key]
    rates = []
    for rate in CANDIDATE_RATES:
        ok = _test_input(idx, rate) if kind == "input" else _test_output(idx, rate)
        if ok:
            rates.append(rate)
    with _lock:
        _cache[key] = rates
    return rates


def best_rate(idx: int | None, kind: str = "input",
              fallback: int = 48000) -> int:
    """Рабочая частота устройства (или запасной вариант)."""
    if idx is None:
        return fallback
    rates = working_rates(idx, kind)
    return rates[0] if rates else fallback


def device_label(idx: int, name: str, kind: str = "input") -> str:
    """Подпись устройства с рабочей частотой."""
    rates = working_rates(idx, kind)
    if not rates:
        return f"{name} — не работает"
    return f"{name}  [{rates[0]} Гц]"


def level_probe(idx: int | None, seconds: float = 0.6) -> float:
    """Текущий пик на входе (0 — тишина или устройство не открывается)."""
    import numpy as np
    import sounddevice as sd
    if idx is None:
        return 0.0
    rate = best_rate(idx, "input")
    try:
        rec = sd.rec(int(seconds * rate), samplerate=rate, channels=1,
                     dtype="float32", device=idx)
        sd.wait()
        audio = np.asarray(rec, dtype="float32").squeeze()
        return float(np.abs(audio).max()) if audio.size else 0.0
    except Exception:
        return 0.0
