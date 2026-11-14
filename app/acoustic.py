"""Акустический режим: фраза играет в динамики, микрофон её подхватывает.

Это единственный способ обойтись без виртуального кабеля, когда игра
показывает в микрофонах только реальные устройства (Razer, Fifine), а
loopback-устройства (Stereo Mix) в системе нет.

Схема:
    приложение -> динамики -> (воздух) -> микрофон Fifine -> игра

Калибровка подбирает громкость, при которой микрофон уверенно слышит фразу,
и проверяет, нет ли риска «свиста» (слишком сильный сигнал в микрофоне).
"""

from __future__ import annotations

import threading
import time

import numpy as np

SR = 48000


class AcousticPlayer:
    """Играет фразы в выход, измеряя, как их слышит микрофон."""

    def __init__(self, out_device: int | None = None, mic_device: int | None = None):
        self.out_device = out_device
        self.mic_device = mic_device
        self.gain = 1.0
        self.calibrated = False

    # ---------- измерение ----------
    def _measure_pickup(self, phrase: np.ndarray, gain: float,
                        seconds: float = 1.6) -> dict:
        """Проиграть фразу с усилением и измерить, что услышал микрофон."""
        import sounddevice as sd
        import soundfile as sf

        frames = int(seconds * SR)
        captured = []

        def recorder():
            try:
                with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                    device=self.mic_device, blocksize=1024) as st:
                    data, _ = st.read(frames)
                    captured.append(data[:, 0].copy())
            except Exception:
                pass

        th = threading.Thread(target=recorder, daemon=True)
        th.start()
        time.sleep(0.25)

        try:
            sd.play((phrase * gain).astype(np.float32), samplerate=SR,
                    device=self.out_device)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"воспроизведение: {exc}", "peak": 0.0}

        th.join(timeout=seconds + 1.0)
        if not captured:
            return {"ok": False, "reason": "микрофон не открылся", "peak": 0.0}

        audio = captured[0]
        peak = float(np.abs(audio).max())
        rms = float(np.sqrt((audio.astype("float64") ** 2).mean()))
        return {"ok": True, "peak": peak, "rms": rms}

    def calibrate(self, phrase_path: str) -> dict:
        """Подобрать громкость, при которой микрофон слышит фразу.

        Целевой уровень в микрофоне ~0.05-0.35: ниже — не расслышат,
        выше — риск свиста и искажений.
        """
        import soundfile as sf
        try:
            data, sr = sf.read(phrase_path, dtype="float32", always_2d=False)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"фраза: {exc}"}
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != SR:
            # scipy нет в EXE (исключён из сборки) -> линейная интерполяция
            n_out = int(round(len(data) * SR / sr))
            if n_out > 0 and len(data) > 1:
                x_in = np.arange(len(data), dtype=np.float64)
                x_out = np.linspace(0, len(data) - 1, n_out)
                data = np.interp(x_out, x_in, data).astype(np.float32)
        peak = float(np.abs(data).max())
        if peak > 0:
            data = data / peak

        best = None
        for gain in (0.35, 0.55, 0.75, 0.9, 1.0):
            res = self._measure_pickup(data, gain)
            if not res.get("ok"):
                continue
            level = res["peak"]
            # берём самый тихий gain, который микрофон ещё слышит уверенно
            if level >= 0.04:
                best = {"gain": gain, "level": level, "rms": res["rms"]}
                break
            if best is None or level > best["level"]:
                best = {"gain": gain, "level": level, "rms": res["rms"]}

        if best is None:
            return {"ok": False, "reason": "микрофон ничего не слышит"}
        self.gain = best["gain"]
        self.calibrated = True
        loud = best["level"] > 0.6
        return {"ok": True, "gain": best["gain"], "level": best["level"],
                "loud": loud,
                "reason": ("сигнал сильный — возможен свист, убавь громкость"
                           if loud else "")}

    # ---------- воспроизведение ----------
    def play(self, phrase_path: str, gain: float | None = None) -> bool:
        import sounddevice as sd
        import soundfile as sf
        try:
            data, sr = sf.read(phrase_path, dtype="float32", always_2d=False)
        except Exception:
            return False
        if data.ndim > 1:
            data = data.mean(axis=1)
        g = self.gain if gain is None else gain
        try:
            sd.play((data * g).astype(np.float32), samplerate=sr, device=self.out_device)
            return True
        except Exception:
            return False
