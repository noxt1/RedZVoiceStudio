"""Замер: сколько VRAM занимает каждая модель движка.

Движок держит три модели: Whisper (распознавание), opus-mt (перевод) и
XTTS (синтез). Это нужно, чтобы понимать, что оптимизировать: на карте
16 ГБ и параллельно с игрой важно знать, кто сколько ест.

    "<engine>\\Scripts\\python.exe" research\\bench_vram_parts.py
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Auraloom", "workspace")
REF = os.path.join(WS, "reference.wav")


def vram() -> int:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15).stdout.strip()
        return int(out.split("\n")[0])
    except Exception:
        return 0


def step(label: str, before: int) -> int:
    now = vram()
    print(f"  {label:<34} VRAM {now:>6} МБ  (+{now - before})")
    return now


def main() -> None:
    base = vram()
    print(f"  {'этап':<34} {'VRAM':>10}")
    print(f"  {'исходно (пусто)':<34} {base:>6} МБ")

    import torch
    prev = base
    prev = step("пустой torch (контекст)", prev)

    from faster_whisper import WhisperModel
    asr = WhisperModel("mobiuslabsgmbh/faster-whisper-large-v3-turbo",
                       device="cuda", compute_type="float16")
    prev = step("Whisper large-v3-turbo", prev)

    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-ru-es")
    mt = AutoModelForSeq2SeqLM.from_pretrained(
        "Helsinki-NLP/opus-mt-ru-es", dtype=torch.float32).to("cpu").eval()
    prev = step("opus-mt (CPU, VRAM не жрёт)", prev)

    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    try:
        import xtts_clone
        xtts_clone.patch_torchaudio()
    except Exception:
        pass
    hf = os.path.expanduser(r"~\.cache\huggingface\hub")
    snaps = glob.glob(os.path.join(hf, "models--tts-hub--XTTS-v2", "snapshots", "*"))
    cfg = XttsConfig()
    cfg.load_json(os.path.join(snaps[0], "config.json"))
    tts = Xtts.init_from_config(cfg)
    tts.load_checkpoint(cfg, checkpoint_dir=snaps[0],
                        vocab_path=os.path.join(snaps[0], "vocab.json"))
    prev = step("XTTS (до .cuda())", prev)
    tts.cuda()
    prev = step("XTTS на GPU", prev)
    gpt_latent, spk_emb = tts.get_conditioning_latents(audio_path=[REF])
    prev = step("XTTS + кэш голоса", prev)

    print(f"\n  ИТОГО движок занимает примерно {prev - base} МБ VRAM")
    print("  (с Whisper small вместо turbo будет меньше — замерить отдельно)")


if __name__ == "__main__":
    main()
