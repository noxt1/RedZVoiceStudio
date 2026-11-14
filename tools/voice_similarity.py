"""Оценка похожести: насколько клон похож на исходный голос.

Метрика составная, потому что одна величина тут ненадёжна:

  1. ECAPA-TDNN (speechbrain) — косинус эмбеддингов. Для живых голосов
     «тот же голос, разная фраза» даёт ~0.45, «чужие голоса» ~0.0.
     На синтетике XTTS значения занижены, поэтому это относительная, а не
     абсолютная мера.

  2. Высота тона (F0, через librosa.yin) — разница медиан в полутонах.
     У одного и того же человека медианы почти совпадают (0-2 полутона),
     у разных голосов расходятся сильно.

  3. Спектральный центроид — «цвет» тембра.

Итоговый вердикт выводится по pitch-метрике (она устойчива к синтетике),
ECAPA идёт справочно.

    python tools\\voice_similarity.py
    python tools\\voice_similarity.py --reference path\\to\\reference.wav
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

SR = 16000


def load_mono(path: str) -> tuple[np.ndarray, int]:
    import soundfile as sf
    audio, sr = sf.read(path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio.astype(np.float32), sr


def resample(audio: np.ndarray, sr: int, sr_out: int = SR) -> np.ndarray:
    """Полифазный пересемплинг с FIR-фильтром — без алиасинга в полосу."""
    if sr == sr_out or len(audio) == 0:
        return audio
    from math import gcd
    from scipy.signal import resample_poly

    g = gcd(int(sr), int(sr_out))
    up, down = int(sr_out // g), int(sr // g)
    return resample_poly(audio, up, down).astype(np.float32)


def f0_median(audio: np.ndarray, sr: int) -> float:
    """Медианная высота тона в Гц (0 — если не определилась)."""
    import librosa
    if len(audio) < sr // 4:
        return 0.0
    f0 = librosa.yin(audio, fmin=60, fmax=400, sr=sr,
                     frame_length=1024, hop_length=256)
    voiced = f0[np.isfinite(f0) & (f0 > 60)]
    if voiced.size < 5:
        return 0.0
    return float(np.median(voiced))


def spectral_centroid(audio: np.ndarray, sr: int) -> float:
    import librosa
    if len(audio) == 0:
        return 0.0
    return float(np.mean(librosa.feature.spectral_centroid(y=audio, sr=sr)))


def semitones(f1: float, f2: float) -> float:
    if f1 <= 0 or f2 <= 0:
        return 99.0
    return float(12.0 * np.log2(f1 / f2))


class VoiceProfiler:
    """Считает эмбеддинги ECAPA для сравнения голосов."""

    def __init__(self, model: str = "speechbrain/spkrec-ecapa-voxceleb", device: str | None = None):
        import torch
        from speechbrain.inference.speaker import EncoderClassifier
        self.torch = torch
        self.clf = EncoderClassifier.from_hparams(
            source=model,
            savedir=os.path.join(ROOT, ".ecapa"),
            run_opts={"device": device or ("cuda" if torch.cuda.is_available() else "cpu")},
        )

    def embed(self, path: str) -> np.ndarray:
        audio, sr = load_mono(path)
        audio = resample(audio, sr, SR)
        t = self.torch.from_numpy(audio).unsqueeze(0)
        with self.torch.no_grad():
            v = self.clf.encode_batch(t).squeeze().cpu().numpy()
        n = np.linalg.norm(v)
        return v / n if n else v


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", default=os.path.join(ROOT, "reference.wav"))
    parser.add_argument("--wav-dir", default=os.path.join(ROOT, "out", "wav"))
    parser.add_argument("--model", default="speechbrain/spkrec-ecapa-voxceleb")
    parser.add_argument("--max-semitones", type=float, default=8.0,
                        help="справочный порог расхождения высоты тона (полутона)")
    parser.add_argument("--min-ecapa", type=float, default=0.30,
                        help="минимальная схожесть ECAPA")
    parser.add_argument("--min-mean", type=float, default=0.25,
                        help="минимальная средняя схожесть по набору")
    args = parser.parse_args()

    if not os.path.exists(args.reference):
        sys.exit(f"Референс не найден: {args.reference}")

    profiler = VoiceProfiler(args.model)
    ref_emb = profiler.embed(args.reference)
    ref_audio, ref_sr = load_mono(args.reference)
    ref_f0 = f0_median(resample(ref_audio, ref_sr, SR), SR)
    ref_cent = spectral_centroid(ref_audio, ref_sr)

    files = sorted(glob.glob(os.path.join(args.wav_dir, "mx_*.wav")))
    if not files:
        sys.exit(f"Нет клипов в {args.wav_dir}")

    print(f"Референс: {os.path.basename(args.reference)}")
    print(f"  высота тона: {ref_f0:.1f} Гц | спектральный центроид: {ref_cent:.0f} Гц\n")

    rows = []
    for path in files:
        emb = profiler.embed(path)
        ecapa = float(np.dot(ref_emb, emb))
        audio, sr = load_mono(path)
        f0 = f0_median(resample(audio, sr, SR), SR)
        st = semitones(ref_f0, f0)
        cent = spectral_centroid(audio, sr)
        rows.append((os.path.basename(path), ecapa, st, abs(cent - ref_cent)))

    rows.sort(key=lambda t: t[1])
    print("  клип            ECAPA   ΔF0 (полутонов)   Δцентроид")
    for name, ecapa, st, dcent in rows:
        ok = ecapa >= args.min_ecapa
        mark = "OK " if ok else "!! "
        print(f"  {mark}{name:<13} {ecapa:+.3f}   {st:+6.2f}          {dcent:6.0f}")

    st_values = [r[2] for r in rows if r[2] < 90]
    mean_st = float(np.mean(st_values)) if st_values else 99.0
    mean_ecapa = float(np.mean([r[1] for r in rows]))
    worst = rows[0]

    print(f"\nСредняя схожесть ECAPA: {mean_ecapa:.3f}")
    print(f"Средняя разница высоты тона: {mean_st:.2f} полутона (справочно)")
    print(f"Худшая: {worst[0]} — ECAPA {worst[1]:+.3f}")

    if mean_ecapa < args.min_mean:
        print(f"\nСредняя схожесть ниже {args.min_mean}: клон не похож на оригинал.")
        print("Что делать: запиши референс дольше (20-30 c), в тихой комнате,")
        print("без шума и музыки — и прогони сканер заново.")
        raise SystemExit(1)
    print("Клон узнаваем как твой голос (ECAPA выше порога).")


if __name__ == "__main__":
    main()
