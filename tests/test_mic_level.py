"""Порог речи не зависит от громкости: тихая речь доходит до Whisper.

Замер (tools/check_mic_gain.py) показал: одна и та же запись, ослабленная
на 18 дБ, теряла 9 фраз из 18 ещё до движка — виноват абсолютный порог
0.006 и требование `rms > thr*1.5`. Эти тесты фиксируют, что такого больше
нет: сегментация работает от шума комнаты, а не от абсолютного уровня.

Сигнал синтетический (речь не записывается), поэтому тест воспроизводим
на любой машине и не требует torch.
"""

from __future__ import annotations

import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "app"), os.path.join(ROOT, "app", "qtapp")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from live_engine import LiveEngine  # noqa: E402
from audio_diag import segment_metrics  # noqa: E402

import live_engine  # noqa: E402

SR = live_engine.SR_REC
BLOCK = live_engine.BLOCK_SEC


def speech_like(seconds: float, rms: float, sr: int = 44100,
                seed: int = 7) -> np.ndarray:
    """Сигнал, похожий на речь: гармоники + слоговая модуляция.

    Уровень задаётся по RMS громких участков, поэтому тест не зависит от
    формы огибающей. Клиппинга нет: пик держится около 3·RMS.
    """
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    carrier = (0.62 * np.sin(2 * np.pi * 180 * t)
               + 0.28 * np.sin(2 * np.pi * 540 * t + 0.7)
               + 0.10 * np.sin(2 * np.pi * 1300 * t + 1.9))
    carrier += 0.05 * rng.standard_normal(n)          # шипящие
    syllables = 0.15 + 0.85 * np.sin(2 * np.pi * 4.0 * t) ** 2
    env = syllables.copy()
    # Межсловные паузы по 0,2 с: у настоящей речи отношение громких кадров
    # к тихим — 4…20, у ровного шума — около 1,05.
    gap = int(0.2 * sr)
    step = int(0.9 * sr)
    for start in range(int(0.35 * sr), n - gap, step):
        env[start:start + gap] = 0.0
    ramp = int(0.03 * sr)
    env[:ramp] *= np.linspace(0.0, 1.0, ramp)
    env[-ramp:] *= np.linspace(1.0, 0.0, ramp)
    sig = carrier * env
    loud = env > 0.5
    sig *= rms / max(float(np.sqrt(np.mean(sig[loud] ** 2))), 1e-9)
    return sig.astype(np.float32)


def silence(seconds: float, sr: int = 44100) -> np.ndarray:
    return np.zeros(int(seconds * sr), dtype=np.float32)


def run_engine(audio: np.ndarray, sr: int = 44100) -> list[np.ndarray]:
    """Прогнать сигнал блоками через настоящий колбэк микрофона."""
    engine = LiveEngine()
    engine._cont_on = True
    captured: list[np.ndarray] = []
    engine._queue_translate = lambda pcm, sr_: captured.append(pcm)
    size = int(sr * BLOCK)
    for i in range(0, len(audio) - size + 1, size):
        engine._cont_callback(audio[i:i + size].reshape(-1, 1), size,
                             None, None)
    engine._flush_segment()
    return captured


