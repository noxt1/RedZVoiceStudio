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


def _native_rate(idx: int) -> int:
    """Родная частота устройства — на ней же работает и мост."""
    try:
        import sounddevice as sd
        return int(float(sd.query_devices(idx)["default_samplerate"]))
    except Exception:
        return 0


def _test_input(idx: int, rate: int, seconds: float = 0.35) -> bool:
    import numpy as np
    import sounddevice as sd
    try:
        with sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                            device=idx, blocksize=1024) as st:
            data, _ = st.read(int(rate * seconds))
        if len(data) == 0:
            return False
        # «Чужая» частота открывается без ошибки, но отдаёт ЦИФРОВЫЕ НУЛИ.
        # Раньше такой вариант считался рабочим, запись шла с него и
        # выходила тишиной (индикатор микрофона не двигался вообще).
        return float(np.abs(data).max()) > 1e-7
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
    # Сначала родная частота устройства: на ней поток открывается
    # штатно, без пересэмплирования драйвером.
    native = _native_rate(idx)
    order = ([native] if native else []) + [r for r in CANDIDATE_RATES if r != native]
    rates = []
    for rate in order:
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


_EXCLUSIVE_APIS = ("wdm-ks",)


def _same_device_name(name: str) -> str:
    """Имя без хвоста «2- »: WDM-KS зовёт микрофон без него.

    «Микрофон (2- fifine Microphone)» (MME) и «Микрофон (fifine
    Microphone)» (WDM-KS) — одно и то же устройство.
    """
    import re
    s = " ".join(str(name).lower().split())
    return re.sub(r"\(\s*\d+\s*-\s*", "(", s)


def safe_input(idx: int | None) -> int | None:
    """Тот же микрофон, но в обычном (разделяемом) host API.

    PortAudio показывает один и тот же микрофон несколько раз — для MME,
    DirectSound, WASAPI и WDM-KS. WDM-KS работает эксклюзивно: устройство
    может не открыться (занято системой) или открыться без звука, а имя у
    него без хвоста «(2- ...)» — по нему такие записи и видно. Если выбрано
    именно WDM-KS-устройство, подставляем его копию из MME/WASAPI.
    """
    if idx is None:
        return None
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        apis = sd.query_hostapis()
        dev = devices[idx]
        api = str(apis[dev["hostapi"]]["name"]).lower()
        if not any(bad in api for bad in _EXCLUSIVE_APIS):
            return idx
        name = _same_device_name(str(dev["name"]))
        best = None
        for i, d in enumerate(devices):
            if int(d["max_input_channels"]) <= 0:
                continue
            if _same_device_name(str(d["name"])) != name:
                continue
            twin = str(apis[d["hostapi"]]["name"]).lower()
            if any(bad in twin for bad in _EXCLUSIVE_APIS):
                continue
            score = 0 if "mme" in twin else (1 if "directsound" in twin else 2)
            if best is None or score < best[0]:
                best = (score, i)
        return best[1] if best else idx
    except Exception:
        return idx
