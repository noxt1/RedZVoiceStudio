"""Проверка «живости»: тон реально меняет подачу голоса.

Синтезирует одну и ту же фразу с разными тонами и сравнивает:
  * темп (длительность);
  * разброс высоты тона F0 (экспрессия);
  * пик/средний уровень (энергия).

Движок нужен с torch:
    "<engine>\\Scripts\\python.exe" research\\test_voice_tone.py
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import prosody  # noqa: E402
import voice_tone as vt  # noqa: E402

SR = 24000
WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
REF = os.path.join(WS, "reference.wav")

PHRASES = [
    ("aggressive", "Eres un maldito cabron, no te mas"),
    ("friendly", "Hola amigo, me da gusto verte, gracias"),
]


def main() -> None:
    if not os.path.exists(REF):
        print(f"нет образца голоса: {REF}")
        return

    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    # torchaudio -> soundfile (обход torchcodec/FFmpeg), как в движке
    try:
        import xtts_clone
        xtts_clone.patch_torchaudio()
    except Exception as exc:  # noqa: BLE001
        print(f"патч torchaudio не применился: {exc}")

    cfg = XttsConfig()
    snap = None
    hf = os.path.expanduser(r"~\.cache\huggingface\hub")
    import glob
    snaps = glob.glob(os.path.join(hf, "models--tts-hub--XTTS-v2", "snapshots", "*"))
    if snaps:
        snap = snaps[0]
        cfg.load_json(os.path.join(snap, "config.json"))
    tts = Xtts.init_from_config(cfg)
    if snap:
        tts.load_checkpoint(cfg, checkpoint_dir=snap,
                            vocab_path=os.path.join(snap, "vocab.json"))
    tts.cuda()
    print("модель загружена, считаю кэш голоса…")
    gpt_latent, spk_emb = tts.get_conditioning_latents(audio_path=[REF])

    print("\n=== сравнение тонов ===")
    rows = []
    for label, text in PHRASES:
        tone, params = vt.describe(text)
        assert tone == label, f"тон определён неверно: {tone} != {label}"
        t0 = time.time()
        chunks = tts.inference_stream(
            text, "es", gpt_latent, spk_emb,
            stream_chunk_size=10, **params)
        audio = np.concatenate([c.detach().cpu().numpy() for c in chunks])
        dur = len(audio) / SR
        f0_std = prosody.f0_spread(audio, SR)
        f0_range = prosody.f0_range(audio, SR)
        peak = float(np.abs(audio).max())
        rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
        rows.append((label, dur, f0_std, f0_range, peak, rms, time.time() - t0))
        print(f"  {label:<11} темп={dur:.2f}с  F0 σ={f0_std:.1f}  "
              f"F0 размах={f0_range:.0f}  пик={peak:.3f}  RMS={rms:.4f}  "
              f"(синтез {rows[-1][6]:.1f}с)")

    if len(rows) == 2:
        ag, fr = rows[0], rows[1]
        print("\n=== ИТОГ ===")
        d_tempo = (ag[1] - fr[1]) / max(0.01, fr[1]) * 100
        print(f"  злой тон короче на {abs(d_tempo):.0f}% "
              f"(ag={ag[1]:.2f}с vs friendly={fr[1]:.2f}с)")
        print(f"  разброс F0: злой {ag[2]:.1f} Гц vs добрый {fr[2]:.1f} Гц")
        print(f"  энергия RMS: злой {ag[5]:.4f} vs добрый {fr[5]:.4f}")


if __name__ == "__main__":
    main()
