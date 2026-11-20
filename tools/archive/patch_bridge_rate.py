"""Патч: мост подбирает частоту дискретизации, поддерживаемую обоими устройствами.

Микрофоны бывают только на 44.1 кГц (Fifine), а наушники — на 48 кГц.
Без согласования частот микрофон и выход расходятся по времени.

    python tools\\patch_bridge_rate.py
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "app", "mic_bridge.py")

OLD_CONST = '''SR = 48000          # рабочая частота моста
BLOCK = 1024        # размер блока
'''

NEW_CONST = '''BLOCK = 1024        # размер блока
RATE_CANDIDATES = (48000, 44100, 32000, 16000)


def pick_sample_rate(mic_device, render_device) -> int:
    """Частота, которую поддерживают оба устройства.

    Микрофон может быть только на 44.1 кГц, а наушники — на 48 кГц: тогда
    мост работать не станет, и речь/фразы разъедутся по времени.
    """
    import sounddevice as sd
    for rate in RATE_CANDIDATES:
        ok = True
        try:
            if mic_device is not None:
                sd.check_input_settings(device=mic_device, channels=1, dtype="float32",
                                        samplerate=rate)
            if render_device is not None:
                sd.check_output_settings(device=render_device, channels=1,
                                         dtype="float32", samplerate=rate)
        except Exception:
            ok = False
        if ok:
            return rate
    return 48000
'''

OLD_INIT = '''        self._mic_blocks: deque[np.ndarray] = deque(maxlen=64)
'''
NEW_INIT = '''        self.sr = pick_sample_rate(mic_device, render_device)
        self._mic_blocks: deque[np.ndarray] = deque(maxlen=64)
'''

OLD_START = '''        kwargs = {"device": self.mic_device} if self.mic_device is not None else {}
        self._in = sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                 blocksize=BLOCK, callback=self._in_callback, **kwargs)
        out_kwargs = {"device": self.render_device} if self.render_device is not None else {}
        self._out = sd.OutputStream(samplerate=SR, channels=1, dtype="float32",
                                    blocksize=BLOCK, callback=self._out_callback, **out_kwargs)
'''
NEW_START = '''        kwargs = {"device": self.mic_device} if self.mic_device is not None else {}
        self._in = sd.InputStream(samplerate=self.sr, channels=1, dtype="float32",
                                 blocksize=BLOCK, callback=self._in_callback, **kwargs)
        out_kwargs = {"device": self.render_device} if self.render_device is not None else {}
        self._out = sd.OutputStream(samplerate=self.sr, channels=1, dtype="float32",
                                    blocksize=BLOCK, callback=self._out_callback, **out_kwargs)
'''

OLD_PLAY = '''        if sr != SR:
            from math import gcd
            from scipy.signal import resample_poly
            g = gcd(int(sr), SR)
            data = resample_poly(data, SR // g, int(sr) // g).astype(np.float32)
'''
NEW_PLAY = '''        if sr != self.sr:
            from math import gcd
            from scipy.signal import resample_poly
            g = gcd(int(sr), self.sr)
            data = resample_poly(data, self.sr // g, int(sr) // g).astype(np.float32)
'''

OLD_MON = '''                sd.play(data, samplerate=SR, device=self.monitor_device)
'''
NEW_MON = '''                sd.play(data, samplerate=self.sr, device=self.monitor_device)
'''

OLD_STATUS = '''        return {"running": self.running, "mic_peak": self.mic_peak,
                "out_peak": self.peak_out}
'''
NEW_STATUS = '''        return {"running": self.running, "mic_peak": self.mic_peak,
                "out_peak": self.peak_out, "sr": self.sr}
'''


def main() -> None:
    with io.open(TARGET, encoding="utf-8") as fh:
        src = fh.read()
    applied = []
    for label, old, new in (("константы", OLD_CONST, NEW_CONST),
                            ("инициализация", OLD_INIT, NEW_INIT),
                            ("потоки", OLD_START, NEW_START),
                            ("ресемплинг фразы", OLD_PLAY, NEW_PLAY),
                            ("монитор", OLD_MON, NEW_MON),
                            ("статус", OLD_STATUS, NEW_STATUS)):
        if old in src:
            src = src.replace(old, new, 1)
            applied.append(label)
        else:
            print(f"  ! не найдено: {label}")
    with io.open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("Применено:", ", ".join(applied) if applied else "ничего")


if __name__ == "__main__":
    main()