class LevelGateTest(unittest.TestCase):
    def test_any_level_reaches_engine(self) -> None:
        """−20, −40 и −52 dBFS дают один и тот же сегмент.

        До исправления тихие уровни отбрасывались целиком (`strong < 3`
        при абсолютном пороге 0.006), и в Whisper уходила тишина.
        """
        for dbfs in (-20, -40, -52):
            rms = 10 ** (dbfs / 20.0)
            audio = np.concatenate([silence(0.6),
                                    speech_like(1.6, rms),
                                    silence(1.2)])
            segs = run_engine(audio)
            self.assertEqual(len(segs), 1, f"{dbfs} dBFS: {len(segs)} сегментов")
            seg = segs[0]
            self.assertGreater(float(np.sqrt(np.mean(seg ** 2))), rms * 0.5,
                               f"{dbfs} dBFS: сигнал потерян")

    def test_level_invariance(self) -> None:
        """Ослабление на 18 дБ не меняет форму сегмента (только уровень)."""
        base = np.concatenate([silence(0.6), speech_like(1.6, 0.05),
                               silence(1.2)])
        quiet = (base * 0.126).astype(np.float32)
        a, b = run_engine(base)[0], run_engine(quiet)[0]
        self.assertAlmostEqual(len(a) / SR, len(b) / SR, delta=0.06)
        n = min(len(a), len(b))
        corr = float(np.corrcoef(a[:n], b[:n])[0, 1])
        self.assertGreater(corr, 0.9, f"форма изменилась: r={corr:.2f}")

    def test_noise_alone_is_dropped(self) -> None:
        """Ровный шум на любом уровне не считается речью."""
        rng = np.random.default_rng(11)
        for amp in (0.002, 0.01, 0.05):
            noise = (rng.standard_normal(int(3.0 * SR)) * amp).astype(np.float32)
            self.assertEqual(run_engine(noise), [], f"шум amp={amp} прошёл")

    def test_quiet_ending_kept(self) -> None:
        """Тихое окончание слова не срезается обрезкой тишины."""
        body = speech_like(1.4, 0.05)
        # Тихий «фриктив» на 18 дБ тише тела слова, без пауз внутри.
        t = np.arange(int(0.45 * SR)) / SR
        tail = (0.006 * np.sin(2 * np.pi * 700 * t)).astype(np.float32)
        audio = np.concatenate([silence(0.4), body, tail, silence(0.8)])
        seg = run_engine(audio)[0]
        cut = LiveEngine._trim_silence(audio)
        # Обрезка снимает только тишину до и после фразы (с запасом
        # 0,25 с), но не саму речь.
        self.assertGreater(len(cut), int(0.75 * len(audio)),
                           "обрезка съела полезную часть записи")
        self.assertGreater(len(seg), int(2.2 * SR))
        # Тихий хвост (перед обязательной тишиной-запасом 0,25 с) выжил.
        window = seg[-int(0.45 * SR):-int(0.25 * SR)]
        self.assertGreater(float(np.sqrt(np.mean(window ** 2))), 1e-5,
                           "тихое окончание срезано")

    def test_no_clipping(self) -> None:
        """Громкий вход не даёт клиппинга после обработки."""
        audio = np.concatenate([silence(0.4), speech_like(1.5, 0.3) * 3.2,
                                silence(0.8)])
        audio = np.clip(audio, -1.0, 1.0).astype(np.float32)
        for seg in run_engine(audio):
            self.assertTrue(np.all(np.isfinite(seg)))
            self.assertLessEqual(float(np.abs(seg).max()), 1.0)
            self.assertEqual(segment_metrics(seg, SR)["clipping"], 0.0)

    def test_short_pause_kept_in_one_segment(self) -> None:
        """Пауза 0.4 с внутри фразы не рвёт её на две реплики."""
        audio = np.concatenate([silence(0.5), speech_like(0.8, 0.05),
                                silence(0.4), speech_like(0.8, 0.05),
                                silence(1.1)])
        self.assertEqual(len(run_engine(audio)), 1)

    def test_long_pause_splits(self) -> None:
        """Пауза 1.2 с — это уже две фразы."""
        audio = np.concatenate([silence(0.5), speech_like(0.8, 0.05),
                                silence(1.2), speech_like(0.8, 0.05),
                                silence(1.1)])
        self.assertEqual(len(run_engine(audio)), 2)

    def test_segment_lengths(self) -> None:
        """Короткая, средняя и длинная фразы дают по одному сегменту."""
        for seconds in (0.5, 3.0, 8.0):
            audio = np.concatenate([silence(0.5), speech_like(seconds, 0.05),
                                    silence(1.0)])
            segs = run_engine(audio)
            self.assertEqual(len(segs), 1, f"{seconds} с: {len(segs)}")


class StructureTest(unittest.TestCase):
    def test_speech_passes_noise_fails(self) -> None:
        for rms in (0.002, 0.02, 0.2):
            self.assertTrue(
                LiveEngine._has_speech_structure(speech_like(1.0, rms)),
                f"речь RMS {rms} не распознана как речь")
            rng = np.random.default_rng(5)
            noise = (rng.standard_normal(SR) * rms).astype(np.float32)
            self.assertFalse(LiveEngine._has_speech_structure(noise),
                             f"шум RMS {rms} принят за речь")

    def test_short_segment_accepted(self) -> None:
        self.assertTrue(LiveEngine._has_speech_structure(
            speech_like(0.1, 0.02)))
        self.assertFalse(LiveEngine._has_speech_structure(
            np.zeros(0, dtype=np.float32)))


class ResampleTest(unittest.TestCase):
    def test_resample_keeps_duration_and_tone(self) -> None:
        """44,1 → 16 кГц: длительность и частота тона сохраняются."""
        from live_client import resample_to_16k
        t = np.arange(int(0.5 * SR)) / SR
        tone = np.sin(2 * np.pi * 440 * t).astype(np.float32)
        out = resample_to_16k(tone, SR)
        self.assertEqual(len(out), int(round(len(tone) * 16000 / SR)))
        self.assertTrue(np.all(np.isfinite(out)))
        self.assertGreater(float(np.corrcoef(
            out[:4000], np.sin(2 * np.pi * 440 * np.arange(4000) / 16000))[0, 1]),
            0.95)
        self.assertAlmostEqual(float(np.sqrt(np.mean(out ** 2))),
                               float(np.sqrt(np.mean(tone ** 2))), delta=0.02)


if __name__ == "__main__":
    unittest.main(verbosity=2)
